import logging
import json
import os
import random
import requests as py_requests
from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from django.core.cache import cache
from django.db import models
from .models import MonitorTask, CheckResult, Agency, Proxy, SiteCredential

# 1. Clean Imports
logger = logging.getLogger(__name__)

from .deep_scan import DeepDiscoveryEngine

# VaticanPro is legacy class that may not exist
VaticanPro = None

try:
    from worker_vatican.monitor import VaticanPro
except ImportError:
    logger.warning("⚠️ worker_vatican.monitor.VaticanPro not found (legacy module)")

try:
    from worker_vatican.hydra_monitor import HydraBot
except ImportError:
    HydraBot = None
    logger.warning("⚠️ HydraBot not found")

try:
    from worker_vatican.god_tier_monitor import GodTierVaticanMonitor
except ImportError:
    GodTierVaticanMonitor = None
    logger.warning("⚠️ GodTierVaticanMonitor not found")

# ✅ GOD-TIER CONFIGURATION
# Set to 'headless' for ultra-fast HTTP mode (10x faster)
# Set to 'browser' for legacy browser mode (slower but more reliable)
# Set to 'hybrid' to try headless first, fallback to browser (recommended)
VATICAN_MONITOR_MODE = os.getenv('VATICAN_MONITOR_MODE', 'hybrid')

logger.info(f"🚀 Vatican Monitor Mode: {VATICAN_MONITOR_MODE}")


# ============================================================================
# BOKUN → GOOGLE SHEETS SYNC TASK
# ============================================================================

@shared_task(name="sync_bokun_to_sheets", queue="celery")
def sync_bokun_to_sheets():
    """
    Fetch bookings from Bokun API and sync to Google Sheets
    Runs every 5 minutes
    
    This task:
    1. Fetches confirmed bookings from Bokun
    2. Writes them to Google Sheets (Bookings_Input)
    3. Bot then reads from Sheets and creates monitoring tasks
    """
    try:
        from backend.services.bokun_api import get_bokun_api
        from datetime import datetime, timedelta
        
        logger.info("📥 Starting Bokun → Sheets sync...")
        
        # Get Bokun API client
        api = get_bokun_api()
        
        # Fetch bookings for next 90 days
        from_date = datetime.now()
        to_date = datetime.now() + timedelta(days=90)
        
        # Sync to Google Sheets
        synced_count = api.sync_bookings_to_sheets(from_date, to_date)
        
        logger.info(f"✅ Bokun sync complete: {synced_count} bookings synced")
        return f"Synced {synced_count} bookings"
        
    except Exception as e:
        logger.error(f"❌ Bokun sync failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return f"Failed: {str(e)}"


@shared_task(name="sync_sheets_to_monitoring", queue="celery")
def sync_sheets_to_monitoring():
    """
    Read pending bookings from Google Sheets and create monitoring tasks
    Runs every 5 minutes
    
    This task:
    1. Reads from Google Sheets (Bookings_Input)
    2. Finds bookings with status "Pending"
    3. Creates MonitorTask for each booking
    4. Updates status to "Monitoring"
    """
    try:
        from backend.services.bokun_sheets_sync import get_bokun_sync
        
        logger.info("📊 Starting Sheets → Monitoring sync...")
        
        # Get Sheets sync service
        sync = get_bokun_sync()
        
        # Get pending bookings
        pending_bookings = sync.get_pending_bookings()
        
        if not pending_bookings:
            logger.info("ℹ️ No pending bookings in Sheets")
            return "No pending bookings"
        
        logger.info(f"📋 Found {len(pending_bookings)} pending bookings")
        
        created_count = 0
        
        for booking in pending_bookings:
            try:
                booking_id = booking.get('Booking ID', '')
                date = booking.get('Date', '')
                time = booking.get('Time', '10:00')
                visitors = int(booking.get('Visitors', 1))
                
                if not booking_id or not date:
                    logger.warning(f"⚠️ Skipping booking with missing data: {booking}")
                    continue
                
                # Check if monitoring task already exists
                existing_task = MonitorTask.objects.filter(
                    dates__contains=[date],
                    preferred_times__contains=[time],
                    visitors=visitors,
                    is_active=True
                ).first()
                
                if existing_task:
                    logger.info(f"⏭️ Task already exists for {booking_id}")
                    # Update status anyway
                    sync.update_booking_status(
                        booking_id,
                        'Monitoring',
                        notes=f'Monitoring task ID: {existing_task.id}'
                    )
                    continue
                
                # Get default agency (or create one)
                agency = Agency.objects.filter(is_active=True).first()
                
                if not agency:
                    logger.warning("⚠️ No active agency found, creating default")
                    agency = Agency.objects.create(
                        name='Default Agency',
                        api_key='default',
                        is_active=True
                    )
                
                # Convert date format: DD/MM/YYYY → YYYY-MM-DD
                try:
                    from datetime import datetime
                    date_obj = datetime.strptime(date, '%d/%m/%Y')
                    date_formatted = date_obj.strftime('%Y-%m-%d')
                except:
                    date_formatted = date
                
                # Create monitoring task
                task = MonitorTask.objects.create(
                    agency=agency,
                    site='vatican',
                    area_name='Vatican Museums',
                    dates=[date_formatted],
                    preferred_times=[time],
                    visitors=visitors,
                    adult_count=visitors,
                    child_count=0,
                    ticket_type=0,  # Standard ticket
                    ticket_name='Vatican Museums - Standard Entry',
                    check_interval=300,  # 5 minutes
                    tier='snipe',
                    is_active=True,
                    notification_mode='available_only'
                )
                
                logger.info(f"✅ Created monitoring task {task.id} for booking {booking_id}")
                
                # Update Google Sheets status
                sync.update_booking_status(
                    booking_id,
                    'Monitoring',
                    notes=f'Bot monitoring task created (ID: {task.id})'
                )
                
                created_count += 1
                
            except Exception as e:
                logger.error(f"Failed to create task for booking {booking.get('Booking ID')}: {e}")
                continue
        
        logger.info(f"✅ Sheets sync complete: {created_count} tasks created")
        return f"Created {created_count} monitoring tasks"
        
    except Exception as e:
        logger.error(f"❌ Sheets sync failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return f"Failed: {str(e)}"

def normalize_date(date_str):
    """
    Normalize any date format to DD/MM/YYYY for Vatican API.
    Handles: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY
    Returns None if date is in the past or invalid.
    """
    from datetime import datetime, date as date_type
    try:
        # Parse the date
        if '-' in date_str and len(date_str) == 10 and date_str[4] == '-':
            # YYYY-MM-DD
            dt = datetime.strptime(date_str, '%Y-%m-%d').date()
        elif '/' in date_str:
            # DD/MM/YYYY
            dt = datetime.strptime(date_str, '%d/%m/%Y').date()
        elif '-' in date_str:
            # DD-MM-YYYY
            dt = datetime.strptime(date_str, '%d-%m-%Y').date()
        else:
            logger.error(f"❌ Unknown date format: {date_str}")
            return None

        # Skip past dates
        today = date_type.today()
        if dt < today:
            # ✅ FIX BUG #3: Log at debug level to reduce noise (still visible if needed)
            logger.debug(f"⏭️ Skipping past date: {date_str} ({dt})")
            return None

        return dt.strftime('%d/%m/%Y')
    except Exception as e:
        logger.error(f"❌ Date normalization failed for '{date_str}': {e}")
        return None


def get_proxy_str(site='vatican'):
    """Helper to select the best proxy using Smart Reputation Logic"""
    now = timezone.now()
    
    # Reset expired cooldowns (clean up logic, or just filter)
    # Filter proxies that are active AND not cooling down
    valid_proxies = Proxy.objects.filter(is_active=True).filter(
        models.Q(cooldown_until__isnull=True) | models.Q(cooldown_until__lte=now)
    )
    
    # Vatican prefers Oxylabs but can use any proxy
    proxy_obj = valid_proxies.filter(ip_port__icontains='oxylabs').order_by('?').first()
    if not proxy_obj:
        proxy_obj = valid_proxies.order_by('?').first()

    if not proxy_obj:
        # If ALL proxies are on cooldown, pick the one with the earliest cooldown expiry
        # This prevents 100% downtime if everything is banned
        emergency_proxy = Proxy.objects.filter(is_active=True).order_by('cooldown_until').first()
        if emergency_proxy:
            logger.warning(f"⚠️ All proxies on cooldown! Using earliest available: {emergency_proxy} (Expires: {emergency_proxy.cooldown_until})")
            proxy_obj = emergency_proxy
        else:
            return None, None

    # Update Last Used
    proxy_obj.last_used = now
    proxy_obj.save(update_fields=['last_used'])

    user = proxy_obj.username
    if 'oxylabs' in proxy_obj.ip_port.lower():
        session_id = random.randint(10000, 99999)
        user = f"{proxy_obj.username}-session-{session_id}"
    
    if user and proxy_obj.password:
        return f"http://{user}:{proxy_obj.password}@{proxy_obj.ip_port}", proxy_obj
    else:
        return f"http://{proxy_obj.ip_port}", proxy_obj

def report_proxy_status(proxy_obj, success=True):
    """Update proxy reputation based on result"""
    if not proxy_obj: 
        return
        
    if success:
        if proxy_obj.fail_count > 0:
            proxy_obj.fail_count = 0
            proxy_obj.consecutive_failures = 0
            proxy_obj.cooldown_until = None
            proxy_obj.save()
    else:
        proxy_obj.fail_count += 1
        proxy_obj.consecutive_failures += 1
        
        # Smart Cooldown Logic (Exponential Backoff)
        # 1 fail = 0m, 3 fails = 5m, 5 fails = 30m, 10 fails = 2h
        cooldown_mins = 0
        if proxy_obj.consecutive_failures >= 3:
            cooldown_mins = 5
        if proxy_obj.consecutive_failures >= 5:
            cooldown_mins = 30
        if proxy_obj.consecutive_failures >= 10:
            cooldown_mins = 120
            
        if cooldown_mins > 0:
            proxy_obj.cooldown_until = timezone.now() + timedelta(minutes=cooldown_mins)
            logger.warning(f"🚫 Proxy {proxy_obj} cooling down for {cooldown_mins}m (Failures: {proxy_obj.consecutive_failures})")
            
        proxy_obj.save()


@shared_task(name="refresh_vatican_session", queue="vatican")
def refresh_vatican_session():
    """Runs periodically to pre-warm Vatican cookies and store in Redis"""
    logger.info("🔄 GOD TIER: Refreshing Vatican Session...")
    try:
        proxy_str, _ = get_proxy_str('vatican')
        
        # Check for ANY active credential to use for warming (can use first found)
        creds = SiteCredential.objects.filter(site='vatican', is_active=True).first()
        username = creds.username if creds else None
        password = creds.password if creds else None
        
        monitor = VaticanPro(proxy=proxy_str, username=username, password=password)
        # Force generation
        monitor.generate_trust_cookies()
        
        if monitor.session.cookies:
            cookies = monitor.session.cookies.get_dict()
            cache.set('vatican_cookies', cookies, timeout=600)
            logger.info(f"✅ Vatican Session Cached! ({len(cookies)} cookies)")
            return "Session Refreshed"
    except Exception as e:
        logger.error(f"Failed to refresh Vatican session: {e}")
    return "Failed"


# ✅ NEW: SMART VATICAN MONITOR (Multi-Agency Optimized)
@shared_task(name="run_smart_vatican_monitor", queue="vatican")
def run_smart_vatican_monitor(date, ticket_id, ticket_name, language, task_ids, visitors=2):
    """
    ULTRA-OPTIMIZED: Checks ONE specific (date, ticket_id, language) combo
    and notifies ALL agencies (task_ids) interested in it.
    
    Args:
        date: DD/MM/YYYY format
        ticket_id: Vatican ticket ID (e.g., '929041748')
        ticket_name: Human-readable name
        language: Language code (ENG/ITA/FRA/DEU/SPA) or None for standard tickets
        task_ids: List of MonitorTask IDs interested in this combo
    """
    try:
        logger.info(f"🎯 SMART CHECK: {date} | Ticket: {ticket_id} ({ticket_name}) | Lang: {language} | Agencies: {len(task_ids)}")
        
        from worker_vatican.hydra_monitor import HydraBot
        import asyncio
        
        async def check_ticket():
            bot = HydraBot(use_proxies=True)
            
            async with bot.get_browser() as browser:
                page = await browser.new_page()
                
                try:
                    # Navigate to deep link for this specific ticket/date
                    # Use ticket_type=0 for standard, 1 for guided (determined by language presence)
                    ticket_type = 1 if language else 0
                    
                    # Resolve IDs to get to the page
                    resolved_ids = await bot.resolve_all_dynamic_ids(
                        page,
                        ticket_type=ticket_type,
                        target_date=date,
                        visitors=visitors
                    )
                    
                    # 💡 DYNAMIC RESOLUTION LOGIC
                    # Ignore the passed 'ticket_id' (it's likely stale).
                    # Find the fresh ID that matches 'ticket_name'.
                    fresh_id = None
                    exact_match = None
                    
                    logger.info(f"🔎 Resolving fresh ID for name '{ticket_name}' among {len(resolved_ids)} candidates...")
                    
                    # ✅ IMPROVED: Multi-strategy matching
                    # Strategy 1: Exact substring match
                    for item in resolved_ids:
                        r_name = item.get('name', '').lower()
                        t_name = ticket_name.lower()
                        
                        if t_name in r_name or r_name in t_name:
                            if ticket_type == 0 and "lunch" in r_name: continue
                            exact_match = item['id']
                            logger.info(f"✅ Exact Match: '{ticket_name}' -> ID {exact_match}")
                            break
                    
                    # Strategy 2: Keyword matching (if no exact match)
                    if not exact_match:
                        # Extract key terms from ticket name
                        keywords = []
                        t_lower = ticket_name.lower()
                        
                        # CRITICAL: Be specific about Musei Vaticani vs Palazzo Papale
                        if 'musei' in t_lower:
                            keywords.extend(['musei', 'vaticani', 'aree', 'museali'])  # ✅ Added 'aree museali'
                            # Explicitly exclude Palazzo Papale
                        elif 'palazzo' in t_lower:
                            keywords.extend(['palazzo', 'papale'])
                        elif 'specola' in t_lower:
                            keywords.extend(['specola', 'vaticana'])
                        
                        if 'biglietti' in t_lower or 'admission' in t_lower or 'ingresso' in t_lower:
                            keywords.extend(['biglietti', 'ingresso'])
                        if 'visita' in t_lower or 'guided' in t_lower or 'tour' in t_lower:
                            keywords.extend(['visita', 'guidata'])
                        
                        # Try to find ticket with most keyword matches
                        best_match = None
                        best_score = 0
                        
                        for item in resolved_ids:
                            r_name = item.get('name', '').lower()
                            score = sum(1 for kw in keywords if kw in r_name)
                            
                            # CRITICAL: If looking for Musei Vaticani, reject Palazzo Papale
                            if 'musei' in t_lower and 'palazzo' in r_name:
                                continue
                            # If looking for Palazzo Papale, reject Musei Vaticani
                            if 'palazzo' in t_lower and 'musei' in r_name:
                                continue
                            
                            # ✅ MONDAY FIX: Exclude special event tickets (Monday-only programs)
                            # These have different schedules and should never match standard tickets
                            monday_special_keywords = ['quaresima', 'didattiche - laboratorio', 'pellegrinaggi']
                            if any(x in r_name for x in monday_special_keywords):
                                logger.info(f"⏭️ Skipping Monday-special ticket: {r_name}")
                                continue
                            
                            # Avoid lunch/special tickets for standard admission
                            if ticket_type == 0 and any(x in r_name for x in ['lunch', 'pranzo', 'pellegrinaggi']):
                                continue
                            
                            if score > best_score:
                                best_score = score
                                best_match = item['id']
                        
                        if best_match and best_score >= 2:
                            exact_match = best_match
                            logger.info(f"✅ Keyword Match: '{ticket_name}' -> ID {exact_match} (score: {best_score})")
                    
                    # Strategy 3: Use first standard ticket as fallback
                    if not exact_match and ticket_type == 0:
                        for item in resolved_ids:
                            r_name = item.get('name', '').lower()
                            
                            # ✅ MONDAY FIX: Skip Monday-special tickets in fallback too
                            monday_special_keywords = ['quaresima', 'didattiche - laboratorio', 'pellegrinaggi']
                            if any(x in r_name for x in monday_special_keywords):
                                continue
                            
                            # Look for standard admission tickets
                            # ✅ IMPROVED: Also check for "aree museali" and "ingresso" patterns
                            if any(x in r_name for x in ['biglietti', 'ingresso', 'aree museali', 'museali']):
                                # Exclude special tickets
                                if not any(x in r_name for x in ['lunch', 'pranzo', 'pellegrinaggi', 'gruppi', 'palazzo', 'specola']):
                                    exact_match = item['id']
                                    logger.info(f"✅ Fallback Match: Using first standard ticket -> ID {exact_match}")
                                    break
                    
                    if exact_match:
                        fresh_id = exact_match
                    else:
                        # LOG THE CANDIDATES for debugging
                        candidate_names = [i.get('name', '') for i in resolved_ids]
                        logger.warning(f"⚠️ No name match for '{ticket_name}'. Candidates: {candidate_names}")
                        logger.warning(f"Falling back to stale ID {ticket_id} (Risky)")
                        fresh_id = ticket_id # Fallback
                    
                    # Determine ticket index for language detection
                    # For now, we pass 0 - the method will auto-detect language selector
                    ticket_index = 0
                    
                    # ✅ USE ENHANCED CHECK METHOD with FRESH ID
                    result = await bot.check_via_click(
                        page,
                        ticket_id=fresh_id,
                        ticket_name=ticket_name,
                        ticket_index=ticket_index,
                        visit_date=date,
                        visitors=visitors
                    )
                    
                    slots = result.get('slots', [])
                    detected_lang = result.get('language')
                    
                    await page.close()
                    
                    return {
                        'status': 'available' if slots else 'sold_out',
                        'slots': slots,
                        'language_detected': detected_lang,
                        'checked_id': fresh_id
                    }
                    
                except Exception as e:
                    logger.error(f"Check failed: {e}")
                    await page.close()
                    return {
                        'status': 'error',
                        'slots': [],
                        'error': str(e)
                    }
        
        # Run the check
        check_result = asyncio.run(check_ticket())
        
        status = check_result['status']
        slots = check_result['slots']
        detected_lang = check_result.get('language_detected')
        
        # ✅ NOTIFY ALL INTERESTED AGENCIES
        tasks = MonitorTask.objects.filter(id__in=task_ids)
        
        for task in tasks:
            task.last_checked = timezone.now()
            task.last_status = status
            
            # ✅ STATE CHANGE DETECTION using Redis
            # Key format: ticket_state:{task_id}:{date} (STABLE - no ticket_id to avoid cache misses)
            state_key = f"ticket_state:{task.id}:{date}"
            previous_state = cache.get(state_key)
            
            # 🛡️ DEFENSIVE: Handle Redis Bytes vs String mismatch
            if isinstance(previous_state, bytes):
                previous_state = previous_state.decode('utf-8')

            # Determine if this is a state CHANGE
            is_now_available = len(slots) > 0
            was_previously_available = previous_state == 'available' if previous_state else False
            is_first_check = previous_state is None
            
            # State change: closed → open
            status_changed_to_open = is_now_available and not was_previously_available
            
            # Update cache with current state
            new_state = 'available' if is_now_available else 'closed'
            cache.set(state_key, new_state, timeout=86400 * 7)  # 7 days TTL
            
            # Save result to database (always, for history)
            CheckResult.objects.create(
                task=task,
                status=status,
                details={
                    'date': date,
                    'ticket_id': ticket_id,
                'effective_ticket_id': check_result.get('checked_id'),
                    'ticket_name': ticket_name,
                    'language': language or detected_lang,
                    'slots': slots,
                    'state_changed': status_changed_to_open,
                    'previous_state': previous_state,
                    'is_first_check': is_first_check
                },
                error_message=check_result.get('error')
            )
            
            # ✅ Save slots to last_result_summary for Telegram display
            try:
                summary_data = {
                    "updates": {
                        date: [{
                            'id': ticket_id,
                            'name': ticket_name,
                            'slots': slots
                        }]
                    },
                    "last_updated": str(timezone.now())
                }
                task.last_result_summary = json.dumps(summary_data)
            except Exception as e:
                logger.error(f"Failed to save result summary: {e}")
            
            task.save()
            
            # ✅ FIXED: Never alert on first check - just establish baseline
            # Only alert on actual state changes (closed → open)
            should_alert = False
            
            # 🛡️ SPAM GUARD: Cooldown key (STABLE - no ticket_id)
            # Prevent sending same alert for same task/date within 60 minutes
            alert_cooldown_key = f"alert_cooldown:{task.id}:{date}"
            
            if is_first_check:
                # First check - establish baseline, never alert
                logger.info(f"ℹ️ First check: {ticket_name} - establishing baseline (status: {new_state})")
                should_alert = False
            elif status_changed_to_open:
                # State changed from closed to open - check cooldown
                if cache.get(alert_cooldown_key):
                    logger.info(f"⏳ SUPPRESSED ALERT: Cooldown active for {ticket_name}")
                    should_alert = False
                else:
                    logger.info(f"🔔 STATE CHANGE: {ticket_name} went from CLOSED → OPEN! Sending Alert.")
                    should_alert = True
                    # Set Cooldown
                    cache.set(alert_cooldown_key, "sent", timeout=3600) # 1 Hour Silence
            elif not is_now_available:
                logger.info(f"🔒 {ticket_name} is CLOSED ({len(slots)} slots)")
            else:
                logger.info(f"ℹ️ {ticket_name} still AVAILABLE - no alert needed")
            
            # Send Telegram notification only if should_alert passed all checks
            if should_alert and task.notification_mode != 'silent':
                try:
                    from .notification_utils import format_vatican_notification, send_telegram_signal
                    from .models import TelegramGroup
                    
                    # Get all approved groups for this agency
                    approved_groups = TelegramGroup.objects.filter(
                        agency=task.agency,
                        status='approved',
                        notification_enabled=True
                    )
                    
                    if approved_groups.exists():
                        message = format_vatican_notification(
                            date=date,
                            ticket_name=ticket_name,
                            ticket_id=str(check_result.get('checked_id') or ticket_id),
                            slots=slots,
                            preferred_times=task.preferred_times if hasattr(task, 'preferred_times') else None,
                            language=detected_lang or language,
                            visitors=task.visitors,
                            check_method="smart"
                        )
                        
                        # Send to all approved groups
                        sent_count = 0
                        for group in approved_groups:
                            if send_telegram_signal(group.chat_id, message):
                                sent_count += 1
                        
                        logger.info(f"✅ TELEGRAM ALERT sent to {sent_count}/{approved_groups.count()} groups for {task.agency.name}")
                    
                    # Fallback: Also send to legacy telegram_chat_id if set
                    elif task.agency.telegram_chat_id:
                        message = format_vatican_notification(
                            date=date,
                            ticket_name=ticket_name,
                            ticket_id=str(check_result.get('checked_id') or ticket_id),
                            slots=slots,
                            preferred_times=task.preferred_times if hasattr(task, 'preferred_times') else None,
                            language=detected_lang or language,
                            visitors=task.visitors,
                            check_method="smart"
                        )
                        
                        send_telegram_signal(task.agency.telegram_chat_id, message)
                        logger.info(f"✅ TELEGRAM ALERT sent to legacy chat_id for {task.agency.name}")
                    else:
                        logger.warning(f"⚠️ No approved Telegram groups found for agency {task.agency.name}")
                        
                except Exception as e:
                    logger.error(f"Notification failed for task {task.id}: {e}")
        
        logger.info(f"✅ Completed check for {date}/{ticket_id} - Checked {len(task_ids)} agencies")
        return f"Checked {ticket_name} - Found {len(slots)} slots - State change alerts sent if applicable"
        
    except Exception as e:
        logger.error(f"Smart monitor failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return f"Failed: {str(e)}"


# ✅ SEARCH API COMPLIANT MONITOR (Vatican Bot Rules Compliant)
@shared_task(name="run_god_tier_vatican_monitor", queue="vatican")
def run_god_tier_vatican_monitor(date, ticket_id, ticket_name, language, task_ids, visitors=2, use_browser_fallback=True):
    """
    🚀 VATICAN BOT RULES COMPLIANT: Uses Search API + timeavail API as mandated.
    
    CRITICAL: This function MUST follow Vatican Bot Rules:
    1. ALWAYS use Search API to get fresh ticket IDs
    2. NEVER use hardcoded/stale ticket IDs
    3. Use timeavail API with fresh IDs and JSESSIONID
    
    Args:
        date: DD/MM/YYYY format
        ticket_id: Vatican ticket ID (IGNORED - will resolve fresh ID)
        ticket_name: Human-readable name for matching
        language: Language code (ENG/ITA/FRA/DEU/SPA) or None for standard tickets
        task_ids: List of MonitorTask IDs interested in this combo
        use_browser_fallback: If True, uses HydraBot when Search API fails
    """
    try:
        logger.info(f"🚀 SEARCH API CHECK: {date} | Ticket: {ticket_name} | Lang: {language} | Agencies: {len(task_ids)}")
        
        ticket_type = 1 if language else 0
        
        # ✅ STEP 1: Use Search API to get fresh ticket IDs (MANDATORY)
        try:
            from worker_vatican.search_api_monitor import VaticanSearchAPIMonitor
            
            # Get proxy for this check
            proxy_str, proxy_obj = get_proxy_str('vatican')
            
            # Initialize Search API Monitor
            monitor = VaticanSearchAPIMonitor(proxy_str=proxy_str)
            
            # Resolve fresh ticket IDs using Search API
            fresh_tickets = monitor.resolve_ticket_ids(
                target_date=date,
                visitors=visitors,
                ticket_type=ticket_type,
                language=language
            )
            
            if not fresh_tickets:
                logger.error(f"❌ Search API returned no tickets for {date}")
                if use_browser_fallback:
                    logger.info("🔄 Falling back to browser mode")
                    return run_smart_vatican_monitor(date, ticket_id, ticket_name, language, task_ids, visitors)
                else:
                    report_proxy_status(proxy_obj, success=False)
                    return f"Failed: No tickets found via Search API"
            
            # ✅ STEP 2: Match ticket by name (3-tier strategy from Vatican Bot Rules)
            fresh_id = None
            
            # Strategy 1: Exact substring match
            for ticket in fresh_tickets:
                t_name_lower = ticket['name'].lower()
                target_name_lower = ticket_name.lower()
                
                if target_name_lower in t_name_lower or t_name_lower in target_name_lower:
                    # Skip lunch/special tickets for standard admission
                    if ticket_type == 0 and any(x in t_name_lower for x in ['lunch', 'pranzo', 'pellegrinaggi']):
                        continue
                    fresh_id = ticket['id']
                    logger.info(f"✅ Exact Match: '{ticket_name}' -> ID {fresh_id}")
                    break
            
            # Strategy 2: Keyword matching
            if not fresh_id:
                keywords = []
                t_lower = ticket_name.lower()
                
                if 'musei' in t_lower:
                    keywords.extend(['musei', 'vaticani', 'aree', 'museali'])
                elif 'palazzo' in t_lower:
                    keywords.extend(['palazzo', 'papale'])
                elif 'specola' in t_lower:
                    keywords.extend(['specola', 'vaticana'])
                
                if 'biglietti' in t_lower or 'admission' in t_lower or 'ingresso' in t_lower:
                    keywords.extend(['biglietti', 'ingresso'])
                if 'visita' in t_lower or 'guided' in t_lower or 'tour' in t_lower:
                    keywords.extend(['visita', 'guidata'])
                
                best_match = None
                best_score = 0
                
                for ticket in fresh_tickets:
                    t_name_lower = ticket['name'].lower()
                    score = sum(1 for kw in keywords if kw in t_name_lower)
                    
                    # Venue exclusions
                    if 'musei' in t_lower and 'palazzo' in t_name_lower:
                        continue
                    if 'palazzo' in t_lower and 'musei' in t_name_lower:
                        continue
                    
                    if ticket_type == 0 and any(x in t_name_lower for x in ['lunch', 'pranzo', 'pellegrinaggi']):
                        continue
                    
                    if score > best_score:
                        best_score = score
                        best_match = ticket['id']
                
                if best_match and best_score >= 2:
                    fresh_id = best_match
                    logger.info(f"✅ Keyword Match: '{ticket_name}' -> ID {fresh_id} (score: {best_score})")
            
            # Strategy 3: Fallback to first appropriate ticket
            if not fresh_id and ticket_type == 0:
                for ticket in fresh_tickets:
                    t_name_lower = ticket['name'].lower()
                    if any(x in t_name_lower for x in ['biglietti', 'ingresso', 'aree museali', 'museali']):
                        if not any(x in t_name_lower for x in ['lunch', 'pranzo', 'pellegrinaggi', 'gruppi', 'palazzo', 'specola']):
                            fresh_id = ticket['id']
                            logger.info(f"✅ Fallback Match: Using first standard ticket -> ID {fresh_id}")
                            break
            
            if not fresh_id:
                candidate_names = [t['name'] for t in fresh_tickets]
                logger.error(f"❌ No name match for '{ticket_name}'. Candidates: {candidate_names}")
                if use_browser_fallback:
                    logger.info("🔄 Falling back to browser mode")
                    return run_smart_vatican_monitor(date, ticket_id, ticket_name, language, task_ids, visitors)
                else:
                    return f"Failed: Could not match ticket name"
            
            # ✅ STEP 3: Check availability using timeavail API with fresh ID
            success, available_slots = monitor.check_availability(
                ticket_id=fresh_id,
                target_date=date,
                visitors=visitors,
                language=language
            )
            
            if success:
                report_proxy_status(proxy_obj, success=True)
                unique_slots = available_slots  # Already processed by Search API monitor
                status = 'available' if unique_slots else 'sold_out'
                logger.info(f"✅ Search API Check Complete: {ticket_name} - Found {len(unique_slots)} slots")
            else:
                logger.error(f"❌ Timeavail API failed for ticket {fresh_id}")
                report_proxy_status(proxy_obj, success=False)
                if use_browser_fallback:
                    logger.info("🔄 Falling back to browser mode")
                    return run_smart_vatican_monitor(date, ticket_id, ticket_name, language, task_ids, visitors)
                else:
                    return f"Failed: Timeavail API error"
            
        except ImportError:
            logger.error("❌ Search API Monitor not available, falling back to browser mode")
            if use_browser_fallback:
                return run_smart_vatican_monitor(date, ticket_id, ticket_name, language, task_ids, visitors)
            else:
                return f"Failed: Search API Monitor not available"
        except Exception as e:
            logger.error(f"❌ Search API check failed: {e}")
            if use_browser_fallback:
                logger.info("🔄 Falling back to browser mode due to error")
                return run_smart_vatican_monitor(date, ticket_id, ticket_name, language, task_ids, visitors)
            else:
                return f"Failed: {str(e)}"
        
        
        # ✅ NOTIFY ALL INTERESTED AGENCIES
        tasks = MonitorTask.objects.filter(id__in=task_ids)
        
        for task in tasks:
            task.last_checked = timezone.now()
            task.last_status = status
            
            # State change detection (STABLE KEY - no ticket_id)
            state_key = f"ticket_state:{task.id}:{date}"
            previous_state = cache.get(state_key)
            
            if isinstance(previous_state, bytes):
                previous_state = previous_state.decode('utf-8')
            
            is_now_available = len(unique_slots) > 0
            was_previously_available = previous_state == 'available' if previous_state else False
            is_first_check = previous_state is None
            status_changed_to_open = is_now_available and not was_previously_available
            
            new_state = 'available' if is_now_available else 'closed'
            cache.set(state_key, new_state, timeout=86400 * 7)
            
            # Save result
            CheckResult.objects.create(
                task=task,
                status=status,
                details={
                    'date': date,
                    'ticket_id': fresh_id,  # ✅ Use fresh ID
                    'effective_ticket_id': fresh_id,  # ✅ Track the actual ID used
                    'original_ticket_id': ticket_id,  # ✅ Keep original for reference
                    'ticket_name': ticket_name,
                    'language': language,
                    'slots': unique_slots,
                    'state_changed': status_changed_to_open,
                    'previous_state': previous_state,
                    'is_first_check': is_first_check,
                    'check_method': 'search_api_compliant',  # ✅ Updated method name
                    'checked_at': str(timezone.now())
                }
            )
            
            # ✅ Save slots to last_result_summary for Telegram display
            try:
                summary_data = {
                    "updates": {
                        date: [{
                            'id': fresh_id,  # ✅ Use fresh ID
                            'name': ticket_name,
                            'slots': unique_slots
                        }]
                    },
                    "last_updated": str(timezone.now())
                }
                task.last_result_summary = json.dumps(summary_data)
            except Exception as e:
                logger.error(f"Failed to save result summary: {e}")
            
            task.save()
            
            # ✅ FIXED: Smart notification logic with stable cache keys
            should_alert = False
            alert_cooldown_key = f"alert_cooldown:{task.id}:{date}"  # ✅ STABLE KEY
            last_slot_count_key = f"last_slot_count:{task.id}:{date}"  # ✅ STABLE KEY
            
            # Get previous slot count
            try:
                last_slot_count = int(cache.get(last_slot_count_key) or 0)
            except:
                last_slot_count = 0
            
            current_slot_count = len(unique_slots)
            
            # Check for significant improvement (e.g. from <5 to >10 slots)
            significant_improvement = False
            if last_slot_count < 5 and current_slot_count >= 10:
                significant_improvement = True
                logger.info(f"📈 SIGNIFICANT IMPROVEMENT: Slots jumped from {last_slot_count} to {current_slot_count}!")

            # ✅ FIXED: Never alert on first check - just establish baseline
            if is_first_check:
                # First check - establish baseline, never alert
                logger.info(f"ℹ️ First check: {ticket_name} - establishing baseline (status: {new_state})")
                should_alert = False
            elif status_changed_to_open:
                # State changed from closed to open - check cooldown
                if cache.get(alert_cooldown_key):
                    logger.info(f"⏳ SUPPRESSED ALERT: Cooldown active for {ticket_name}")
                    should_alert = False
                else:
                    logger.info(f"🔔 STATE CHANGE: {ticket_name} went from CLOSED → OPEN!")
                    should_alert = True
            elif is_now_available and significant_improvement and not cache.get(alert_cooldown_key):
                # Already open, but significantly better availability (and no cooldown)
                logger.info(f"🔔 AVAILABILITY SPIKE: {ticket_name} has much better availability!")
                should_alert = True
            elif not is_now_available:
                logger.info(f"🔒 {ticket_name} is CLOSED ({len(unique_slots)} slots)")
            else:
                logger.info(f"ℹ️ {ticket_name} still AVAILABLE - no alert needed")
            
            # Update cache
            if should_alert:
                 # Set cooldown immediately to prevent duplicate alerts
                 cache.set(alert_cooldown_key, "sent", timeout=3600)  # 1 hour cooldown
            
            cache.set(last_slot_count_key, current_slot_count, timeout=86400) # Keep count for 24h
            
            # ✅ FIXED: Send notification only if should_alert is True
            if should_alert and task.notification_mode != 'silent':
                try:
                    from .notification_utils import format_vatican_notification, send_telegram_signal
                    from .models import TelegramGroup
                    
                    # Get all approved groups for this agency
                    approved_groups = TelegramGroup.objects.filter(
                        agency=task.agency,
                        status='approved',
                        notification_enabled=True
                    )
                    
                    if approved_groups.exists():
                        # Send availability alert
                        message = format_vatican_notification(
                            date=date,
                            ticket_name=ticket_name,
                            ticket_id=str(fresh_id),  # ✅ Use fresh ID
                            slots=unique_slots,
                            preferred_times=task.preferred_times if hasattr(task, 'preferred_times') else None,
                            language=language,
                            visitors=task.visitors,
                            check_method="search-api"  # ✅ Updated method name
                        )
                        
                        # Send to all approved groups
                        sent_count = 0
                        for group in approved_groups:
                            if send_telegram_signal(group.chat_id, message):
                                sent_count += 1
                        
                        logger.info(f"✅ TELEGRAM NOTIFICATION sent to {sent_count}/{approved_groups.count()} groups for {task.agency.name}")
                    
                    # Fallback: Also send to legacy telegram_chat_id if set and no groups
                    elif task.agency.telegram_chat_id:
                        message = format_vatican_notification(
                            date=date,
                            ticket_name=ticket_name,
                            ticket_id=str(fresh_id),  # ✅ Use fresh ID
                            slots=unique_slots,
                            preferred_times=task.preferred_times if hasattr(task, 'preferred_times') else None,
                            language=language,
                            visitors=task.visitors,
                            check_method="search-api"  # ✅ Updated method name
                        )
                        send_telegram_signal(task.agency.telegram_chat_id, message)
                        logger.info(f"✅ TELEGRAM NOTIFICATION sent to legacy chat_id for {task.agency.name}")
                    else:
                        logger.warning(f"⚠️ No approved Telegram groups found for agency {task.agency.name}")
                        
                except Exception as e:
                    logger.error(f"❌ Notification failed: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
        
        logger.info(f"✅ Search API check complete: {ticket_name} - Found {len(unique_slots)} slots")
        return f"Search API Checked {ticket_name} - Found {len(unique_slots)} slots"
        
    except Exception as e:
        logger.error(f"Search API monitor failed: {e}")
        # Fallback to browser mode on error
        if use_browser_fallback:
            logger.info("Falling back to browser mode due to error")
            return run_smart_vatican_monitor(date, ticket_id, ticket_name, language, task_ids, visitors)
        return f"Failed: {str(e)}"


@shared_task(name="run_shared_vatican_monitor", queue="vatican")

def run_shared_vatican_monitor(ticket_type, language, dates):
    """
    OPTIMIZED: Checks a list of dates for a specific configuration
    and updates ALL matching tasks in the database.
    """
    try:
        # Resolve Pattern Name based on Type
        # Type 0 = Standard -> "Admission"
        # Type 1 = Guided -> "Guided" (or specific name if we had it, but shared monitor is generic)
        name_pattern = "Admission" if ticket_type == 0 else "Guided"
        
        # Use HydraBot for check
        bot = HydraBot(use_proxies=True)
        bot.target_dates = dates
        
        logger.info(f"🐉 HYDRA SHARED: Checking {len(dates)} dates (Type: {ticket_type}, Lang: {language}, Pattern: {name_pattern})")
        
        # Determine language for bot
        # Standard tickets (type 0) should have None, guided tours (type 1) use specified language
        bot_lang = language if ticket_type == 1 else None 
        
        import asyncio
        # Pass name_pattern to bot
        results = asyncio.run(bot.run_once(ticket_type=ticket_type, language=bot_lang, name_pattern=name_pattern))
        
        # Process Results & Update Tasks
        # ... (rest of logic) ...
        # Match date format reliably (Handle ISO vs DD/MM/YYYY)
        # ... (omitted for brevity, keeping existing logic) ...
        
        # Find tasks
        from django.db.models import Q
        # ... (query construction) ...
        
        # Use Q expressions for multiple variants
        # Re-construct query since we are replacing the block
        date_query = Q()
        for d in dates: # Broad query for any date in the batch
             date_query |= Q(dates__icontains=d)
             # Also add variants just in case
             if "-" in d:
                 try:
                     from datetime import datetime
                     dt = datetime.strptime(d, "%Y-%m-%d")
                     date_query |= Q(dates__icontains=dt.strftime("%d/%m/%Y"))
                 except: pass

        matching_tasks = MonitorTask.objects.filter(
            date_query,
            site='vatican', 
            ticket_type=ticket_type,
            is_active=True
        )
        
        if ticket_type == 1:
            matching_tasks = matching_tasks.filter(language__iexact=language)
        
        logger.info(f"📝 Found {matching_tasks.count()} tasks for {dates}...")
        
        # Aggregation
        task_updates = {} 

        for date_str, rich_items in results.items():
            # ... (date format matching logic repeated for specific result key) ...
            target_tasks = matching_tasks # Simplified scope

            for task in target_tasks:
                 # Check if this task cares about this date
                 # This logic is a bit loose in original code (it checked all matching tasks against all results)
                 # We can refine:
                 task_wants_date = False
                 for d in task.dates:
                     if date_str in d or d in date_str: # Simple contains check
                         task_wants_date = True
                         break
                 if not task_wants_date: continue

                 if task.id not in task_updates:
                    task_updates[task.id] = {
                        'task': task,
                        'updates': {}
                    }
                 
                 task_updates[task.id]['updates'][date_str] = rich_items
                 
                 # Dynamic ID update (InMemory only, avoiding persistence trap)
                 if rich_items:
                     best = rich_items[0]
                     # We can update the DB specifically if we want dashboard to show it,
                     # but we should NOT rely on it for dispatch.
                     # User said: "Stop treating ID as Constant".
                     # So let's update it for visibility, but our dispatch logic (orchestrate)
                     # should NOT use it.
                     if task.ticket_id != best['id']:
                         task.ticket_id = best['id']
                         task.ticket_name = best.get('name')
                         # We save it, but we won't use it for dispatch anymore.
                 
                 has_slots = any(len(i['slots']) > 0 for i in rich_items)
                 status = 'available' if has_slots else 'sold_out'
                 
                 task.last_checked = timezone.now()
                 task.last_status = status
                 
                 if status == 'available' or task.last_status != 'available':
                        CheckResult.objects.create(
                            task=task,
                            status=status,
                            details={date_str: rich_items},
                        )
                 task.save()
                 
        # Notifications (same as before)

        # Send Notifications for each Task
        for tid, data in task_updates.items():
            task = data['task']
            updates = data['updates'] # Map: date -> rich_list
            
            # Check if ANY available slots found
            found_any = False
            for d, rich_list in updates.items():
                # rich_list is [{slots:[], ...}, ...]
                for item in rich_list:
                    if item.get('slots'):
                        found_any = True
                        break
                if found_any: break
            
            # SPAM PREVENTION LOGIC
            # We sort keys and hash the content to see if it EXACTLY matches the last notification
            current_hash = "none"
            try:
                import hashlib
                # Create a canonical string representation of updates
                # e.g. "2026-05-25:09:00,09:30|2026-05-26:10:00"
                # Sort dates
                sorted_dates = sorted(updates.keys())
                content_str = ""
                for d in sorted_dates:
                    rich_list = updates[d]
                    # Sort items by name to be deterministic
                    # rich_list.sort(key=lambda x: x.get('name', '')) # Optional
                    
                    for item in rich_list:
                         s_list = item.get('slots', [])
                         if s_list:
                             sorted_slots = sorted(s_list)
                             content_str += f"{d}:{item.get('name')}:{','.join(sorted_slots)}|"
                
                # Create MD5 of this content
                current_hash = hashlib.md5(content_str.encode()).hexdigest()
                
                # Check against last stored hash (we need a place to store it)
                # We can store it in 'last_result_summary' or a new field.
                # Since 'last_result_summary' is JSON, we can add a field there.
                
                prev_summary = {}
                if task.last_result_summary:
                    try:
                        prev_summary = json.loads(task.last_result_summary)
                    except:
                        pass
                
                last_notified_hash = prev_summary.get('_notified_hash')
                
                # If exact duplicate of what we LAST NOTIFIED, skip (unless 'always' mode?)
                # User complaint: "bot is spamming". So we SKIP.
                # Only if found_any is True (we don't spam 'sold_out' anyway usually)
                if found_any and current_hash == last_notified_hash:
                    logger.info(f"🔕 Skipping duplicate notification for Task {task.id} (Hash match)")
                    
                    # Even if we skip, we should probably update the summary with latest time?
                    # But if we update summary, we MUST keep the hash.
                    prev_summary['last_updated'] = str(timezone.now())
                    task.last_result_summary = json.dumps(prev_summary)
                    task.save(update_fields=['last_result_summary'])
                    continue
                
                # Update hash in DB (even if we don't notify below, we should track state)
                # But typically we update it AFTER sending notification.
            except Exception as e:
                logger.error(f"Hash calc failed: {e}")
                current_hash = "error"
            
            if found_any and task.notification_mode != 'silent':
                # Build Message
                msg = f"⛪ *VATICAN FOUND!* ({task.area_name})\n"
                
                # Helper for Link Generation
                def get_vatican_link(d_str, t_type):
                     try:
                         from zoneinfo import ZoneInfo
                         from datetime import datetime
                         rome = ZoneInfo("Europe/Rome")
                         if "/" in d_str:
                             dt = datetime.strptime(d_str, "%d/%m/%Y")
                         else:
                             dt = datetime.strptime(d_str, "%Y-%m-%d")
                         midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=rome)
                         ts = int(midnight.timestamp() * 1000)
                         tag_id = 3 if t_type == 0 else 2
                         tag = "MV-Biglietti" if t_type == 0 else "MV-Visite-Guidate"
                         return f"https://tickets.museivaticani.va/home/fromtag/{tag_id}/{ts}/{tag}/1"
                     except:
                         return "https://tickets.museivaticani.va/"

                user_prefs = task.preferred_times or []
                
                for date, rich_list in updates.items():
                    # Only show if slots exist
                    for item in rich_list:
                         slots = item.get('slots', [])
                         if not slots: continue
                         
                         name = item.get('name', 'Unknown Ticket')
                         # Pass available ID for direct link
                         t_id = item.get('id', task.ticket_id)
                         link = get_vatican_link(date, task.ticket_type, t_id)
                         
                         # Check strictly for preferred times
                         found_prefs = []
                         missing_prefs = []
                         
                         for p in user_prefs:
                             # Check if any slot exactly matches or starts with preference
                             # e.g. "13:30" matches "13:30" or "13:30:00"
                             match = next((s for s in slots if s.startswith(p)), None)
                             if match:
                                 found_prefs.append(match)
                             else:
                                 missing_prefs.append(p)
                         
                         # Construct Message Header based on Preferences
                         if found_prefs:
                             msg += f"✅ **PREFERRED TIME FOUND!**\n"
                             for fp in found_prefs:
                                 msg += f"   • {fp}\n"
                         elif user_prefs:
                             msg += f"❌ Preferred times ({', '.join(missing_prefs)}) are SOLD OUT.\n"
                         
                         msg += f"\n📅 *{date}*: {name}\n"
                         
                         # List all slots (highlighted)
                         formatted_slots = []
                         slots.sort()
                         for s in slots:
                             if s in found_prefs:
                                 formatted_slots.append(f"**{s}**") # Bold
                             else:
                                 formatted_slots.append(s)
                                 
                         slot_str = ", ".join(formatted_slots[:25])
                         if len(formatted_slots) > 25: slot_str += "..."
                         
                         msg += f"⏰ All Slots: {slot_str}\n"
                         msg += f"🔗 [Book Now]({link})\n"
                
                send_telegram_signal(task.agency.telegram_chat_id, msg)
                
            # Update Summary with NEW Hash and Content (Always, if found_any)
            # This ensures dashboard shows latest info AND hash is saved for next comparison.
            if found_any:
                try:
                     summary_data = {
                         "updates": updates,
                         "_notified_hash": current_hash,
                         "last_updated": str(timezone.now())
                     }
                     task.last_result_summary = json.dumps(summary_data)
                     task.save(update_fields=['last_result_summary'])
                except Exception as e:
                    logger.error(f"Failed to save summary: {e}")

        return f"Shared Check Completed and Notified for {len(dates)} dates"

    except Exception as e:
        logger.error(f"Error in run_shared_vatican_monitor: {e}")
        return str(e)

def send_telegram_signal(chat_id, message):
    try:
        from .models import TelegramGroup
        group = TelegramGroup.objects.filter(chat_id=str(chat_id)).first()
        if group and not group.notification_enabled:
            logger.info(f"🔕 Notifications disabled for group: {chat_id}")
            return
    except Exception:
        pass
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        logger.error("No TELEGRAM_BOT_TOKEN configured")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        py_requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
        logger.info(f"Telegram signal sent to {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send Telegram signal: {e}")


@shared_task(name="resolve_and_check_task", queue="vatican")
def resolve_and_check_task(task_id):
    """
    ✅ REQUIRED: Resolves ticket_id for a task that doesn't have one, then checks it.
    
    This function is MANDATORY for tasks without ticket_id.
    Tasks will NOT be checked until they have a valid ticket_id.
    
    Flow:
    1. Check if task already has ticket_id → if yes, just check it
    2. If no ticket_id → resolve from Vatican website (REQUIRED)
    3. Save ticket_id to database
    4. Check the task using the resolved ID
    """
    try:
        # ✅ Clear the queue lock at the start
        queue_key = f"resolving:{task_id}"
        cache.delete(queue_key)
        
        task = MonitorTask.objects.get(id=task_id)

        # ✅ Normalize and validate date before anything else
        if not task.dates:
            logger.warning(f"⚠️ Task #{task_id} has no dates - skipping")
            return f"Skipped: no dates"

        date_normalized = normalize_date(task.dates[0])
        if not date_normalized:
            logger.info(f"⏭️ Task #{task_id} date '{task.dates[0]}' is past or invalid - skipping")
            # Mark as closed (not error) so dashboard doesn't show red
            task.last_status = 'closed'
            task.save(update_fields=['last_status'])
            return f"Skipped: past date {task.dates[0]}"

        if task.ticket_id:
            # Already has ID, just check it
            logger.info(f"✅ Task #{task_id} already has ticket_id, checking directly")
            return run_god_tier_vatican_monitor(
                date=date_normalized,
                ticket_id=task.ticket_id,
                ticket_name=task.ticket_name,
                language=task.language,
                task_ids=[task_id],
                visitors=task.visitors
            )
        
        logger.info(f"🔍 RESOLVING ticket_id for Task #{task_id}: {task.ticket_name} (REQUIRED)")
        
        # Use HydraBot to resolve fresh ID
        from worker_vatican.hydra_monitor import HydraBot
        import asyncio
        
        async def resolve_id():
            bot = HydraBot(use_proxies=True)
            async with bot.get_browser() as browser:
                page = await browser.new_page()
                
                # ✅ Normalize date format (handles YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY)
                date_formatted = normalize_date(task.dates[0])
                if not date_formatted:
                    await page.close()
                    return None  # Past or invalid date - skip silently
                
                # Resolve all IDs
                resolved_ids = await bot.resolve_all_dynamic_ids(
                    page,
                    ticket_type=task.ticket_type,
                    target_date=date_formatted,
                    visitors=task.visitors
                )
                
                await page.close()
                
                # Match by name (same logic as in tasks.py)
                ticket_name = task.ticket_name
                
                # Strategy 1: Exact match
                for item in resolved_ids:
                    r_name = item.get('name', '').lower()
                    t_name = ticket_name.lower()
                    
                    if t_name in r_name or r_name in t_name:
                        if task.ticket_type == 0 and "lunch" in r_name:
                            continue
                        return item['id']
                
                # Strategy 2: Keyword match
                keywords = []
                t_lower = ticket_name.lower()
                
                if 'musei' in t_lower:
                    keywords.extend(['musei', 'vaticani', 'aree', 'museali'])  # ✅ FIXED: Added 'aree', 'museali'
                elif 'palazzo' in t_lower:
                    keywords.extend(['palazzo', 'papale'])
                elif 'specola' in t_lower:
                    keywords.extend(['specola', 'vaticana'])
                
                if 'biglietti' in t_lower or 'admission' in t_lower or 'ingresso' in t_lower:
                    keywords.extend(['biglietti', 'ingresso'])
                if 'visita' in t_lower or 'guided' in t_lower or 'tour' in t_lower:
                    keywords.extend(['visita', 'guidata'])
                
                best_match = None
                best_score = 0
                
                for item in resolved_ids:
                    r_name = item.get('name', '').lower()
                    score = sum(1 for kw in keywords if kw in r_name)
                    
                    # CRITICAL: Venue exclusions
                    if 'musei' in t_lower and 'palazzo' in r_name:
                        continue
                    if 'palazzo' in t_lower and 'musei' in r_name:
                        continue
                    
                    if task.ticket_type == 0 and any(x in r_name for x in ['lunch', 'pranzo', 'pellegrinaggi']):
                        continue
                    
                    if score > best_score:
                        best_score = score
                        best_match = item['id']
                
                if best_match and best_score >= 2:
                    return best_match
                
                # Strategy 3: Fallback to first standard ticket
                if task.ticket_type == 0:
                    for item in resolved_ids:
                        r_name = item.get('name', '').lower()
                        # ✅ IMPROVED: Also check for "aree museali" and "ingresso" patterns
                        if any(x in r_name for x in ['biglietti', 'ingresso', 'aree museali', 'museali']):
                            # ✅ CRITICAL: Exclude wrong venues
                            if not any(x in r_name for x in ['lunch', 'pranzo', 'pellegrinaggi', 'gruppi', 'palazzo', 'specola']):
                                return item['id']
                
                return None
        
        # Run resolution
        fresh_id = asyncio.run(resolve_id())
        
        if fresh_id:
            # Update task with fresh ID
            task.ticket_id = fresh_id
            task.save(update_fields=['ticket_id'])
            logger.info(f"✅ Resolved and saved ticket_id {fresh_id} for Task #{task_id}")
            
            # Now check the task using the smart path
            return run_god_tier_vatican_monitor(
                date=date_normalized,
                ticket_id=fresh_id,
                ticket_name=task.ticket_name,
                language=task.language,
                task_ids=[task_id],
                visitors=task.visitors
            )
        else:
            logger.warning(f"⚠️ Could not resolve ticket_id for Task #{task_id} - will retry next cycle")
            # Don't set error - just leave status as-is and retry next orchestration cycle
            return f"Skipped: Could not resolve ticket_id for task {task_id} - will retry"
            
    except Exception as e:
        logger.error(f"Error in resolve_and_check_task: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return f"Failed: {str(e)}"


def _get_task_priority(task):
    """
    Calculate priority for a task based on day of week.
    High priority days (Fri, Sat, Mon, Thu) get shorter intervals.
    
    Returns: priority_multiplier (0.5 for high priority, 1.0 for normal)
    """
    if not task.dates:
        return 1.0
    
    try:
        # Check first date in task
        date_str = task.dates[0]
        date = normalize_date(date_str)
        if not date:
            return 1.0
        
        # Parse DD/MM/YYYY
        day, month, year = date.split('/')
        dt = datetime(int(year), int(month), int(day))
        weekday = dt.weekday()  # 0=Monday, 6=Sunday
        
        # High priority: Friday(4), Saturday(5), Monday(0), Thursday(3)
        if weekday in [0, 3, 4, 5]:
            return 0.5  # Check 2x more frequently
        else:
            return 1.0  # Normal frequency
    except Exception:
        return 1.0


@shared_task(name="orchestrate_all_tasks")
def orchestrate_all_tasks():
    """
    ✅ ULTRA-OPTIMIZED: Groups tasks by (date, ticket_id, language, visitors) for maximum efficiency.
    ✅ PRIORITY-BASED: High-demand days (Fri, Sat, Mon, Thu) checked 2x more frequently.
    
    Example: If 5 agencies want the same ticket/date/language, we check ONCE and notify all 5.
    """
    now = timezone.now()
    active_tasks = MonitorTask.objects.filter(is_active=True)
    
    # ✅ NEW GROUPING STRUCTURE
    # Key: (date, ticket_id, language, visitors) → List of task IDs
    smart_groups = {}
    
    # Tasks that need immediate ID resolution (blocking)
    tasks_needing_id = []
    
    for task in active_tasks:
        # User defined interval or default 120s (Optimized)
        interval_seconds = getattr(task, 'check_interval', 120)
        if not interval_seconds or interval_seconds < 60:
            interval_seconds = 60  # Force min 60s
        
        # ✅ PRIORITY ADJUSTMENT: High-demand days get 2x frequency
        priority_multiplier = _get_task_priority(task)
        adjusted_interval = int(interval_seconds * priority_multiplier)
        
        should_run = False
        if not task.last_checked:
            should_run = True
        else:
            elapsed = (now - task.last_checked).total_seconds()
            if elapsed >= adjusted_interval:
                should_run = True
                
        if should_run:
            if task.site == 'vatican' and task.dates:
                # ✅ CRITICAL: ALWAYS require ticket_id - resolve if missing
                if not task.ticket_id:
                    logger.warning(f"⚠️ Task #{task.id} has no ticket_id - will resolve immediately")
                    tasks_needing_id.append(task)
                else:
                    # Has ticket_id - add to smart groups
                    for raw_date in task.dates:
                        # ✅ Normalize date + skip past/invalid dates silently
                        date = normalize_date(raw_date)
                        if not date:
                            continue
                        # Group by EXACT combo including visitors
                        key = (date, task.ticket_id, task.language or None, task.visitors)
                        
                        if key not in smart_groups:
                            smart_groups[key] = {
                                'task_ids': [],
                                'ticket_name': task.ticket_name or 'Unknown Ticket',
                                'visitors': task.visitors,
                                'priority': priority_multiplier
                            }
                        
                        smart_groups[key]['task_ids'].append(task.id)
    
    # ✅ RESOLVE IDs FOR TASKS WITHOUT ticket_id (REQUIRED - NO SKIPPING)
    # These tasks MUST get a ticket_id before they can be checked
    if tasks_needing_id:
        logger.info(f"🔍 {len(tasks_needing_id)} tasks REQUIRE ticket_id resolution")
        for task in tasks_needing_id:
            # Skip if all dates are past
            valid_dates = [d for d in task.dates if normalize_date(d)]
            if not valid_dates:
                logger.info(f"⏭️ Task #{task.id} has no future dates - skipping resolution")
                continue

            # ✅ SPAM PREVENTION: Check if already queued (using Redis cache)
            queue_key = f"resolving:{task.id}"
            if cache.get(queue_key):
                logger.info(f"   Task #{task.id} already queued for resolution - skipping")
                continue
            
            # Mark as queued (expires in 5 minutes)
            cache.set(queue_key, "queued", timeout=300)
            
            # Queue a task to resolve ID and then check
            # This is REQUIRED - task won't be checked until ID is resolved
            resolve_and_check_task.apply_async(
                args=[task.id],
                queue='vatican',  # ✅ FIXED: Explicitly specify queue
                countdown=random.randint(5, 30)
            )
            logger.info(f"   Task #{task.id} ({task.dates[0] if task.dates else 'N/A'}) - queued for ID resolution")
                
    # ✅ DISPATCH SMART TASKS (New optimized method with priority)
    smart_count = 0
    high_priority_count = 0
    
    for (date, ticket_id, language, visitors), data in smart_groups.items():
        task_ids = data['task_ids']
        ticket_name = data['ticket_name']
        priority = data.get('priority', 1.0)
        
        if priority < 1.0:
            high_priority_count += 1
        
        # Jitter for anti-ban (shorter for high priority)
        if priority < 1.0:
            jitter = random.randint(2, 15)  # Faster dispatch for high priority
        else:
            jitter = random.randint(5, 30)
        
        # ✅ Dispatch based on configured mode
        if VATICAN_MONITOR_MODE == 'headless':
            # Ultra-fast headless mode only (no fallback)
            run_god_tier_vatican_monitor.apply_async(
                args=[date, ticket_id, ticket_name, language, task_ids, visitors],
                kwargs={'use_browser_fallback': False},
                countdown=jitter
            )
        elif VATICAN_MONITOR_MODE == 'browser':
            # Legacy browser mode
            run_smart_vatican_monitor.apply_async(
                args=[date, ticket_id, ticket_name, language, task_ids, visitors],
                countdown=jitter
            )
        else:  # 'hybrid' (default)
            # Try headless first, fallback to browser if needed
            run_god_tier_vatican_monitor.apply_async(
                args=[date, ticket_id, ticket_name, language, task_ids, visitors],
                kwargs={'use_browser_fallback': True},
                countdown=jitter
            )
        
        smart_count += 1
        priority_label = "⚡HIGH" if priority < 1.0 else "NORMAL"
        logger.info(f"📊 [{priority_label}] Smart Group: {date}/{ticket_id}/{language}/{visitors}v → {len(task_ids)} agencies")

    total_checks = smart_count + len(tasks_needing_id)
    logger.info(
        f"✅ Orchestration Complete: {smart_count} smart checks "
        f"({high_priority_count} high priority) + {len(tasks_needing_id)} ID resolutions"
    )
    
    return f"Queued {smart_count} smart checks ({high_priority_count} high priority), {len(tasks_needing_id)} ID resolutions."
@shared_task(name="cleanup_old_results")
def cleanup_old_results():
    """
    Delete CheckResult records older than 7 days to save space.
    Runs daily via Celery Beat.
    """
    days_to_keep = 7
    cutoff_date = timezone.now() - timedelta(days=days_to_keep)
    
    deleted_count, _ = CheckResult.objects.filter(check_time__lt=cutoff_date).delete()
    
    logger.info(f"🧹 Cleanup: Deleted {deleted_count} results older than {days_to_keep} days.")
    return f"Deleted {deleted_count} old results"

@shared_task(name="cleanup_expired_monitor_tasks")
def cleanup_expired_monitor_tasks():
    """
    ✅ ENHANCED: Removes dates/times from the past.
    - Removes past dates entirely
    - For today's date, removes times that have already passed
    - If a task has no future dates/times, it is deleted
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    # Use Rome timezone for Vatican tasks
    rome = ZoneInfo("Europe/Rome")
    now = timezone.now().astimezone(rome)
    now_date = now.date()
    now_time = now.time()
    
    tasks = MonitorTask.objects.all()
    cleaned_count = 0
    deleted_count = 0
    times_removed = 0
    
    for task in tasks:
        if not task.dates:
            continue
            
        # Filter dates
        new_dates = []
        changed = False
        
        for d_str in task.dates:
            try:
                # Handle formats
                if "/" in d_str:
                    dt = datetime.strptime(d_str, "%d/%m/%Y").date()
                elif "-" in d_str:
                    dt = datetime.strptime(d_str, "%Y-%m-%d").date()
                else:
                    continue 
                
                # Future date - keep it
                if dt > now_date:
                    new_dates.append(d_str)
                # Today's date - check preferred times
                elif dt == now_date:
                    # If task has preferred times, filter out past times
                    if task.preferred_times and len(task.preferred_times) > 0:
                        future_times = []
                        for time_str in task.preferred_times:
                            try:
                                # Parse time (format: "HH:MM" or "HH:MM:SS")
                                time_parts = time_str.split(':')
                                hour = int(time_parts[0])
                                minute = int(time_parts[1]) if len(time_parts) > 1 else 0
                                
                                task_time = datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()
                                
                                # Keep times that haven't passed yet (add 30 min buffer)
                                from datetime import timedelta as td
                                buffer_time = (datetime.combine(now_date, now_time) - td(minutes=30)).time()
                                
                                if task_time > buffer_time:
                                    future_times.append(time_str)
                                else:
                                    times_removed += 1
                                    logger.info(f"⏰ Removed past time {time_str} from Task #{task.id}")
                            except:
                                # Keep invalid time formats
                                future_times.append(time_str)
                        
                        # If there are still future times today, keep the date
                        if future_times:
                            task.preferred_times = future_times
                            new_dates.append(d_str)
                            changed = True
                        else:
                            # All times have passed, remove the date
                            changed = True
                            logger.info(f"📅 All times passed for today on Task #{task.id} - removing date")
                    else:
                        # No preferred times, keep today's date (might have slots later)
                        new_dates.append(d_str)
                # Past date - remove it
                else:
                    changed = True
            except:
                pass 
                
        if changed:
            if not new_dates:
                logger.info(f"🗑️ Task #{task.id} has no future dates/times. Deleting.")
                task.delete()
                deleted_count += 1
            else:
                task.dates = new_dates
                task.save()
                cleaned_count += 1
    
    logger.info(f"🧹 Cleanup: Updated {cleaned_count} tasks, Deleted {deleted_count} tasks, Removed {times_removed} past times")
    return f"Cleanup: Updated {cleaned_count} tasks, Deleted {deleted_count} tasks, Removed {times_removed} past times"


@shared_task(name="cleanup_backed_up_queues")
def cleanup_backed_up_queues():
    """
    ✅ NEW: Periodically checks and cleans backed-up Celery queues.
    Runs every hour to prevent queue overflow.
    
    Monitors:
    - vatican queue (should be < 100 tasks)
    - celery queue (should be < 200 tasks)
    
    If queue exceeds threshold, purges old tasks.
    """
    try:
        from django.core.cache import cache
        import redis
        
        # Connect to Redis
        redis_url = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
        r = redis.from_url(redis_url)
        
        # Define queue thresholds
        queue_thresholds = {
            'vatican': 100,
            'celery': 200
        }
        
        cleaned_queues = []
        
        for queue_name, threshold in queue_thresholds.items():
            try:
                queue_length = r.llen(queue_name)
                
                if queue_length > threshold:
                    logger.warning(f"⚠️ Queue '{queue_name}' backed up: {queue_length} tasks (threshold: {threshold})")
                    
                    # Purge the queue
                    r.delete(queue_name)
                    logger.info(f"🧹 Purged queue '{queue_name}' - removed {queue_length} tasks")
                    cleaned_queues.append(f"{queue_name}:{queue_length}")
                else:
                    logger.info(f"✅ Queue '{queue_name}' healthy: {queue_length} tasks")
            except Exception as e:
                logger.error(f"Error checking queue '{queue_name}': {e}")
        
        if cleaned_queues:
            return f"Cleaned queues: {', '.join(cleaned_queues)}"
        else:
            return "All queues healthy"
            
    except Exception as e:
        logger.error(f"Error in cleanup_backed_up_queues: {e}")
        return f"Failed: {str(e)}"

@shared_task(name="send_daily_summary")
def send_daily_summary():
    """
    Sends a daily summary report to all agencies with active monitors.
    Scheduled to run every morning.
    """
    try:
        from .notification_utils import send_telegram_signal
        
        # Group active tasks by agency
        active_tasks = MonitorTask.objects.filter(is_active=True)
        agencies = {}
        
        for task in active_tasks:
            if task.agency_id not in agencies:
                agencies[task.agency_id] = {
                    'agency': task.agency,
                    'tasks': []
                }
            agencies[task.agency_id]['tasks'].append(task)
            
        logger.info(f"📊 Generating daily summary for {len(agencies)} agencies")
        
        for agency_id, data in agencies.items():
            agency = data['agency']
            tasks = data['tasks']

            # ❌ DISABLED: daily summary notifications suppressed
            # Only slot monitoring sends to agencies
            continue
            
        return f"Sent summaries to {len(agencies)} agencies"
        
    except Exception as e:
        logger.error(f"Failed to send daily summary: {e}")
        return f"Failed: {str(e)}"
# 🚀 100-TICKET STRATEGY: NEW TASKS

@shared_task(name="run_deep_scan", queue="vatican")
def run_deep_scan(date, chat_id=None):
    """
    Perform a comprehensive scan across all visitor counts for a specific date.
    """
    try:
        engine = DeepDiscoveryEngine(target_date=date)
        results = engine.run()
        report = engine.format_report(results)
        
        if chat_id:
            from .notification_utils import send_telegram_signal
            send_telegram_signal(chat_id, report)
            
        return f"Deep scan for {date} complete."
    except Exception as e:
        logger.error(f"Deep scan failed: {e}")
        return f"Error: {e}"


@shared_task(name="run_bulk_discovery", queue="vatican")
def run_bulk_discovery(date_from, date_to, target_tickets=100):
    """
    Automated job to reach the ticket target using the fallback strategy.
    6px -> 4px -> 3px -> 2px.
    """
    from .tasks_bulk_hold import bulk_hold_scan
    from .models import BulkHoldConfig, Agency
    
    # This task effectively configures and triggers BulkHoldConfig objects
    # based on the 100-ticket goal.
    
    # For now, we reuse the existing bulk_hold_scan logic but ensure it's
    # triggered with the fallback strategy in mind.
    return bulk_hold_scan()


@shared_task(name="vatican_orchestrator")
def vatican_orchestrator():
    """System-wide orchestrator agent"""
    from .orchestrator import run_orchestration
    return run_orchestration()
