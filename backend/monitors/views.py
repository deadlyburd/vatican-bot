from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import Agency, MonitorTask, CheckResult, Proxy, SiteCredential, User
from .serializers import (
    AgencySerializer, MonitorTaskSerializer, CheckResultSerializer,
    ProxySerializer, SiteCredentialSerializer
)
import logging
import secrets
import random
from django.utils import timezone

logger = logging.getLogger(__name__)


# ============================================
# Authentication APIs
# ============================================

@api_view(['POST'])
def register_user(request):
    """
    Register a new user.
    Body: {
        "email": "user@example.com",
        "username": "username",
        "password": "password123",
        "full_name": "Full Name",
        "agency_id": 1  # Optional - if not provided, creates new agency
    }
    """
    try:
        email = request.data.get('email')
        username = request.data.get('username')
        password = request.data.get('password')
        full_name = request.data.get('full_name', '')
        agency_id = request.data.get('agency_id')
        
        # Validation
        if not email or not username or not password:
            return Response({'error': 'Email, username, and password are required'}, status=400)
        
        # Check if user already exists
        if User.objects.filter(email=email).exists():
            return Response({'error': 'Email already registered'}, status=400)
        
        if User.objects.filter(username=username).exists():
            return Response({'error': 'Username already taken'}, status=400)
        
        # Get or create agency
        if agency_id:
            try:
                agency = Agency.objects.get(id=agency_id)
            except Agency.DoesNotExist:
                return Response({'error': 'Agency not found'}, status=404)
        else:
            # Create new agency for this user
            agency = Agency.objects.create(
                name=f"{username}'s Agency",
                api_key=secrets.token_hex(16),
                plan='free'
            )
        
        # Create user
        user = User.objects.create(
            email=email,
            username=username,
            full_name=full_name,
            agency=agency
        )
        user.set_password(password)
        user.save()
        
        # Generate session token (simple token for now)
        session_token = secrets.token_urlsafe(32)
        
        # Store session in cache (expires in 7 days)
        from django.core.cache import cache
        cache.set(f"session:{session_token}", {
            'user_id': user.id,
            'agency_id': agency.id,
            'username': user.username
        }, timeout=7*24*60*60)
        
        return Response({
            'success': True,
            'message': 'User registered successfully',
            'session_token': session_token,
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'full_name': user.full_name
            },
            'agency': {
                'id': agency.id,
                'name': agency.name,
                'plan': agency.plan
            }
        })
        
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
def login_user(request):
    """
    Login user.
    Body: {
        "username": "username or email",
        "password": "password123"
    }
    """
    try:
        username_or_email = request.data.get('username')
        password = request.data.get('password')
        
        if not username_or_email or not password:
            return Response({'error': 'Username/email and password are required'}, status=400)
        
        # Find user by username or email
        from django.db.models import Q
        user = User.objects.filter(
            Q(username=username_or_email) | Q(email=username_or_email)
        ).first()
        
        if not user:
            return Response({'error': 'Invalid credentials'}, status=401)
        
        if not user.is_active:
            return Response({'error': 'Account is inactive'}, status=403)
        
        # Check password
        if not user.check_password(password):
            return Response({'error': 'Invalid credentials'}, status=401)
        
        # Update last login
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        
        # Generate session token
        session_token = secrets.token_urlsafe(32)
        
        # Store session in cache (expires in 7 days)
        from django.core.cache import cache
        cache.set(f"session:{session_token}", {
            'user_id': user.id,
            'agency_id': user.agency.id,
            'username': user.username,
            'is_super_admin': user.is_super_admin  # Include super admin flag
        }, timeout=7*24*60*60)
        
        return Response({
            'success': True,
            'message': 'Login successful',
            'session_token': session_token,
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'full_name': user.full_name,
                'is_admin': user.is_admin,
                'is_super_admin': user.is_super_admin  # Include in response
            },
            'agency': {
                'id': user.agency.id,
                'name': user.agency.name,
                'plan': user.agency.plan,
                'telegram_chat_id': user.agency.telegram_chat_id
            }
        })
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
def logout_user(request):
    """
    Logout user.
    Headers: Authorization: Bearer <session_token>
    """
    try:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return Response({'error': 'Invalid authorization header'}, status=401)
        
        session_token = auth_header.replace('Bearer ', '')
        
        # Delete session from cache
        from django.core.cache import cache
        cache.delete(f"session:{session_token}")
        
        return Response({
            'success': True,
            'message': 'Logged out successfully'
        })
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
def verify_session(request):
    """
    Verify session token and return user info.
    Headers: Authorization: Bearer <session_token>
    """
    try:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return Response({'error': 'Invalid authorization header'}, status=401)
        
        session_token = auth_header.replace('Bearer ', '')
        
        # Get session from cache
        from django.core.cache import cache
        session_data = cache.get(f"session:{session_token}")
        
        if not session_data:
            return Response({'error': 'Invalid or expired session'}, status=401)
        
        # Get user
        user = User.objects.select_related('agency').get(id=session_data['user_id'])
        
        if not user.is_active:
            return Response({'error': 'Account is inactive'}, status=403)
        
        return Response({
            'success': True,
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'full_name': user.full_name,
                'is_admin': user.is_admin,
                'is_super_admin': user.is_super_admin
            },
            'agency': {
                'id': user.agency.id,
                'name': user.agency.name,
                'plan': user.agency.plan,
                'telegram_chat_id': user.agency.telegram_chat_id
            }
        })
        
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=404)
    except Exception as e:
        logger.error(f"Session verification error: {e}")
        return Response({'error': str(e)}, status=500)


def get_user_from_request(request):
    """Helper function to get user from session token"""
    try:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None
        
        session_token = auth_header.replace('Bearer ', '')
        
        from django.core.cache import cache
        session_data = cache.get(f"session:{session_token}")
        
        if not session_data:
            return None
        
        user = User.objects.select_related('agency').get(id=session_data['user_id'])
        return user if user.is_active else None
        
    except:
        return None


class AgencyViewSet(viewsets.ModelViewSet):
    queryset = Agency.objects.all()
    serializer_class = AgencySerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    
    def get_queryset(self):
        """Filter agencies based on authenticated user"""
        user = get_user_from_request(self.request)
        if user:
            # User can only see their own agency
            return Agency.objects.filter(id=user.agency.id)
        # If no auth, return empty (or all for backwards compatibility during migration)
        return Agency.objects.all()


class MonitorTaskViewSet(viewsets.ModelViewSet):
    serializer_class = MonitorTaskSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        """Filter tasks based on authenticated user's agency"""
        user = get_user_from_request(self.request)
        
        queryset = MonitorTask.objects.all()
        
        # Filter by user's agency if authenticated
        if user:
            queryset = queryset.filter(agency=user.agency)
        else:
            # Backwards compatibility: allow agency_id query param
            agency_id = self.request.query_params.get('agency_id')
            if agency_id:
                queryset = queryset.filter(agency_id=agency_id)
        
        return queryset

    def perform_create(self, serializer):
        # No monitor count limits — plan gates tier features (hold/snipe), not quantity
        serializer.save()

class CheckResultViewSet(viewsets.ModelViewSet):
    serializer_class = CheckResultSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        """Filter results based on authenticated user's agency"""
        user = get_user_from_request(self.request)
        
        queryset = CheckResult.objects.all().order_by('-check_time')
        task_id = self.request.query_params.get('task')
        
        # Filter by user's agency if authenticated
        if user:
            queryset = queryset.filter(task__agency=user.agency)
        else:
            # Backwards compatibility
            agency_id = self.request.query_params.get('agency_id')
            if agency_id:
                queryset = queryset.filter(task__agency_id=agency_id)
        
        if task_id:
            queryset = queryset.filter(task_id=task_id)
            
        return queryset

class ProxyViewSet(viewsets.ModelViewSet):
    queryset = Proxy.objects.all()
    serializer_class = ProxySerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

class SiteCredentialViewSet(viewsets.ModelViewSet):
    queryset = SiteCredential.objects.all()
    serializer_class = SiteCredentialSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

class AgencyLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # ✅ Disable SessionAuth to bypass CSRF

    def post(self, request):
        name = request.data.get('name')
        api_key = request.data.get('api_key')
        
        if not name or not api_key:
            return Response({'error': 'Name and API Key search required'}, status=status.HTTP_400_BAD_REQUEST)
            
        agency = Agency.objects.filter(name=name, api_key=api_key).order_by('id').first()
        
        if not agency:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
            
        if not agency.is_active:
            return Response({'error': 'Agency account is inactive'}, status=status.HTTP_403_FORBIDDEN)
            
        return Response({
            'id': agency.id,
            'name': agency.name,
            'chat_id': agency.telegram_chat_id
        })

class MyAgencyView(APIView):
    """
    Get or Create an Agency for the authenticated Clerk User.
    Expects 'owner_id' in request data.
    """
    permission_classes = [permissions.AllowAny] # In future, verify JWT
    authentication_classes = []  # ✅ Disable SessionAuth to bypass CSRF

    def post(self, request):
        owner_id = request.data.get('owner_id', 'local-admin')
        email = request.data.get('email', 'admin@local.com')
        
        # 1. Try to find by ID first
        agency = Agency.objects.filter(owner_id=owner_id).first()
        created = False
        
        if not agency:
             # 2. Account Recovery: Try to find orphaned agency by name pattern
             email_prefix = email.split('@')[0]
             potential_name = f"Agency-{email_prefix}"
             
             # Also try relaxed match if name was user-edited, but this is risky.
             # Stick to default name pattern for auto-recovery.
             agency = Agency.objects.filter(name=potential_name, owner_id__isnull=True).first()
             
             if agency:
                 # ✅ Claim it!
                 agency.owner_id = owner_id
                 agency.save()
             else:
                 # 3. Create new
                 import uuid
                 defaults = {
                    'name': f"Agency-{email_prefix}",
                    'api_key': str(uuid.uuid4())[:8]
                 }
                 agency, created = Agency.objects.get_or_create(
                    owner_id=owner_id,
                    defaults=defaults
                 )
            
        return Response({
            'id': agency.id,
            'name': agency.name,
            'api_key': agency.api_key,
            'chat_id': agency.telegram_chat_id,
            'plan': agency.plan,
            'task_limit': {'free': 1000, 'pro': 2000, 'agency': 5000}.get(agency.plan, 1000)
        })


# ✅ NEW: Vatican Ticket Discovery API
from rest_framework.decorators import api_view

@api_view(['GET'])
def get_vatican_tickets(request):
    """
    Returns list of available Vatican tickets with their IDs and language requirements.
    Dynamically fetches from Vatican website using HydraBot.
    Cleans up and groups tickets for better display.
    
    Query params:
        date: DD/MM/YYYY format (default: 20/02/2026)
    
    Returns:
        {
            'date': '20/02/2026',
            'tickets': [...],
            'grouped': {...}  # Tickets grouped by category
        }
    """
    date = request.query_params.get('date', '20/02/2026')
    visitors = int(request.query_params.get('visitors', 1))
    
    # Ticket name mappings - ORDER MATTERS! Check ticket types FIRST, locations LAST
    # These are checked in order, so more specific terms should come first
    TICKET_TYPE_KEYWORDS = [
        # Ticket types (check these FIRST)
        ('visita guidata', 'Guided Tour'),
        ('tour guidato', 'Guided Tour'),
        ('visite guidate', 'Guided Tour'),
        ('audioguida', 'Entry + Audio Guide'),
        ('ingresso intero', 'Standard Entry (Full Price)'),
        ('ingresso ridotto', 'Standard Entry (Reduced)'),
        ('ingresso gratuito', 'Standard Entry (Free)'),
        ('biglietto di ingresso', 'Standard Entry'),
        ('biglietto ingresso', 'Standard Entry'),
        ("biglietti d'ingresso", 'Standard Entry'),
        ('biglietti di ingresso', 'Standard Entry'),
        # Special experiences
        ('prime experience', 'Prime Experience'),
        ('experience', 'Special Experience'),
        # Locations (check LAST as fallback)
        ('cappella sistina', 'Sistine Chapel'),
        ('giardini vaticani', 'Vatican Gardens'),
    ]
    
    def normalize_ticket_name(raw_name):
        """Parse Italian ticket name and return clean English label + time slot"""
        name_lower = raw_name.lower()
        
        # Extract time slot if present (e.g., "09:00", "14:30")
        import re
        time_match = re.search(r'(\d{1,2}[:\.]?\d{2})', raw_name)
        time_slot = time_match.group(1).replace('.', ':') if time_match else None
        
        # Determine category - check in order, first match wins
        category = 'Vatican Museums'  # Default fallback
        for italian, english in TICKET_TYPE_KEYWORDS:
            if italian in name_lower:
                category = english
                break
        
        # Build clean name
        if time_slot:
            clean_name = f"{category} - {time_slot}"
        else:
            clean_name = category
            
        return {
            'clean_name': clean_name,
            'category': category,
            'time_slot': time_slot,
            'original_name': raw_name
        }
    
    try:
        from worker_vatican.hydra_monitor import HydraBot
        import asyncio
        import logging
        
        async def fetch_category(browser, bot, ticket_type):
            """Helper to fetch a specific category in its own page"""
            try:
                page = await browser.new_page()
                tickets = await bot.resolve_all_dynamic_ids(
                    page,
                    ticket_type=ticket_type,
                    target_date=date,
                    visitors=visitors
                )
                await page.close()
                return tickets
            except Exception as e:
                logger.error(f"Failed to fetch types={ticket_type}: {e}")
                return []

        async def fetch_tickets():
            bot = HydraBot()
            result = []
            
            try:
                async with bot.get_browser() as browser:
                    # Run standard (0) and guided (1) in parallel
                    task_standard = fetch_category(browser, bot, 0)
                    task_guided = fetch_category(browser, bot, 1)
                    
                    results = await asyncio.gather(task_standard, task_guided)
                    standard_tickets, guided_tickets = results
                    
                    # Process Standard
                    for ticket in standard_tickets:
                        try:
                            parsed = normalize_ticket_name(ticket['name'])
                            result.append({
                                'id': ticket['id'],
                                'name': parsed['clean_name'],
                                'originalName': parsed['original_name'],
                                'description': ticket.get('description', ''),
                                'category': parsed['category'],
                                'timeSlot': parsed['time_slot'],
                                'needsLanguage': False,
                                'availableLanguages': [],
                                'ticketType': 0,
                                'deepLink': ticket.get('deep_link', '')
                            })
                        except Exception as e:
                            logger.error(f"Error parsing ticket {ticket}: {e}")

                    # Process Guided
                    for ticket in guided_tickets:
                        try:
                            parsed = normalize_ticket_name(ticket['name'])
                            result.append({
                                'id': ticket['id'],
                                'name': parsed['clean_name'],
                                'originalName': parsed['original_name'],
                                'description': ticket.get('description', ''),
                                'category': parsed['category'],
                                'timeSlot': parsed['time_slot'],
                                'needsLanguage': True,
                                'availableLanguages': ['ENG', 'ITA', 'FRA', 'DEU', 'SPA'],
                                'ticketType': 1,
                                'deepLink': ticket.get('deep_link', '')
                            })
                        except Exception as e:
                            logger.error(f"Error parsing ticket {ticket}: {e}")
            
            except Exception as e:
                logger.error(f"Browser error: {e}")
                # Don't raise, return what we have (or empty) so UI doesn't crash 500
                pass
            
            return result
        
        tickets = asyncio.run(fetch_tickets())
        
        # Group tickets by category for cleaner display
        grouped = {}
        for ticket in tickets:
            cat = ticket['category']
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append(ticket)
        
        # Sort each group by time slot
        for cat in grouped:
            grouped[cat].sort(key=lambda t: t['timeSlot'] or '99:99')
        
        return Response({
            'date': date,
            'tickets': tickets,
            'grouped': grouped,
            'total': len(tickets)
        })
    
    except Exception as e:
        import traceback
        return Response({
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)



# ============================================
# Telegram Group Management APIs
# ============================================

@api_view(['GET'])
def list_telegram_groups(request):
    """
    List all Telegram groups with their approval status.
    Query params:
        status: Filter by status (pending/approved/rejected/suspended)
    """
    from .models import TelegramGroup
    
    status_filter = request.query_params.get('status')
    
    groups = TelegramGroup.objects.all()
    
    if status_filter:
        groups = groups.filter(status=status_filter)
    
    groups = groups.order_by('-created_at')
    
    data = []
    for group in groups:
        data.append({
            'id': group.id,
            'chat_id': group.chat_id,
            'chat_title': group.chat_title,
            'chat_type': group.chat_type,
            'chat_username': group.chat_username,
            'status': group.status,
            'agency': {
                'id': group.agency.id,
                'name': group.agency.name
            } if group.agency else None,
            'added_by': {
                'user_id': group.added_by_user_id,
                'username': group.added_by_username,
                'first_name': group.added_by_first_name
            },
            'member_count': group.member_count,
            'notification_enabled': group.notification_enabled,
            'created_at': group.created_at.isoformat(),
            'approved_at': group.approved_at.isoformat() if group.approved_at else None,
            'approved_by': group.approved_by,
            'rejection_reason': group.rejection_reason,
            'last_activity': group.last_activity.isoformat() if group.last_activity else None
        })
    
    return Response(data)


@api_view(['POST'])
def approve_telegram_group(request, group_id):
    """
    Approve a Telegram group.
    Body params:
        agency_id: Optional - Link group to specific agency
    """
    from .models import TelegramGroup, Agency
    import os
    
    try:
        group = TelegramGroup.objects.get(id=group_id)
        agency_id = request.data.get('agency_id')
        
        # Link to agency if provided
        if agency_id:
            try:
                agency = Agency.objects.get(id=agency_id)
                group.agency = agency
                group.save()
            except Agency.DoesNotExist:
                return Response({'error': 'Agency not found'}, status=404)
        
        # Approve
        admin_id = request.user.id if hasattr(request, 'user') and request.user.is_authenticated else 'admin'
        group.approve(admin_id=str(admin_id))
        
        # Send approval notification to group
        try:
            from telegram import Bot
            bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
            
            bot.send_message(
                chat_id=group.chat_id,
                text=(
                    f"✅ **Group Approved!**\n\n"
                    f"Your group has been approved by an admin.\n\n"
                    f"You will now receive notifications when Vatican tickets become available!\n\n"
                    f"Use /start to manage your monitors."
                ),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send approval notification: {e}")
        
        return Response({
            'success': True,
            'message': 'Group approved',
            'group': {
                'id': group.id,
                'chat_id': group.chat_id,
                'chat_title': group.chat_title,
                'status': group.status
            }
        })
        
    except TelegramGroup.DoesNotExist:
        return Response({'error': 'Group not found'}, status=404)
    except Exception as e:
        logger.error(f"Error approving group: {e}")
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
def reject_telegram_group(request, group_id):
    """
    Reject a Telegram group.
    Body params:
        reason: Rejection reason (required)
    """
    from .models import TelegramGroup
    import os
    
    try:
        group = TelegramGroup.objects.get(id=group_id)
        reason = request.data.get('reason', 'Not specified')
        
        # Reject
        admin_id = request.user.id if hasattr(request, 'user') and request.user.is_authenticated else 'admin'
        group.reject(admin_id=str(admin_id), reason=reason)
        
        # Send rejection notification to group
        try:
            from telegram import Bot
            bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
            
            bot.send_message(
                chat_id=group.chat_id,
                text=(
                    f"❌ **Group Rejected**\n\n"
                    f"Your group approval request has been rejected.\n\n"
                    f"**Reason:** {reason}\n\n"
                    f"Please contact support if you believe this is an error."
                ),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send rejection notification: {e}")
        
        return Response({
            'success': True,
            'message': 'Group rejected',
            'group': {
                'id': group.id,
                'chat_id': group.chat_id,
                'chat_title': group.chat_title,
                'status': group.status
            }
        })
        
    except TelegramGroup.DoesNotExist:
        return Response({'error': 'Group not found'}, status=404)
    except Exception as e:
        logger.error(f"Error rejecting group: {e}")
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
def suspend_telegram_group(request, group_id):
    """
    Suspend a Telegram group.
    Body params:
        reason: Suspension reason (optional)
    """
    from .models import TelegramGroup
    
    try:
        group = TelegramGroup.objects.get(id=group_id)
        reason = request.data.get('reason')
        
        group.suspend(reason=reason)
        
        return Response({
            'success': True,
            'message': 'Group suspended',
            'group': {
                'id': group.id,
                'chat_id': group.chat_id,
                'chat_title': group.chat_title,
                'status': group.status
            }
        })
        
    except TelegramGroup.DoesNotExist:
        return Response({'error': 'Group not found'}, status=404)
    except Exception as e:
        logger.error(f"Error suspending group: {e}")
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
def list_held_slots(request):
    """List all active held slots — all holds for super admin, agency-filtered otherwise."""
    from .models import HeldSlot
    from django.core.cache import cache

    # Check session for super admin
    auth_header = request.headers.get('Authorization', '')
    session_data = None
    if auth_header.startswith('Bearer '):
        token = auth_header.replace('Bearer ', '')
        session_data = cache.get(f"session:{token}")

    status_filter = request.query_params.get('status', 'held')

    # Super admin or no auth — return all holds
    if session_data and session_data.get('is_super_admin'):
        holds = HeldSlot.objects.all()
    else:
        agency = _get_agency_from_request(request)
        if not agency:
            # No auth — return all holds (for dashboard display)
            holds = HeldSlot.objects.all()
        else:
            holds = HeldSlot.objects.filter(task__agency=agency)

    if status_filter != 'all':
        holds = holds.filter(status=status_filter)

    holds = holds.order_by('date', 'slot_time', 'visitors')

    data = []
    for h in holds:
        import json as _json
        notes = {}
        try:
            notes = _json.loads(h.notes or '{}')
        except Exception:
            pass
        data.append({
            'id': h.id,
            'date': h.date,
            'slot_time': h.slot_time,
            'ticket_name': h.ticket_name,
            'visitors': h.visitors,
            'adult_count': h.adult_count,
            'child_count': h.child_count,
            'total_price': str(h.total_price),
            'status': h.status,
            'hold_duration_minutes': h.hold_duration_minutes(),
            'last_keepalive_at': h.last_keepalive_at.isoformat(),
            'hold_started_at': h.hold_started_at.isoformat(),
            'notes': notes,
        })
    return Response({'results': data, 'count': len(data)})


@api_view(['GET'])
def get_available_slots(request):
    """
    Get available slots for browser extension auto-booking.
    Returns slots that are currently held and ready to be booked.
    
    Query params:
    - status: Filter by status (default: 'held')
    - limit: Max number of slots to return (default: 10)
    """
    from .models import HeldSlot
    from django.core.cache import cache
    
    # Get query parameters
    status_filter = request.GET.get('status', 'held')
    limit = int(request.GET.get('limit', 10))
    
    # Check authentication
    auth_header = request.headers.get('Authorization', '')
    session_data = None
    if auth_header.startswith('Bearer '):
        token = auth_header.replace('Bearer ', '')
        session_data = cache.get(f"session:{token}")
    
    # Get held slots
    if session_data and session_data.get('is_super_admin'):
        holds = HeldSlot.objects.all()
    else:
        agency = _get_agency_from_request(request)
        if not agency:
            # No auth - return test slots only (for extension testing)
            holds = HeldSlot.objects.filter(slot_id__startswith='TEST')
            if holds.count() == 0:
                return Response({'slots': [], 'count': 0})
        else:
            holds = HeldSlot.objects.filter(task__agency=agency)
    
    # Filter by status
    if status_filter != 'all':
        holds = holds.filter(status=status_filter)
    
    # Order by date and limit
    holds = holds.order_by('date', 'slot_time')[:limit]
    
    # Format slots for extension
    slots = []
    for h in holds:
        # Get task and buyer profile
        task = h.task
        agency = task.agency if task else None
        buyer_profile = agency.buyer_profile if agency and hasattr(agency, 'buyer_profile') else None
        
        # Parse participants from task or buyer profile
        participants = []
        if task and task.participants_json:
            try:
                import json
                participants = json.loads(task.participants_json)
            except:
                pass
        
        # If no task participants, use buyer profile participants
        if not participants and buyer_profile and buyer_profile.participants_json:
            try:
                import json
                participants = json.loads(buyer_profile.participants_json)
            except:
                pass
        
        # If still no participants, create from buyer profile
        if not participants and buyer_profile:
            participants = [{
                'first_name': buyer_profile.first_name,
                'last_name': buyer_profile.last_name
            }] * h.visitors
        
        # Build slot data
        slot_data = {
            'id': h.id,
            'date': h.date,  # DD/MM/YYYY format
            'time': h.slot_time,  # HH:MM format
            'ticket_id': h.ticket_id,
            'ticket_name': h.ticket_name,
            'visitors': h.visitors,
            'adult_count': h.adult_count,
            'child_count': h.child_count,
            'language': getattr(task, 'language', None) if task else None,
            'status': h.status,
            'hold_started_at': h.hold_started_at.isoformat() if h.hold_started_at else None,
        }
        
        # Add profile data if available
        if buyer_profile:
            slot_data['profile'] = {
                'first_name': buyer_profile.first_name,
                'last_name': buyer_profile.last_name,
                'email': buyer_profile.email,
                'phone': buyer_profile.phone,
                'city': buyer_profile.city,
                'country': buyer_profile.country,
                'birth_date': buyer_profile.birth_date.isoformat() if buyer_profile.birth_date else None,
                'gender': buyer_profile.gender,
                'language': buyer_profile.language,
            }
            
            # Add card data if available (for auto-pay)
            if buyer_profile.card_number:
                slot_data['card'] = {
                    'number': buyer_profile.card_number,
                    'expiry': buyer_profile.card_expiry,
                    'cvv': buyer_profile.card_cvv,
                    'holder': buyer_profile.card_holder,
                }
        
        # Add participants
        slot_data['participants'] = participants[:h.visitors]  # Limit to visitor count
        
        slots.append(slot_data)
    
    return Response({
        'slots': slots,
        'count': len(slots),
        'timestamp': timezone.now().isoformat()
    })


@api_view(['POST'])
def mark_slot_paid(request):
    """Mark a held slot as paid — called by local browser agent after successful booking."""
    from .models import HeldSlot
    from .notification_utils import send_telegram_signal
    from .models import TelegramGroup

    hold_id = request.data.get('hold_id')
    reference = request.data.get('reference', '')
    epay_url = request.data.get('epay_url', '')

    if not hold_id:
        return Response({'error': 'hold_id required'}, status=400)

    try:
        held = HeldSlot.objects.get(id=hold_id)
    except HeldSlot.DoesNotExist:
        return Response({'error': 'Hold not found'}, status=404)

    held.status = 'paid'
    held.payment_url = epay_url
    held.save(update_fields=['status', 'payment_url'])

    # Notify all groups
    msg = (
        f"✅ *Ticket Booked!*\n\n"
        f"📅 {held.date} {held.slot_time}\n"
        f"👥 {held.visitors} visitors | €{held.total_price}\n"
        f"🔖 Ref: `{reference}`"
    )
    # ❌ DISABLED: payment success notifications suppressed — only slot monitoring sends to agencies
    # groups = TelegramGroup.objects.filter(agency=held.task.agency, status='approved', notification_enabled=True)
    # for g in groups:
    #     send_telegram_signal(g.chat_id, msg)

    return Response({'success': True, 'hold_id': hold_id, 'reference': reference})


@api_view(['POST'])
def mark_slot_booked(request, slot_id):
    """
    Mark a slot as booked after extension completes booking.
    Called by browser extension after successful auto-booking.
    
    Body params:
    - reference: Optional booking reference number
    - epay_url: Optional payment URL
    """
    from .models import HeldSlot
    
    try:
        slot = HeldSlot.objects.get(id=slot_id)
        
        # Update slot status
        slot.payment_ready = True
        slot.status = 'paying'
        
        # Store optional data
        reference = request.data.get('reference', '')
        epay_url = request.data.get('epay_url', '')
        
        if epay_url:
            slot.payment_url = epay_url
            slot.save(update_fields=['payment_ready', 'status', 'payment_url'])
        else:
            slot.save(update_fields=['payment_ready', 'status'])
        
        return Response({
            'success': True,
            'message': f'Slot {slot_id} marked as booked',
            'slot': {
                'id': slot.id,
                'date': slot.date,
                'time': slot.slot_time,
                'status': slot.status
            }
        })
        
    except HeldSlot.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Slot not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error marking slot as booked: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['POST'])
def sync_google_sheets(request):
    """
    Manually trigger Google Sheets sync for an agency.
    Can also be used as a webhook endpoint.
    
    Body params:
    - agency_id: ID of agency to sync (optional - syncs all if not provided)
    - agency_name: Name of agency to sync (alternative to agency_id)
    
    Returns:
    - success: boolean
    - message: status message
    - participants_count: number of participants synced
    """
    from .models import Agency
    from .tasks_google_sheets import sync_participants_for_agency, sync_participants_from_sheets
    
    try:
        agency_id = request.data.get('agency_id')
        agency_name = request.data.get('agency_name')
        
        # If specific agency requested
        if agency_id or agency_name:
            if agency_name:
                try:
                    agency = Agency.objects.get(name__iexact=agency_name, is_active=True)
                    agency_id = agency.id
                except Agency.DoesNotExist:
                    return Response({
                        'success': False,
                        'error': f'Agency "{agency_name}" not found'
                    }, status=404)
            
            # Trigger sync for specific agency
            result = sync_participants_for_agency.delay(agency_id)
            
            # Wait for result (max 10 seconds)
            try:
                sync_result = result.get(timeout=10)
                return Response(sync_result)
            except Exception as e:
                return Response({
                    'success': False,
                    'error': f'Sync task failed: {str(e)}'
                }, status=500)
        
        # Sync all agencies
        else:
            result = sync_participants_from_sheets.delay()
            
            # Wait for result (max 30 seconds)
            try:
                sync_result = result.get(timeout=30)
                return Response(sync_result)
            except Exception as e:
                return Response({
                    'success': False,
                    'error': f'Sync task failed: {str(e)}'
                }, status=500)
        
    except Exception as e:
        logger.error(f"Error triggering Google Sheets sync: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
def get_browser_trigger_group(request):
    """Return the configured browser trigger group chat_id."""
    from django.core.cache import cache
    trigger = cache.get('browser_trigger_group')
    if trigger:
        return Response(trigger)
    return Response({'chat_id': None, 'title': None})


@api_view(['POST'])
def agent_heartbeat(request):
    """Agent registers itself as online. Scoped by agency_key."""
    from django.core.cache import cache
    import time as _t
    agent_id   = request.data.get('agent_id', 'unknown')
    hostname   = request.data.get('hostname', '')
    agency_key = request.data.get('agency_key', 'default')

    # Store under agency-scoped key
    cache_key = f'online_agents_{agency_key}'
    agents = cache.get(cache_key, {})
    agents[agent_id] = {'hostname': hostname, 'last_seen': _t.time(), 'agency_key': agency_key}
    cache.set(cache_key, agents, timeout=None)

    # Register this agency_key so list_agents can find it
    known_keys = cache.get('known_agency_keys', set())
    known_keys.add(agency_key)
    cache.set('known_agency_keys', known_keys, timeout=None)

    return Response({'ok': True})


@api_view(['GET'])
def list_agents(request):
    """List agents online in the last 60s. If agency_key provided, scoped to that agency only."""
    from django.core.cache import cache
    import time as _t
    agency_key = request.query_params.get('agency_key', '')
    now = _t.time()

    if agency_key:
        # Scoped — only this agency's agents
        agents = cache.get(f'online_agents_{agency_key}', {})
        online = {k: v for k, v in agents.items() if now - v.get('last_seen', 0) < 300}
    else:
        # No key — merge legacy unscoped + all agency-scoped buckets
        all_agents = {}
        legacy = cache.get('online_agents', {})
        all_agents.update({k: v for k, v in legacy.items() if now - v.get('last_seen', 0) < 300})
        known_keys = cache.get('known_agency_keys', set()) or set()
        for key in known_keys:
            bucket = cache.get(f'online_agents_{key}', {})
            all_agents.update({k: v for k, v in bucket.items() if now - v.get('last_seen', 0) < 300})
        online = all_agents

    return Response({'agents': online})


@api_view(['GET'])
def get_browser_pending(request):
    """
    Return pending browser tasks for this agent — scoped by agency_key.
    Agent polls every 2s. Tasks are only visible to the correct agency.
    """
    from django.core.cache import cache
    agent_id   = request.query_params.get('agent_id', '')
    agency_key = request.query_params.get('agency_key', 'default')

    # 1. Agent-specific + agency-scoped queue (most targeted)
    if agent_id:
        key = f'browser_pending_{agency_key}_{agent_id}'
        targeted = cache.get(key, [])
        if targeted:
            cache.delete(key)
            return Response({'requests': targeted})

    # 2. Agency-wide queue (any agent for this agency)
    agency_key_queue = f'browser_pending_{agency_key}'
    pending = cache.get(agency_key_queue, [])
    if pending:
        cache.delete(agency_key_queue)
        return Response({'requests': pending})

    # 3. Legacy fallback (for older bots)
    legacy = cache.get('browser_pending', [])
    if legacy:
        cache.delete('browser_pending')
        return Response({'requests': legacy})

    return Response({'requests': []})


@api_view(['GET'])
def get_agent_config(request):
    """Return runtime config for the local agent (poll interval, etc.)."""
    from django.core.cache import cache
    config = cache.get('agent_config', {})
    return Response({
        'poll_interval': config.get('poll_interval', 2),
        'agent_id': config.get('agent_id', ''),
    })


@api_view(['POST'])
def set_agent_config(request):
    """Admin endpoint to update agent runtime config."""
    from django.core.cache import cache
    config = cache.get('agent_config', {})
    if 'poll_interval' in request.data:
        try:
            config['poll_interval'] = float(request.data['poll_interval'])
        except (ValueError, TypeError):
            pass
    cache.set('agent_config', config, timeout=None)
    return Response({'success': True, 'config': config})


@api_view(['POST'])
def remote_snipe(request):
    """
    Called by Android/remote agents to complete a full reservation server-side.
    The agent does: hold (recap) → calls this endpoint → gets epay URL back.
    
    This endpoint:
    1. Solves Turnstile via 2captcha (~30s)
    2. Calls /api/visit/reservation with the token
    3. Returns the epay URL to the agent
    
    Body: { hold_id: int }
    """
    from .models import HeldSlot, BuyerProfile
    from .epay_ssl import make_vatican_session
    from .turnstile_pool import get_token_sync
    import json as _json

    hold_id = request.data.get('hold_id')
    if not hold_id:
        return Response({'error': 'hold_id required'}, status=400)

    try:
        held = HeldSlot.objects.get(id=hold_id)
    except HeldSlot.DoesNotExist:
        return Response({'error': 'Hold not found'}, status=404)

    try:
        profile = BuyerProfile.objects.get(agency=held.task.agency)
    except BuyerProfile.DoesNotExist:
        return Response({'error': 'No buyer profile'}, status=400)

    # Solve Turnstile (~30s)
    token = get_token_sync()
    if not token:
        return Response({'error': 'Could not solve Turnstile — check 2captcha balance'}, status=503)

    # Restore session with held slot's cookies
    notes = {}
    try:
        notes = _json.loads(held.notes or '{}')
    except Exception:
        pass

    s = make_vatican_session(
        jsessionid=held.jsessionid,
        ticketmv=held.ticketmv,
        serverid=notes.get('serverid', '')
    )

    # Build participant list
    participants = []
    try:
        task_parts = _json.loads(held.task.participants_json or '[]')
        for p in task_parts[:held.visitors]:
            participants.append({
                "surname": p.get('last_name', profile.last_name),
                "name": p.get('first_name', profile.first_name),
                "id": 60, "ticketType": "intero", "services": [58]
            })
    except Exception:
        pass
    while len(participants) < held.visitors:
        participants.append({
            "surname": profile.last_name, "name": profile.first_name,
            "id": 60, "ticketType": "intero", "services": [58]
        })

    BASE_V = 'https://tickets.museivaticani.va'
    res_body = {
        "recaptcha": token,
        "lang": "it",
        "recapId": held.recap_id,
        "visitorNum": held.visitors,
        "visitId": str(held.slot_id),
        "visitTypeId": int(held.ticket_id),
        "tickets": [
            {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(held.adult_count)},
            {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": str(held.child_count)},
        ],
        "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": held.visitors}],
        "representativeUser": profile.to_representative_user(),
        "participantUser": participants,
        "gdpr": [{"id": 1, "check": True}, {"id": 3, "check": False}],
    }

    HC = {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': f'{BASE_V}/home/checkout',
        'Origin': BASE_V,
    }

    try:
        r = s.post(f'{BASE_V}/api/visit/reservation', json=res_body, headers=HC, timeout=20, allow_redirects=False)
        if r.status_code == 200:
            data = r.json()
            epay = data.get('epay', {})
            epay_url = epay.get('url', '')
            reference = data.get('referenceOrder', '')
            held.status = 'paying'
            held.payment_url = epay_url
            held.save(update_fields=['status', 'payment_url'])
            return Response({
                'success': True,
                'epay_url': epay_url,
                'reference': reference,
                'total': data.get('total'),
            })
        else:
            return Response({'error': f'Reservation failed: {r.status_code}', 'body': r.text[:300]}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=500)
    """
    Pause keepalive for a specific hold — called by local agent before clicking BUY.
    Prevents the Celery keepalive from sending a recap while the browser is mid-checkout.
    """
    from django.core.cache import cache
    from .models import HeldSlot
    try:
        hold = HeldSlot.objects.get(id=hold_id)
    except HeldSlot.DoesNotExist:
        return Response({'error': 'Hold not found'}, status=404)
    # Pause for 15 minutes — enough time to complete checkout
    cache.set(f'hold_recap_paused:{hold_id}', True, timeout=900)
    hold.status = 'paying'
    hold.save(update_fields=['status'])
    return Response({'success': True, 'hold_id': hold_id, 'paused_for_seconds': 900})


@api_view(['POST'])
def pause_hold_recap(request, hold_id):
    """Pause keepalive for a specific hold — called by local agent before clicking BUY."""
    from django.core.cache import cache
    from .models import HeldSlot
    try:
        hold = HeldSlot.objects.get(id=hold_id)
    except HeldSlot.DoesNotExist:
        return Response({'error': 'Hold not found'}, status=404)
    cache.set(f'hold_recap_paused:{hold_id}', True, timeout=900)
    hold.status = 'paying'
    hold.save(update_fields=['status'])
    return Response({'success': True, 'hold_id': hold_id, 'paused_for_seconds': 900})


@api_view(['POST'])
def resume_hold_recap(request, hold_id):
    """Resume keepalive for a hold (e.g. if checkout failed)."""
    from django.core.cache import cache
    from .models import HeldSlot
    try:
        hold = HeldSlot.objects.get(id=hold_id)
    except HeldSlot.DoesNotExist:
        return Response({'error': 'Hold not found'}, status=404)
    cache.delete(f'hold_recap_paused:{hold_id}')
    if hold.status == 'paying':
        hold.status = 'held'
        hold.save(update_fields=['status'])
    return Response({'success': True, 'hold_id': hold_id})


@api_view(['GET'])
def get_buyer_profile(request):
    """Return the first active buyer profile — used by local browser agent."""
    from .models import BuyerProfile, Agency
    try:
        agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
        if not agency:
            return Response({})
        profile = BuyerProfile.objects.filter(agency=agency).first()
        if not profile:
            return Response({})
        bd = None
        if profile.birth_date:
            month_abbr = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'][profile.birth_date.month-1]
            bd = {'year': profile.birth_date.year, 'month': month_abbr, 'day': profile.birth_date.day}
        return Response({
            'first_name': profile.first_name,
            'last_name': profile.last_name,
            'email': profile.email,
            'phone': profile.phone,
            'city': profile.city,
            'country': profile.country,
            'gender': profile.gender,
            'birth_date': bd,
            'language': profile.language,
        })
    except Exception as e:
        return Response({'error': str(e)})


@api_view(['GET'])
def get_buyer_card(request):
    """Return the card details for the first active agency — used for auto-pay."""
    from .models import BuyerProfile, Agency
    try:
        agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
        if not agency:
            return Response({'error': 'No active agency found'}, status=404)
        profile = BuyerProfile.objects.filter(agency=agency).first()
        if not profile or not profile.card_number:
            return Response({'error': 'No card details found'}, status=404)
            
        return Response({
            'card_number': profile.card_number,
            'card_expiry': profile.card_expiry or '', # MM/YY
            'card_cvv': profile.card_cvv or '',
            'card_holder': profile.card_holder or f"{profile.first_name} {profile.last_name}",
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
def release_held_slot(request, hold_id):
    """Release a held slot."""
    from .models import HeldSlot
    from .hold_manager import release_slot
    agency = _get_agency_from_request(request)
    if not agency:
        return Response({'error': 'Not authenticated'}, status=401)

    try:
        hold = HeldSlot.objects.get(id=hold_id, task__agency=agency)
        release_slot(hold)
        return Response({'success': True, 'message': f'Hold #{hold_id} released'})
    except HeldSlot.DoesNotExist:
        return Response({'error': 'Hold not found'}, status=404)


@api_view(['POST'])
def inject_dynamic_details(request, task_id):
    """
    Inject dynamic participant/card details for immediate hold/snipe.
    
    Payload:
    {
      "participants": [
        {"first_name": "John", "last_name": "Doe"},
        {"first_name": "Jane", "last_name": "Smith"}
      ],
      "card": {
        "number": "4111111111111111",
        "expiry": "12/2026",
        "cvv": "123",
        "holder": "John Doe"
      },
      "action": "epay"  // or "snipe"
    }
    """
    from .models import MonitorTask, DynamicInjectionConfig, BuyerProfile
    from django.utils import timezone
    from datetime import timedelta
    
    agency = _get_agency_from_request(request)
    if not agency:
        return Response({'error': 'Not authenticated'}, status=401)
    
    try:
        task = MonitorTask.objects.get(id=task_id, agency=agency)
        profile = BuyerProfile.objects.get(agency=agency)
        
        # Parse injection data
        participants = request.data.get('participants', [])
        card_details = request.data.get('card', {})
        action = request.data.get('action', 'epay')
        
        # Validate action
        if action not in ['epay', 'snipe']:
            return Response({'error': 'Action must be "epay" or "snipe"'}, status=400)
        
        # Validate participants
        if not participants:
            return Response({'error': 'At least one participant required'}, status=400)
        
        # Create injection configuration (valid for 30 minutes)
        config = DynamicInjectionConfig.objects.create(
            task=task,
            buyer_profile=profile,
            participant_overrides=participants,
            card_overrides=card_details,
            action=action,
            expires_at=timezone.now() + timedelta(minutes=30)
        )
        
        return Response({
            'status': 'injection_ready',
            'config_id': config.id,
            'action': config.action,
            'expires_at': config.expires_at.isoformat(),
            'message': f'Dynamic injection configured. Will be used for next available slot.'
        })
        
    except MonitorTask.DoesNotExist:
        return Response({'error': 'Task not found'}, status=404)
    except BuyerProfile.DoesNotExist:
        return Response({'error': 'Buyer profile not configured for this agency'}, status=400)


@api_view(['POST'])
def generate_realtime_epay(request):
    """
    Generate real-time epay link using random profiles and participant info.
    Checks slot availability first, then creates epay link with randomized details.
    
    Payload:
    {
      "date": "2026-06-15",
      "time": "10:00", 
      "visitors": 2,
      "agency_id": 1  // optional - uses random if not provided
    }
    """
    from .models import Agency, BuyerProfile
    from .hold_manager_enhanced import hold_with_dynamic_injection_error_free
    from .tasks_search_api import search_slots
    from django.utils import timezone
    import random
    import json
    
    try:
        # Parse request data
        date = request.data.get('date')
        time_slot = request.data.get('time')
        visitors = request.data.get('visitors', 2)
        agency_id = request.data.get('agency_id')
        
        if not date or not time_slot:
            return Response({'error': 'Date and time are required'}, status=400)
        
        # Get or create random agency profile
        if agency_id:
            agency = Agency.objects.get(id=agency_id)
        else:
            # Use first agency or create a temporary one
            agency = Agency.objects.first()
            if not agency:
                agency = Agency.objects.create(
                    name=f"TempAgency-{random.randint(1000, 9999)}",
                    slug=f"temp-agency-{random.randint(1000, 9999)}"
                )
        
        # Generate random representative profile
        full_name = _generate_random_name()
        first_name, last_name = full_name.split(' ', 1)
        
        # Create or get buyer profile with enhanced random data
        profile, created = BuyerProfile.objects.get_or_create(
            agency=agency,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'email': _generate_random_email(first_name, last_name),
                'phone': _generate_random_phone(),
                'country': 'Italy',
                'city': _generate_random_city(),
                'gender': random.choice(['M', 'F']),
                'language': 'it',
                'birth_date': timezone.now().date() - timezone.timedelta(days=random.randint(7300, 14600))  # 20-40 years old
            }
        )
        
        # Generate random participants with realistic data
        random_participants = []
        for i in range(visitors):
            participant_name = _generate_random_name()
            p_first_name, p_last_name = participant_name.split(' ', 1)
            random_participants.append({
                'first_name': p_first_name,
                'last_name': p_last_name,
                'email': _generate_random_email(p_first_name, p_last_name),
                'phone': _generate_random_phone()
            })
        
        # Create temporary monitor task for this request
        from .models import MonitorTask
        temp_task = MonitorTask.objects.create(
            agency=agency,
            site='vatican',
            area_name='Musei Vaticani',
            dates=json.dumps([date]),
            preferred_times=json.dumps([time_slot]),
            visitors=visitors,
            adult_count=visitors,
            child_count=0,
            ticket_type=0,
            ticket_label='Biglietto Intero',
            check_interval=60,
            tier='notify',
            match_strategy='any',
            notification_mode='any_change',
            is_active=True
        )
        
        # Search for available slots
        available_slots = search_slots(temp_task)
        
        # Find the specific slot requested
        target_slot = None
        for slot in available_slots:
            if (slot.get('date') == date and 
                slot.get('time') == time_slot and 
                slot.get('availability') != 'SOLD_OUT'):
                target_slot = slot
                break
        
        if not target_slot:
            temp_task.delete()
            return Response({
                'status': 'no_slots',
                'message': f'No available slots found for {date} {time_slot}'
            }, status=404)
        
        # Create injection config
        from .models import DynamicInjectionConfig
        injection_config = DynamicInjectionConfig.objects.create(
            task=temp_task,
            buyer_profile=profile,
            participant_overrides=random_participants,
            card_overrides={},  # Empty for epay URL generation
            action='epay',
            expires_at=timezone.now() + timezone.timedelta(minutes=30)
        )
        
        # Hold slot with dynamic injection using error-free handler
        held_slot = hold_with_dynamic_injection_error_free(temp_task, target_slot, injection_config)
        
        if not held_slot:
            temp_task.delete()
            return Response({
                'status': 'hold_failed',
                'message': 'Failed to hold the slot'
            }, status=500)
        
        # Return the epay URL
        return Response({
            'status': 'success',
            'epay_url': held_slot.payment_url,
            'hold_id': held_slot.id,
            'slot_date': date,
            'slot_time': time_slot,
            'visitors': visitors,
            'participants': random_participants,
            'expires_at': injection_config.expires_at.isoformat(),
            'message': 'Epay link generated successfully with random profiles'
        })
        
    except Exception as e:
        return Response({
            'status': 'error',
            'message': f'Failed to generate epay link: {str(e)}'
        }, status=500)


@api_view(['GET'])
def generate_test_profiles(request):
    """
    Generate random test profiles for bot testing
    Query params: count=5, visitors=2
    Returns JSON data only - doesn't save to database
    """
    count = int(request.GET.get('count', 5))
    visitors = int(request.GET.get('visitors', 2))
    
    if count > 50:
        return Response({'error': 'Maximum 50 profiles per request'}, status=400)
    
    test_profiles = []
    for i in range(count):
        test_profiles.append(generate_test_profile(visitors))
    
    return Response({
        'status': 'success',
        'count': count,
        'visitors_per_profile': visitors,
        'profiles': test_profiles,
        'message': f'Generated {count} test profiles with {visitors} visitors each'
    })


def _generate_random_name():
    """Generate a random Italian-sounding name"""
    first_names_male = ['Marco', 'Alessandro', 'Luca', 'Matteo', 'Andrea', 'Giovanni', 
                       'Francesco', 'Antonio', 'Stefano', 'Riccardo', 'Davide', 'Federico',
                       'Gabriele', 'Simone', 'Lorenzo', 'Paolo', 'Michele', 'Gianluca',
                       'Massimo', 'Roberto', 'Enrico', 'Fabio', 'Daniele', 'Christian']
    
    first_names_female = ['Giulia', 'Sofia', 'Aurora', 'Chiara', 'Martina', 'Giorgia',
                         'Francesca', 'Alessia', 'Valentina', 'Elena', 'Sara', 'Elisa',
                         'Veronica', 'Laura', 'Silvia', 'Monica', 'Anna', 'Maria',
                         'Cristina', 'Eleonora', 'Beatrice', 'Federica', 'Camilla', 'Noemi']
    
    last_names = ['Rossi', 'Bianchi', 'Romano', 'Colombo', 'Ricci', 'Marino', 'Greco',
                 'Conti', 'Gallo', 'Ferrari', 'Russo', 'Lombardi', 'Moretti', 'Barbieri',
                 'Fontana', 'Santoro', 'Mariani', 'Rinaldi', 'Gatti', 'Caruso', 'Ferri',
                 'Leone', 'Longo', 'Gentile', 'Martinelli', 'Vitale', 'Lombardo', 'De Luca']
    
    gender = random.choice(['male', 'female'])
    if gender == 'male':
        first_name = random.choice(first_names_male)
    else:
        first_name = random.choice(first_names_female)
    
    return f"{first_name} {random.choice(last_names)}"

def _generate_random_email(first_name, last_name):
    """Generate a realistic email address"""
    domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'libero.it', 'virgilio.it']
    formats = [
        f"{first_name.lower()}.{last_name.lower()}",
        f"{first_name.lower()}{last_name.lower()}",
        f"{first_name.lower()}_{last_name.lower()}",
        f"{first_name[0].lower()}{last_name.lower()}",
        f"{first_name.lower()}{random.randint(10, 99)}"
    ]
    return f"{random.choice(formats)}@{random.choice(domains)}"

def _generate_random_phone():
    """Generate a random Italian phone number"""
    prefixes = ['320', '327', '328', '329', '333', '334', '335', '336', '337', '338', '339',
               '340', '347', '348', '349', '350', '351', '360', '366', '368', '370', '380',
               '388', '389', '390', '391', '392', '393']
    return f"+39{random.choice(prefixes)}{random.randint(100000, 999999)}"

def _generate_random_city():
    """Generate a random Italian city"""
    cities = ['Roma', 'Milano', 'Napoli', 'Torino', 'Palermo', 'Genova', 'Bologna', 'Firenze',
             'Bari', 'Catania', 'Venezia', 'Verona', 'Messina', 'Padova', 'Trieste', 'Brescia',
             'Taranto', 'Prato', 'Modena', 'Reggio Calabria', 'Reggio Emilia', 'Perugia',
             'Livorno', 'Ravenna', 'Cagliari', 'Foggia', 'Rimini', 'Salerno', 'Ferrara']
    return random.choice(cities)


def generate_test_profile(visitors=2):
    """
    Generate a complete test profile with representative and participants
    Returns data only - doesn't save to database
    """
    from django.utils import timezone
    
    # Generate representative profile
    full_name = _generate_random_name()
    first_name, last_name = full_name.split(' ', 1)
    
    representative = {
        'first_name': first_name,
        'last_name': last_name,
        'email': _generate_random_email(first_name, last_name),
        'phone': _generate_random_phone(),
        'country': 'Italy',
        'city': _generate_random_city(),
        'gender': random.choice(['M', 'F']),
        'language': 'it',
        'birth_date': (timezone.now().date() - timezone.timedelta(days=random.randint(7300, 14600))).isoformat()
    }
    
    # Generate participants
    participants = []
    for i in range(visitors):
        participant_name = _generate_random_name()
        p_first_name, p_last_name = participant_name.split(' ', 1)
        participants.append({
            'first_name': p_first_name,
            'last_name': p_last_name,
            'email': _generate_random_email(p_first_name, p_last_name),
            'phone': _generate_random_phone()
        })
    
    return {
        'representative': representative,
        'participants': participants,
        'visitors': visitors
    }


def _get_agency_from_request(request):
    """Helper to get agency from session or query params."""
    from .models import Agency
    
    # First check query parameters (for extension API calls)
    agency_id = request.GET.get('agency_id')
    if agency_id:
        try:
            return Agency.objects.filter(id=int(agency_id)).first()
        except (ValueError, TypeError):
            pass
    
    # Then check session (for web interface)
    agency_id = request.session.get('agency_id')
    if agency_id:
        return Agency.objects.filter(id=agency_id).first()
    
    return None


from django.http import HttpResponse, StreamingHttpResponse
import requests as req_lib
import os
from django.views.decorators.csrf import csrf_exempt

VATICAN_BASE = 'https://tickets.museivaticani.va'

@csrf_exempt
def checkout_redirect(request, hold_id):
    """
    Two modes:
    - GET  → show hold details page with "Get Payment Link" button
    - POST → call Vatican /api/visit/reservation server-side, return epay URL
    
    Also handles direct epay link access with query parameters.
    """
    from .models import HeldSlot, BuyerProfile
    from django.http import JsonResponse

    try:
        hold = HeldSlot.objects.select_related('task__agency').get(id=hold_id, status='held')
    except HeldSlot.DoesNotExist:
        return HttpResponse(_error_page("Hold not found or already expired."),
                           status=404, content_type='text/html')

    # Handle direct epay link generation with token in query params
    turnstile_token = request.GET.get('token') or request.GET.get('recaptcha')
    if turnstile_token and request.method == 'GET':
        # Convert GET with token to internal POST
        from django.http import QueryDict
        post_data = QueryDict(mutable=True)
        post_data['recaptcha'] = turnstile_token
        request.method = 'POST'
        request._body = post_data.urlencode().encode('utf-8')
        return _do_reservation(request, hold)

    if request.method == 'POST':
        return _do_reservation(request, hold)

    # GET — show the hold details page
    agency = hold.task.agency
    has_profile = BuyerProfile.objects.filter(agency=agency).exists()

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Vatican Checkout — {hold.date} {hold.slot_time}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,sans-serif;background:#0a0a0a;color:#fff;
         min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}}
    .card{{background:#111;border:1px solid #222;border-radius:20px;padding:32px;max-width:480px;width:100%}}
    .badge{{display:inline-block;background:#00E37C20;color:#00E37C;border:1px solid #00E37C40;
            border-radius:20px;padding:4px 12px;font-size:12px;font-weight:600;margin-bottom:20px}}
    h2{{font-size:22px;font-weight:700;margin-bottom:8px}}
    .meta{{color:#666;font-size:14px;margin-bottom:28px}}
    .row{{display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid #1a1a1a;font-size:14px}}
    .row:last-of-type{{border-bottom:none}}
    .label{{color:#666}}.value{{color:#fff;font-weight:500}}
    .total{{color:#00E37C;font-size:18px;font-weight:700}}
    .btn{{display:block;width:100%;margin-top:28px;padding:16px;background:#00E37C;color:#000;
          border:none;border-radius:14px;font-size:16px;font-weight:700;cursor:pointer;transition:opacity .2s}}
    .btn:hover{{opacity:.9}}.btn:disabled{{opacity:.5;cursor:not-allowed}}
    .btn-secondary{{background:#1a1a1a;color:#888;border:1px solid #262626;margin-top:12px}}
    .warn{{margin-top:16px;padding:12px;background:#ff4d4d15;border:1px solid #ff4d4d30;
           border-radius:10px;font-size:13px;color:#ff4d4d}}
    .info{{margin-top:16px;padding:12px;background:#00E37C10;border:1px solid #00E37C30;
           border-radius:10px;font-size:13px;color:#00E37C}}
    #result{{margin-top:20px;display:none}}
    .pay-link{{display:block;margin-top:12px;padding:16px;background:#00E37C;color:#000;
               border-radius:14px;font-size:15px;font-weight:700;text-align:center;text-decoration:none}}
    .spinner{{display:inline-block;width:16px;height:16px;border:2px solid #000;
              border-top-color:transparent;border-radius:50%;animation:spin .6s linear infinite;vertical-align:middle;margin-right:8px}}
    @keyframes spin{{to{{transform:rotate(360deg)}}}}
  </style>
</head>
<body>
<div class="card">
  <div class="badge">🔒 SLOT HELD</div>
  <h2>Vatican Checkout</h2>
  <p class="meta">Hold #{hold.id} &bull; Agency: {agency.name}</p>

  <div class="row"><span class="label">Date</span><span class="value">{hold.date}</span></div>
  <div class="row"><span class="label">Time</span><span class="value">{hold.slot_time}</span></div>
  <div class="row"><span class="label">Visitors</span><span class="value">{hold.visitors}</span></div>
  <div class="row"><span class="label">Total</span><span class="value total">&euro;{hold.total_price}</span></div>

  {'<div class="warn">⚠️ No buyer profile set. <a href="#" style="color:#ff4d4d">Set profile</a> to generate payment link.</div>' if not has_profile else ''}

  <div style="margin-top:20px">
    <label style="font-size:12px;color:#666;display:block;margin-bottom:6px">
      Turnstile Token (required — paste from browser DevTools)
    </label>
    <textarea id="recaptchaToken" placeholder="Paste Turnstile token here..."
      style="width:100%;background:#1a1a1a;border:1px solid #262626;border-radius:10px;
             padding:10px;color:#fff;font-size:11px;font-family:monospace;resize:vertical;
             min-height:60px;outline:none"></textarea>
    <p style="font-size:11px;color:#444;margin-top:4px">
      To get token: open Vatican site → DevTools → Network → filter "reservation" → copy recaptcha value
    </p>
    <p style="font-size:11px;color:#444;margin-top:6px">
      Payment link expires in ~10 minutes. Click generate again to regenerate.
    </p>
  </div>

  <button class="btn" id="payBtn" onclick="getPaymentLink()" {'disabled' if not has_profile else ''}>
    💳 Generate Payment Link
  </button>

  <div id="result"></div>
  <p style="margin-top:16px;font-size:12px;color:#444;text-align:center">
    ⚠️ Single-use link. Do not share until ready to pay.
  </p>
</div>

<script>
async function getPaymentLink() {{
  var btn = document.getElementById('payBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Generating...';

  try {{
    var resp = await fetch(window.location.href, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')}},
      body: JSON.stringify({{recaptcha: document.getElementById('recaptchaToken').value.trim()}})
    }});
    var data = await resp.json();

    var result = document.getElementById('result');
    if (data.payment_url) {{
      result.innerHTML = '<div class="info">✅ Reservation confirmed! Payment page opens in new tab.</div>' +
        '<a class="pay-link" href="' + data.payment_url + '" target="_blank">💳 Pay Now — epay.catholica.va</a>' +
        '<p style="font-size:11px;color:#555;margin-top:8px">Expires in ~10 minutes. Open it in any browser/device.</p>';
      result.style.display = 'block';
      window.open(data.payment_url, '_blank');
      btn.innerHTML = '✅ Payment Link Ready';
    }} else {{
      result.innerHTML = '<div class="warn">❌ ' + (data.error || 'Failed to generate link') + '</div>';
      result.style.display = 'block';
      btn.disabled = false;
      btn.innerHTML = '💳 Generate Payment Link';
    }}
  }} catch(e) {{
    document.getElementById('result').innerHTML = '<div class="warn">❌ Network error: ' + e.message + '</div>';
    document.getElementById('result').style.display = 'block';
    btn.disabled = false;
    btn.innerHTML = '💳 Generate Payment Link';
  }}
}}

function getCookie(name) {{
  var v = document.cookie.match('(^|;) ?' + name + '=([^;]*)(;|$)');
  return v ? v[2] : '';
}}
</script>
</body>
</html>"""

    return HttpResponse(html, content_type='text/html')


def _do_reservation(request, held):
    """
    Call Vatican /api/visit/reservation server-side using held JSESSIONID.
    Vatican uses Cloudflare Turnstile (sitekey: 0x4AAAAAAB2Edz1zEK7o5Rj1).
    After success, Vatican redirects to epay.catholica.va — that's the payment URL.
    If session expired, re-holds the slot first with a fresh session.
    """
    import json as _json, re
    from django.http import JsonResponse
    from .models import BuyerProfile

    try:
        profile = BuyerProfile.objects.get(agency=held.task.agency)
    except BuyerProfile.DoesNotExist:
        return JsonResponse({'error': 'No buyer profile set for this agency'}, status=400)

    try:
        req_body = _json.loads(request.body or '{}')
    except Exception:
        req_body = {}
    turnstile_token = (req_body.get('recaptcha', '') or '').strip()
    if not turnstile_token:
        return JsonResponse({
            'error': 'Missing Turnstile token (recaptcha). Open Vatican checkout in a real browser and paste the token.',
        }, status=400)

    # Step 0: Check session freshness and proactively re-hold if needed
    from .hold_manager import _get_services, _build_recap_body, _fresh_re_hold
    from django.utils import timezone
    
    # Check if session is stale (more than 10 minutes since last keepalive or recap is old)
    session_is_stale = False
    if held.last_keepalive_at:
        minutes_since_keepalive = (timezone.now() - held.last_keepalive_at).total_seconds() / 60
        if minutes_since_keepalive > 10:
            session_is_stale = True
            logger.warning(f"Session stale for HeldSlot #{held.id}: {minutes_since_keepalive:.1f} min since keepalive")
    
    # Proactively re-hold if session is stale before attempting epay generation
    if session_is_stale:
        logger.info(f"Proactively re-holding stale session for HeldSlot #{held.id}")
        if _fresh_re_hold(held):
            logger.info(f"Successfully re-held HeldSlot #{held.id} for epay generation")
        else:
            return JsonResponse({
                'error': 'Session expired — slot needs to be re-held. The sweep will pick it up automatically within 30 seconds if still available.',
                'expired': True,
            }, status=400)

    # Create session with current credentials
    s = req_lib.Session()
    s.cookies.set('JSESSIONID', held.jsessionid, domain='tickets.museivaticani.va')
    if held.ticketmv:
        s.cookies.set('ticketmv', held.ticketmv, domain='tickets.museivaticani.va')
    try:
        serverid = (_json.loads(held.notes or '{}') or {}).get('serverid')
    except Exception:
        serverid = None
    if serverid:
        s.cookies.set('SERVERID', serverid, domain='tickets.museivaticani.va')

    services = _get_services(s, held.slot_id, int(held.ticket_id), held.visitors)

    recap_headers = {
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': f'{VATICAN_BASE}/',
        'Origin': VATICAN_BASE,
        'Content-Type': 'application/json',
    }

    recap_body = _build_recap_body(held.slot_id, int(held.ticket_id), held.visitors, services)

    recap_r = s.post(f'{VATICAN_BASE}/api/visit/recap', json=recap_body, headers=recap_headers, timeout=15)
    if recap_r.status_code == 200:
        new_recap_id = recap_r.json().get('recapId', '') or recap_r.json().get('id', '')
        if new_recap_id:
            held.recap_id = new_recap_id
            held.save(update_fields=['recap_id'])
    elif recap_r.status_code == 500 and 'scaduta' in recap_r.text.lower():
        # Session fully expired — need fresh hold
        return JsonResponse({
            'error': 'Session expired — slot needs to be re-held. The sweep will pick it up automatically within 30 seconds if still available.',
            'expired': True,
        }, status=400)
    else:
        return JsonResponse({
            'error': f'Recap failed ({recap_r.status_code})',
            'raw': recap_r.text[:400],
        }, status=400)

    service_ids = []
    if services:
        svc_id = services[0].get('id')
        if svc_id is not None:
            service_ids = [svc_id]

    participants = profile.to_participant_list(held.visitors, ticket_id=60, service_ids=service_ids)
    if not held.recap_id:
        return JsonResponse({'error': 'Missing recapId after recap refresh'}, status=400)

    reservation_services = []
    if services:
        s0 = services[0]
        reservation_services = [{
            "id": s0.get("id", 58),
            "name": s0.get("name", "Diritti di Prevendita"),
            "price": s0.get("price", 5),
            "quantity": held.visitors,
        }]

    body = {
        "recaptcha": turnstile_token,
        "lang": "it",
        "recapId": held.recap_id or '',
        "visitorNum": held.visitors,
        "visitId": held.slot_id,
        "visitTypeId": int(held.ticket_id),
        "tickets": [
            {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(held.adult_count)},
            {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": str(held.child_count)},
        ],
        "services": reservation_services,
        "representativeUser": profile.to_representative_user(),
        "participantUser": participants,
        "gdpr": [{"id": 1, "check": True}, {"id": 3, "check": False}],
    }

    headers = {
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        'Referer': f'{VATICAN_BASE}/home/checkout',
        'Origin': VATICAN_BASE,
        'Content-Type': 'application/json',
        'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Linux"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
    }

    s = req_lib.Session()
    s.cookies.set('JSESSIONID', held.jsessionid, domain='tickets.museivaticani.va')
    if held.ticketmv:
        s.cookies.set('ticketmv', held.ticketmv, domain='tickets.museivaticani.va')
    if serverid:
        s.cookies.set('SERVERID', serverid, domain='tickets.museivaticani.va')

    try:
        r = s.post(
            f'{VATICAN_BASE}/api/visit/reservation',
            json=body, headers=headers, timeout=20,
            allow_redirects=False  # catch the redirect manually
        )

        # Vatican returns 302 redirect to epay on success
        if r.status_code in (200, 302):
            payment_url = ''

            # Check Location header (302 redirect)
            if r.status_code == 302:
                payment_url = r.headers.get('Location', '')

            # Check response body for epay URL
            if not payment_url:
                match = re.search(r'https://epay\.catholica\.va[^\s"\'\\]+', r.text)
                if match:
                    payment_url = match.group(0)

            # Check JSON keys
            if not payment_url:
                try:
                    data = r.json()
                    # Vatican response format: {"total":"2500","referenceOrder":"...","epay":{"url":"https://epay.catholica.va/...",...}}
                    epay = data.get('epay', {})
                    payment_url = (
                        epay.get('url') or
                        data.get('redirectUrl') or
                        data.get('paymentUrl') or
                        data.get('url') or
                        ''
                    )
                    # Build full epay URL if we have the components
                    if not payment_url:
                        siv_id = data.get('sivTransactionId') or data.get('transactionId')
                        mac = data.get('uppRedirectMac') or data.get('mac')
                        if siv_id and mac:
                            payment_url = f"https://epay.catholica.va/pay/public/init/{siv_id}/{mac}/it"
                except Exception:
                    pass

            if payment_url:
                try:
                    from django.utils import timezone
                    import json as _json2
                    notes = _json2.loads(held.notes or '{}')
                    if not isinstance(notes, dict):
                        notes = {}
                except Exception:
                    notes = {}
                try:
                    notes['payment_generated_at'] = timezone.now().isoformat()
                except Exception:
                    pass
                try:
                    held.notes = _json.dumps(notes) if notes else None
                except Exception:
                    pass
                held.status = 'paying'
                held.payment_url = payment_url
                held.save(update_fields=['status', 'payment_url', 'notes'])
                return JsonResponse({'payment_url': payment_url, 'recap_id': held.recap_id})
            else:
                return JsonResponse({
                    'error': 'Reservation succeeded but no payment URL found',
                    'raw': r.text[:500],
                    'status': r.status_code,
                    'headers': dict(r.headers),
                })
        else:
            err_msg = ''
            try:
                err_msg = r.json().get('message', r.text[:200])
            except Exception:
                err_msg = r.text[:200]
            return JsonResponse({
                'error': f'Reservation failed ({r.status_code}): {err_msg}',
            }, status=400)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _error_page(msg):
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Error</title>
<style>body{{font-family:sans-serif;background:#111;color:#fff;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0;flex-direction:column;gap:12px;}}
h2{{color:#ff4d4d;}}p{{color:#888;}}</style></head>
<body><h2>⚠️ {msg}</h2><p>The hold session may have expired.</p></body></html>"""


@api_view(['POST'])
def create_test_slot(request):
    """
    Create a test held slot for extension testing.
    This checks Vatican's REAL availability first and only creates a slot if something is actually available.
    Only searches for Vatican Museums general entry tickets or guided tours (not special tickets).
    """
    from .models import HeldSlot, MonitorTask, Agency
    from django.utils import timezone
    import requests
    from datetime import datetime, timedelta
    
    # Delete any existing test slots first
    HeldSlot.objects.filter(slot_id__startswith='TEST').delete()
    
    # Get parameters from request
    visitors = request.data.get('visitors', 1)
    ticket_type = request.data.get('ticket_type', 0)  # 0=standard, 1=guided
    language = request.data.get('language', 'ENG') if ticket_type == 1 else None
    
    # Check next 90 days for availability (Vatican opens tickets 2-3 months in advance)
    today = datetime.now()
    available_slot = None
    
    logger.info(f"🔍 Searching for Vatican Museums tickets in next 90 days (visitors={visitors}, ticket_type={ticket_type})")
    
    # Exclusion list - same as bot
    EXCLUDED_KEYWORDS = ['pellegrinaggi', 'lunch', 'pranzo', 'gruppi', 'specola', 'palazzo', 'didattiche', 'scuole', 'giardini']
    
    # Check every 7 days to speed up search (day 7, 14, 21, 28, etc.)
    # If we find availability, we'll narrow down to find the earliest slot
    days_to_check = list(range(7, 91, 7))  # Check weeks: 7, 14, 21, ..., 84
    
    for days_ahead in days_to_check:  # Check next 90 days (every 7 days)
        check_date = today + timedelta(days=days_ahead)
        date_str = check_date.strftime('%d/%m/%Y')
        
        try:
            # Step 1: Call Search API to get ticket IDs
            search_url = "https://tickets.museivaticani.va/api/search/resultPerTag"
            tag = "MV-Visite-Guidate" if ticket_type == 1 else "MV-Biglietti"
            
            search_params = {
                'lang': 'it',
                'visitorNum': str(visitors),
                'visitDate': date_str,
                'area': '1',
                'who': '',
                'page': '0',
                'tag': tag
            }
            
            search_response = requests.get(search_url, params=search_params, timeout=10)
            if search_response.status_code != 200:
                continue
                
            search_data = search_response.json()
            visits = search_data.get('visits', [])
            
            if not visits:
                continue
            
            # Find Vatican Museums general entry ticket (filter out special tickets)
            target_ticket = None
            for visit in visits:
                if visit.get('availability') != 'AVAILABLE':
                    continue
                
                name_lower = visit.get('name', '').lower()
                
                # Skip excluded tickets
                if any(excluded in name_lower for excluded in EXCLUDED_KEYWORDS):
                    logger.debug(f"Skipping excluded ticket: {visit.get('name')}")
                    continue
                
                # For standard tickets: look for "Musei Vaticani" + "Biglietti d'ingresso"
                if ticket_type == 0:
                    if 'musei vaticani' in name_lower and 'bigliett' in name_lower and 'ingresso' in name_lower:
                        target_ticket = visit
                        logger.info(f"✅ Found Vatican Museums ticket: {visit.get('name')}")
                        break
                # For guided tours: look for "Visita Guidata" or "Guided Tour"
                else:
                    if any(kw in name_lower for kw in ['visita guidata', 'guided tour', 'visite guidate']):
                        target_ticket = visit
                        logger.info(f"✅ Found guided tour: {visit.get('name')}")
                        break
            
            if not target_ticket:
                logger.debug(f"No Vatican Museums tickets found for {date_str}")
                continue
            
            ticket_id = str(target_ticket['id'])
            ticket_name = target_ticket.get('name', 'Vatican Museums')
            
            # Step 2: Check time availability
            timeavail_url = "https://tickets.museivaticani.va/api/visit/timeavail"
            timeavail_params = {
                'lang': 'it',
                'visitLang': language if language else '',
                'visitTypeId': ticket_id,
                'visitorNum': str(visitors),
                'visitDate': date_str
            }
            
            cookies = {'JSESSIONID': search_response.cookies.get('JSESSIONID', '')}
            time_response = requests.get(timeavail_url, params=timeavail_params, cookies=cookies, timeout=10)
            
            if time_response.status_code != 200:
                continue
            
            time_data = time_response.json()
            timetable = time_data.get('timetable', [])
            
            # Find first available time slot
            for slot in timetable:
                if slot.get('availability') == 'AVAILABLE':
                    available_slot = {
                        'date': date_str,
                        'time': slot['time'],
                        'ticket_id': ticket_id,
                        'ticket_name': ticket_name,
                        'visitors': visitors,
                        'language': language
                    }
                    logger.info(f"✅ Found available slot: {date_str} {slot['time']} - {ticket_name}")
                    break
            
            if available_slot:
                break
                
        except Exception as e:
            logger.error(f"Error checking {date_str}: {e}")
            continue
    
    # If no availability found, return error
    if not available_slot:
        return Response({
            'success': False,
            'error': 'No Vatican Museums tickets available in the next 90 days',
            'message': 'Vatican Museums has no general entry or guided tour availability in the next 3 months. Tickets may not be released yet, or all slots are sold out.'
        }, status=404)
    
    # Create test agency and task
    agency, _ = Agency.objects.get_or_create(
        name="Test Agency",
        defaults={
            'telegram_chat_id': '123456789',
            'is_active': True
        }
    )
    
    task, _ = MonitorTask.objects.get_or_create(
        agency=agency,
        site='vatican',
        ticket_name=available_slot['ticket_name'],
        defaults={
            'dates': [available_slot['date']],
            'preferred_times': [],
            'visitors': visitors,
            'is_active': True,
            'tier': 'hold',
            'language': language
        }
    )
    
    # Create held slot with REAL available data
    held_slot = HeldSlot.objects.create(
        task=task,
        date=available_slot['date'],
        slot_time=available_slot['time'],
        slot_id=f'TEST_SLOT_{timezone.now().timestamp()}',
        ticket_id=available_slot['ticket_id'],
        ticket_name=available_slot['ticket_name'],
        visitors=visitors,
        adult_count=visitors,
        child_count=0,
        total_price=35.00 * visitors,
        status='held',
        hold_started_at=timezone.now(),
        last_keepalive_at=timezone.now()
    )
    
    return Response({
        'success': True,
        'slot_id': held_slot.id,
        'date': held_slot.date,
        'time': held_slot.slot_time,
        'ticket_name': held_slot.ticket_name,
        'visitors': held_slot.visitors,
        'message': f'✅ Vatican Museums ticket found! {held_slot.date} at {held_slot.slot_time}. Extension should detect it within 10 seconds.',
        'is_real_availability': True
    })


@api_view(['DELETE'])
def delete_test_slots(request):
    """Delete all test held slots."""
    from .models import HeldSlot
    
    # Delete test slots (slot_id starts with TEST)
    deleted_count = HeldSlot.objects.filter(slot_id__startswith='TEST').delete()[0]
    
    return Response({
        'success': True,
        'deleted_count': deleted_count,
        'message': f'Deleted {deleted_count} test slot(s)'
    })


@api_view(['POST'])
def auto_snipe_task(request):
    """
    CRM Auto-Snipe endpoint.
    Creates a VaticanTask from CRM data for automatic sniping.
    Called by the CRM Auto-Snipe Engine when it finds bookings needing tickets.
    """
    try:
        data = request.data
        date_str = data.get('date', '')
        time_slot = data.get('time_slot', '09:00')
        visitors = int(data.get('visitors', 4))
        priority = int(data.get('priority', 5))
        customer_email = data.get('customer_email', '')
        customer_name = data.get('customer_name', '')
        source_booking_id = data.get('source_booking_id', '')

        if not date_str:
            return Response({'error': 'date required'}, status=400)

        from .models import VaticanTask
        import json

        task = VaticanTask.objects.create(
            status='new',
            target_date=date_str,
            target_time=time_slot,
            visitors=visitors,
            priority=priority,
            metadata=json.dumps({
                'source': 'crm_auto_snipe',
                'source_booking_id': source_booking_id,
                'customer_email': customer_email,
                'customer_name': customer_name,
            }),
            notes=f'Auto-snipe from CRM: {customer_name} ({customer_email}) — {date_str} {time_slot}',
        )

        logger.info(f" Auto-snipe task #{task.id} created: {date_str} {time_slot} ({visitors}v)")

        return Response({
            'success': True,
            'task_id': task.id,
            'date': date_str,
            'time_slot': time_slot,
            'visitors': visitors,
        }, status=201)

    except Exception as e:
        logger.error(f"Auto-snipe task creation error: {e}")
        return Response({'error': str(e)}, status=500)
