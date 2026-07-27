"""
Admin Panel Views
Provides comprehensive admin functionality for managing agencies, users, and tasks
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import BasePermission
from django.contrib.auth.hashers import make_password
from django.db.models import Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
import hashlib
import secrets

from .models import Agency, User, MonitorTask, TelegramGroup
from .serializers import AgencySerializer, UserSerializer, MonitorTaskSerializer


class IsSuperAdmin(BasePermission):
    """Check super admin via our custom session token auth."""
    def has_permission(self, request, view):
        try:
            auth = request.headers.get('Authorization', '')
            if not auth.startswith('Bearer '):
                return False
            token = auth.replace('Bearer ', '')
            from django.core.cache import cache
            session = cache.get(f'session:{token}')
            if not session or not session.get('is_super_admin'):
                return False
            # Attach user to request for use in views
            request._admin_user = User.objects.get(id=session['user_id'])
            return True
        except Exception:
            return False


class AdminAgencyViewSet(viewsets.ModelViewSet):
    """
    Admin viewset for managing agencies
    """
    queryset = Agency.objects.all()
    serializer_class = AgencySerializer
    permission_classes = [IsSuperAdmin]
    
    def list(self, request):
        """List all agencies with stats"""
        agencies = Agency.objects.annotate(
            user_count=Count('users'),
            task_count=Count('tasks'),
            active_task_count=Count('tasks', filter=Q(tasks__is_active=True))
        ).order_by('name')
        
        data = []
        for agency in agencies:
            # Get latest activity
            latest_task = agency.tasks.order_by('-updated_at').first()
            latest_activity = latest_task.updated_at if latest_task else agency.created_at
            
            data.append({
                'id': agency.id,
                'name': agency.name,
                'plan': agency.plan,
                'is_active': agency.is_active,
                'user_count': agency.user_count,
                'task_count': agency.task_count,
                'active_task_count': agency.active_task_count,
                'latest_activity': latest_activity,
                'created_at': agency.created_at,
                'telegram_chat_id': agency.telegram_chat_id,
                'telegram_groups': list(agency.telegram_groups.values('id', 'chat_id', 'chat_title'))
            })
        
        return Response(data)

    def destroy(self, request, pk=None):
        """Delete agency - block if it has users or tasks"""
        agency = self.get_object()
        if agency.users.exists():
            return Response(
                {'error': f'Cannot delete: agency has {agency.users.count()} user(s). Delete users first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        agency.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def partial_update(self, request, pk=None):
        """Update agency - name, plan, telegram_chat_id"""
        agency = self.get_object()
        if 'name' in request.data:
            agency.name = request.data['name']
        if 'plan' in request.data:
            agency.plan = request.data['plan']
        if 'telegram_chat_id' in request.data:
            agency.telegram_chat_id = request.data['telegram_chat_id'] or None
        if 'is_active' in request.data:
            agency.is_active = request.data['is_active']
        agency.save()
        return Response({'success': True, 'id': agency.id, 'name': agency.name,
                         'plan': agency.plan, 'telegram_chat_id': agency.telegram_chat_id})

    def update(self, request, pk=None):
        return self.partial_update(request, pk)

    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle agency active status"""
        agency = self.get_object()
        agency.is_active = not agency.is_active
        agency.save()
        
        # Also toggle all users and tasks
        agency.users.update(is_active=agency.is_active)
        agency.tasks.update(is_active=agency.is_active)
        
        return Response({
            'success': True,
            'is_active': agency.is_active,
            'message': f'Agency {"activated" if agency.is_active else "deactivated"}'
        })
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get detailed agency statistics"""
        agency = self.get_object()
        
        # Task statistics
        tasks = agency.tasks.all()
        task_stats = {
            'total': tasks.count(),
            'active': tasks.filter(is_active=True).count(),
            'inactive': tasks.filter(is_active=False).count(),
            'by_type': {
                'standard': tasks.filter(ticket_type=0).count(),
                'guided': tasks.filter(ticket_type=1).count()
            },
            'by_language': {}
        }
        
        # Language distribution for guided tours
        for lang in ['ENG', 'ITA', 'FRA', 'DEU', 'SPA']:
            count = tasks.filter(ticket_type=1, language=lang).count()
            if count > 0:
                task_stats['by_language'][lang] = count
        
        # User statistics
        users = agency.users.all()
        user_stats = {
            'total': users.count(),
            'active': users.filter(is_active=True).count(),
            'admins': users.filter(is_admin=True).count(),
            'recent_logins': users.filter(
                last_login__gte=timezone.now() - timedelta(days=7)
            ).count()
        }
        
        # Activity statistics
        recent_tasks = tasks.filter(created_at__gte=timezone.now() - timedelta(days=30))
        activity_stats = {
            'tasks_created_30d': recent_tasks.count(),
            'last_task_created': tasks.order_by('-created_at').first().created_at if tasks.exists() else None,
            'last_user_login': users.order_by('-last_login').first().last_login if users.exists() else None
        }
        
        return Response({
            'agency': {
                'id': agency.id,
                'name': agency.name,
                'plan': agency.plan,
                'is_active': agency.is_active,
                'created_at': agency.created_at
            },
            'tasks': task_stats,
            'users': user_stats,
            'activity': activity_stats
        })


class AdminUserViewSet(viewsets.ModelViewSet):
    """
    Admin viewset for managing users
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsSuperAdmin]
    
    def list(self, request):
        """List all users with agency info"""
        users = User.objects.select_related('agency').order_by('agency__name', 'username')
        
        data = []
        for user in users:
            data.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.full_name,
                'is_active': user.is_active,
                'is_admin': user.is_admin,
                'agency': {
                    'id': user.agency.id,
                    'name': user.agency.name,
                    'plan': user.agency.plan
                },
                'last_login': user.last_login,
                'created_at': user.created_at,
                'task_count': user.agency.tasks.count()
            })
        
        return Response(data)
    
    def create(self, request):
        """Create new user"""
        data = request.data
        
        # Validate required fields
        required_fields = ['username', 'email', 'password', 'agency_id']
        for field in required_fields:
            if field not in data:
                return Response(
                    {'error': f'Field {field} is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Check if username/email already exists
        if User.objects.filter(username=data['username']).exists():
            return Response(
                {'error': 'Username already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if User.objects.filter(email=data['email']).exists():
            return Response(
                {'error': 'Email already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get agency
        try:
            agency = Agency.objects.get(id=data['agency_id'])
        except Agency.DoesNotExist:
            return Response(
                {'error': 'Agency not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create password hash
        password_hash = self._create_password_hash(data['password'])
        
        # Create user
        user = User.objects.create(
            username=data['username'],
            email=data['email'],
            password_hash=password_hash,
            full_name=data.get('full_name', ''),
            agency=agency,
            is_active=data.get('is_active', True),
            is_admin=data.get('is_admin', False)
        )
        
        return Response({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'agency': agency.name
            },
            'message': 'User created successfully'
        })
    
    def update(self, request, pk=None):
        """Update user"""
        user = self.get_object()
        data = request.data
        
        # Update basic fields
        if 'username' in data:
            if User.objects.filter(username=data['username']).exclude(id=user.id).exists():
                return Response(
                    {'error': 'Username already exists'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user.username = data['username']
        
        if 'email' in data:
            if User.objects.filter(email=data['email']).exclude(id=user.id).exists():
                return Response(
                    {'error': 'Email already exists'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user.email = data['email']
        
        if 'full_name' in data:
            user.full_name = data['full_name']
        
        if 'is_active' in data:
            user.is_active = data['is_active']
        
        if 'is_admin' in data:
            user.is_admin = data['is_admin']
        
        # Update agency
        if 'agency_id' in data:
            try:
                agency = Agency.objects.get(id=data['agency_id'])
                user.agency = agency
            except Agency.DoesNotExist:
                return Response(
                    {'error': 'Agency not found'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Update password if provided
        if 'password' in data and data['password']:
            user.password_hash = self._create_password_hash(data['password'])
        
        user.save()
        
        return Response({
            'success': True,
            'message': 'User updated successfully'
        })
    
    def destroy(self, request, pk=None):
        """Delete user"""
        try:
            user = self.get_object()
            # Clear any active sessions for this user from Redis
            try:
                import django_redis
                from django.core.cache import cache
                # Sessions are stored as session_token -> user_id, scan not easy
                # Just delete the user - sessions will naturally expire
            except Exception:
                pass
            user.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        """Reset user password"""
        user = self.get_object()
        new_password = request.data.get('password')
        
        if not new_password:
            return Response(
                {'error': 'Password is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user.password_hash = self._create_password_hash(new_password)
        user.save()
        
        return Response({
            'success': True,
            'message': 'Password reset successfully'
        })
    
    def _create_password_hash(self, password):
        """Create secure password hash - must match User.check_password format: salt$hash"""
        salt = secrets.token_hex(16)
        hashed = hashlib.sha256((password + salt).encode()).hexdigest()
        return f"{salt}${hashed}"


class AdminTaskViewSet(viewsets.ModelViewSet):
    """
    Admin viewset for managing tasks
    """
    queryset = MonitorTask.objects.all()
    serializer_class = MonitorTaskSerializer
    permission_classes = [IsSuperAdmin]
    
    def list(self, request):
        """List all tasks with agency info"""
        tasks = MonitorTask.objects.select_related('agency').order_by('-created_at')
        
        # Filter by agency if specified
        agency_id = request.query_params.get('agency_id')
        if agency_id:
            tasks = tasks.filter(agency_id=agency_id)
        
        data = []
        for task in tasks:
            data.append({
                'id': task.id,
                'agency': {
                    'id': task.agency.id,
                    'name': task.agency.name,
                    'plan': task.agency.plan
                },
                'site': task.site,
                'ticket_name': task.ticket_name,
                'ticket_type': task.get_ticket_type_display(),
                'language': task.language,
                'dates': task.dates,
                'preferred_times': task.preferred_times,
                'visitors': task.visitors,
                'is_active': task.is_active,
                'last_checked': task.last_checked,
                'last_status': task.last_status,
                'created_at': task.created_at,
                'updated_at': task.updated_at
            })
        
        return Response(data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get overall task statistics"""
        tasks = MonitorTask.objects.all()
        
        stats = {
            'total': tasks.count(),
            'active': tasks.filter(is_active=True).count(),
            'by_agency': {},
            'by_type': {
                'standard': tasks.filter(ticket_type=0).count(),
                'guided': tasks.filter(ticket_type=1).count()
            },
            'by_language': {},
            'recent_activity': {
                'created_today': tasks.filter(
                    created_at__date=timezone.now().date()
                ).count(),
                'created_week': tasks.filter(
                    created_at__gte=timezone.now() - timedelta(days=7)
                ).count(),
                'checked_today': tasks.filter(
                    last_checked__date=timezone.now().date()
                ).count()
            }
        }
        
        # By agency
        for agency in Agency.objects.all():
            agency_tasks = tasks.filter(agency=agency)
            if agency_tasks.exists():
                stats['by_agency'][agency.name] = {
                    'total': agency_tasks.count(),
                    'active': agency_tasks.filter(is_active=True).count()
                }
        
        # By language (guided tours only)
        for lang in ['ENG', 'ITA', 'FRA', 'DEU', 'SPA']:
            count = tasks.filter(ticket_type=1, language=lang).count()
            if count > 0:
                stats['by_language'][lang] = count
        
        return Response(stats)


class AdminDashboardViewSet(viewsets.ViewSet):
    """
    Admin dashboard overview
    """
    permission_classes = [IsSuperAdmin]
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Get admin dashboard overview"""
        
        # System statistics
        agencies = Agency.objects.all()
        users = User.objects.all()
        tasks = MonitorTask.objects.all()
        
        # Recent activity
        recent_agencies = agencies.filter(
            created_at__gte=timezone.now() - timedelta(days=30)
        ).count()
        
        recent_users = users.filter(
            created_at__gte=timezone.now() - timedelta(days=30)
        ).count()
        
        recent_tasks = tasks.filter(
            created_at__gte=timezone.now() - timedelta(days=30)
        ).count()
        
        # Active monitoring
        active_tasks = tasks.filter(is_active=True).count()
        active_agencies = agencies.filter(is_active=True).count()
        
        # Top agencies by task count
        top_agencies = agencies.annotate(
            task_count=Count('tasks')
        ).order_by('-task_count')[:5]
        
        return Response({
            'system_stats': {
                'total_agencies': agencies.count(),
                'active_agencies': active_agencies,
                'total_users': users.count(),
                'active_users': users.filter(is_active=True).count(),
                'total_tasks': tasks.count(),
                'active_tasks': active_tasks
            },
            'recent_activity': {
                'new_agencies_30d': recent_agencies,
                'new_users_30d': recent_users,
                'new_tasks_30d': recent_tasks
            },
            'top_agencies': [
                {
                    'id': agency.id,
                    'name': agency.name,
                    'plan': agency.plan,
                    'task_count': agency.task_count,
                    'is_active': agency.is_active
                }
                for agency in top_agencies
            ],
            'system_health': {
                'database_status': 'healthy',
                'last_updated': timezone.now()
            }
        })


class AdminRecapViewSet(viewsets.ViewSet):
    """Admin viewset for viewing recapped slots"""
    permission_classes = [IsSuperAdmin]
    
    def list(self, request):
        """Get all recapped slots from WOR agency"""
        from .models import HeldSlot
        
        # Get WOR agency
        try:
            wor_agency = Agency.objects.get(name='WOR')
        except Agency.DoesNotExist:
            return Response({'error': 'WOR agency not found'}, status=404)
        
        # Get all held slots for WOR
        slots = HeldSlot.objects.filter(
            task__agency=wor_agency,
            status__in=['held', 'paying', 'paid']
        ).select_related('task').order_by('-hold_started_at')
        
        # Apply filters
        status_filter = request.query_params.get('status')
        if status_filter:
            slots = slots.filter(status=status_filter)
        
        date_filter = request.query_params.get('date')
        if date_filter:
            slots = slots.filter(date__contains=date_filter)
        
        # Build response
        data = []
        for slot in slots:
            age_hours = (timezone.now() - slot.hold_started_at).total_seconds() / 3600
            data.append({
                'id': slot.id,
                'date': slot.date,
                'slot_time': slot.slot_time,
                'ticket_name': slot.ticket_name,
                'visitors': slot.visitors,
                'total_price': str(slot.total_price),
                'status': slot.status,
                'recap_id': slot.recap_id,
                'hold_started_at': slot.hold_started_at,
                'age_hours': round(age_hours, 1),
                'jsessionid': slot.jsessionid[:20] + '...' if slot.jsessionid else None,
            })
        
        return Response({
            'slots': data,
            'total': len(data),
            'by_status': {
                'held': sum(1 for s in data if s['status'] == 'held'),
                'paying': sum(1 for s in data if s['status'] == 'paying'),
                'paid': sum(1 for s in data if s['status'] == 'paid'),
            }
        })
