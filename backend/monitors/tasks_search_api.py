"""
Vatican Monitor Tasks — Extension-Driven Booking
=================================================
Flow:
  1. Bokun booking → Google Sheets (sync_bokun_to_sheets)
  2. Sheets → MonitorTask created (sync_sheets_to_monitoring)
  3. Orchestrator dispatches per-date checks every 5s
  4. When slot found → push to Redis 'extension_slots' cache
  5. Extension (3-4 Chrome windows) polls /api/v1/available-slots/ every 10s
  6. Extension opens Vatican, books ticket, captures ePay URL
  7. Extension calls /api/v1/slots/<id>/mark-booked/ with payment link
  8. Backend sends payment link to Telegram + updates Google Sheets

No API hold. No local_browser_agent. Extension does all booking.
"""

import logging
import json
import uuid
import requests
from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from django.core.cache import cache
from .models import MonitorTask, CheckResult

logger = logging.getLogger(__name__)

try:
    from worker_vatican.search_api_monitor import VaticanSearchAPIMonitor
except ImportError:
    VaticanSearchAPIMonitor = None
    logger.error("❌ VaticanSearchAPIMonitor not found!")


# ─────────────────────────────────────────────────────────────────────────────
# Redis key where detected slots are stored for the extension to poll
# ─────────────────────────────────────────────────────────────────────────────
EXTENSION_SLOTS_KEY = 'extension_slots'
EXTENSION_SLOT_TTL  = 600  # 10 minutes — extension must book within this window


def get_proxy_str(site='vatican'):
    """Pick a random active proxy. Read-only."""
    from .models import Proxy
    from django.db import models as dj_models

    now = timezone.now()
    proxy_obj = (
        Proxy.objects.filter(is_active=True)
        .filter(dj_models.Q(cooldown_until__isnull=True) | dj_models.Q(cooldown_until__lte=now))
        .order_by('?')
        .first()
    )
    if not proxy_obj:
        proxy_obj = Proxy.objects.filter(is_active=True).order_by('cooldown_until').first()
    if not proxy_obj:
        return None, None

    user = proxy_obj.username or ''
    if 'oxylabs' in proxy_obj.ip_port.lower() and user:
        import random
        user = f"{user}-session-{random.randint(10000, 99999)}"

    if user and proxy_obj.password:
        return f"http://{user}:{proxy_obj.password}@{proxy_obj.ip_port}", proxy_obj
    return f"http://{proxy_obj.ip_port}", proxy_obj


def _push_slots_for_extension(task, date, slots, ticket_id, ticket_name):
    """
    Push detected slots into Redis so the extension can pick them up.
    Each slot entry contains everything the extension needs to book:
      - date / time / ticket_id / ticket_name / visitors
      - participant names (from task or BuyerProfile)
      - profile (email, phone, etc.)
    Deduplicates by task_id + date + time so we don't flood the queue.
    """
    try:
        agency   = task.agency
        profile  = None
        participants = []

        # 1. Try task-level participants first
        if task.participants_json:
            try:
                participants = json.loads(task.participants_json)
            except Exception:
                pass

        # 2. Fall back to BuyerProfile
        if not participants:
            try:
                bp = agency.buyer_profile
                if bp.participants_json:
                    participants = json.loads(bp.participants_json)
                if not participants:
                    participants = [{'first_name': bp.first_name, 'last_name': bp.last_name}] * task.visitors
                profile = {
                    'first_name': bp.first_name,
                    'last_name':  bp.last_name,
                    'email':      bp.email,
                    'phone':      bp.phone,
                    'city':       getattr(bp, 'city', ''),
                    'country':    getattr(bp, 'country', 'IT'),
                }
            except Exception:
                pass

        # Load existing queue
        existing = cache.get(EXTENSION_SLOTS_KEY) or []

        # Dedup keys already in queue
        existing_keys = {
            f"{e['task_id']}:{e['date']}:{e['time']}"
            for e in existing
        }

        added = 0
        for s in slots:
            slot_time = s.get('time') if isinstance(s, dict) else s
            dedup_key = f"{task.id}:{date}:{slot_time}"
            if dedup_key in existing_keys:
                continue

            entry = {
                'id':           str(uuid.uuid4()),   # unique ID for the extension to reference
                'task_id':      task.id,
                'booking_id':   getattr(task, 'booking_id', ''),
                'date':         date,                # DD/MM/YYYY
                'time':         slot_time,           # HH:MM
                'ticket_id':    str(ticket_id or ''),
                'ticket_name':  ticket_name,
                'visitors':     task.visitors,
                'adult_count':  getattr(task, 'adult_count', task.visitors),
                'child_count':  getattr(task, 'child_count', 0),
                'language':     task.language or '',
                'participants': participants[:task.visitors],
                'profile':      profile or {},
                'agency_id':    agency.id,
                'detected_at':  timezone.now().isoformat(),
            }
            existing.append(entry)
            existing_keys.add(dedup_key)
            added += 1

        if added:
            cache.set(EXTENSION_SLOTS_KEY, existing, timeout=EXTENSION_SLOT_TTL)
            logger.info(f"📤 Pushed {added} slot(s) to extension queue for {date} (task #{task.id})")

    except Exception as e:
        logger.error(f"❌ _push_slots_for_extension failed: {e}")
        import traceback
        logger.error(traceback.format_exc())


# ─────────────────────────────────────────────────────────────────────────────
# Main monitor task
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(name="run_search_api_vatican_monitor", queue="vatican")
def run_search_api_vatican_monitor(date, ticket_id, ticket_name, language, task_ids, visitors=2):
    """
    Check Vatican API for a specific date/ticket combo.
    When slots are found → push to extension queue (no API hold).
    """
    try:
        logger.info(f"🔍 CHECK: {date} | {ticket_name} | visitors={visitors} | tasks={task_ids}")

        if not VaticanSearchAPIMonitor:
            return "Skipped: VaticanSearchAPIMonitor not available"

        # Proxy rotation — up to 3 attempts
        slots = []
        resolved_ticket_id = ticket_id
        status = 'sold_out'

        for attempt in range(3):
            proxy_str, proxy_obj = get_proxy_str('vatican')
            monitor = VaticanSearchAPIMonitor(proxy_str=proxy_str)
            ticket_type = 1 if language else 0

            try:
                success, slots, resolved_ticket_id = monitor.check_ticket(
                    target_date=date,
                    ticket_name=ticket_name,
                    visitors=visitors,
                    ticket_type=ticket_type,
                    language=language,
                )
                status = 'available' if slots else 'sold_out'
                break

            except requests.exceptions.Timeout:
                logger.warning(f"⚠️ Rate limited (attempt {attempt+1}/3)")
                if proxy_obj:
                    proxy_obj.cooldown_until = timezone.now() + timedelta(minutes=15)
                    proxy_obj.save()
                if attempt == 2:
                    return "Rate limited: all proxies exhausted"
                continue

            except Exception as e:
                logger.error(f"❌ Monitor error: {e}")
                return f"Error: {e}"

        # Process each task
        tasks = MonitorTask.objects.filter(id__in=task_ids).select_related('agency')

        for task in tasks:
            task.last_checked = timezone.now()
            task.last_status  = status

            # State change detection
            state_key = f"ticket_state:{task.id}:{date}"
            previous_state = cache.get(state_key)
            if isinstance(previous_state, bytes):
                previous_state = previous_state.decode()

            is_now_available       = bool(slots)
            was_available          = previous_state == 'available'
            is_first_check         = previous_state is None
            status_changed_to_open = is_now_available and not was_available

            cache.set(state_key, 'available' if is_now_available else 'closed', timeout=86400 * 7)

            # Save check result
            CheckResult.objects.create(
                task=task,
                status=status,
                details={
                    'date': date,
                    'ticket_id': ticket_id,
                    'effective_ticket_id': resolved_ticket_id,
                    'ticket_name': ticket_name,
                    'language': language,
                    'slots': slots,
                    'state_changed': status_changed_to_open,
                    'previous_state': previous_state,
                    'is_first_check': is_first_check,
                    'check_method': 'search_api',
                }
            )

            # Update summary
            try:
                task.last_result_summary = json.dumps({
                    "updates": {date: [{'id': resolved_ticket_id or ticket_id, 'name': ticket_name, 'slots': slots}]},
                    "last_updated": str(timezone.now()),
                })
            except Exception:
                pass
            task.save()

            # ── Only act on CLOSED → OPEN transition (or first check if already open) ──
            should_act = is_now_available and (status_changed_to_open or is_first_check)

            if not should_act:
                if not is_now_available:
                    logger.debug(f"🔒 {date}: closed")
                else:
                    logger.debug(f"ℹ️ {date}: still open — already queued")
                continue

            logger.info(f"🎉 {date}: OPEN — pushing {len(slots)} slot(s) to extension queue")

            # ── Push to extension queue ──
            _push_slots_for_extension(
                task=task,
                date=date,
                slots=slots,
                ticket_id=resolved_ticket_id or ticket_id,
                ticket_name=ticket_name,
            )

            # ── Telegram notification (state change only, not first check) ──
            if status_changed_to_open and not is_first_check and task.notification_mode != 'silent':
                _send_availability_alert(task, date, slots, ticket_name, resolved_ticket_id or ticket_id)

        return f"Checked {ticket_name} — {len(slots)} slots — tasks={len(task_ids)}"

    except Exception as e:
        logger.error(f"❌ run_search_api_vatican_monitor failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return f"Failed: {e}"


def _send_availability_alert(task, date, slots, ticket_name, ticket_id):
    """Send Telegram alert when slots open. No payment link — extension handles booking."""
    try:
        from .models import TelegramGroup
        from .notification_utils import format_vatican_notification, send_telegram_signal

        approved_groups = TelegramGroup.objects.filter(
            agency=task.agency,
            status='approved',
            notification_enabled=True,
        )
        targets = list(approved_groups.values_list('chat_id', flat=True))
        if not targets and task.agency.telegram_chat_id:
            targets = [task.agency.telegram_chat_id]
        if not targets:
            return

        message = format_vatican_notification(
            date=date,
            ticket_name=ticket_name,
            ticket_id=str(ticket_id),
            slots=slots,
            preferred_times=getattr(task, 'preferred_times', None),
            language=task.language,
            visitors=task.visitors,
            check_method="search_api",
        )

        for chat_id in targets:
            dedup = f"notified:{chat_id}:{date}"
            if cache.get(dedup):
                continue
            if send_telegram_signal(chat_id, message):
                cache.set(dedup, True, timeout=86400 * 7)

    except Exception as e:
        logger.error(f"❌ Telegram alert failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(name="instant_sniper_scan", queue="vatican")
def instant_sniper_scan():
    return orchestrate_vatican_tasks_search_api()


@shared_task(name="orchestrate_vatican_tasks_search_api", queue="vatican")
def orchestrate_vatican_tasks_search_api():
    """
    Groups active MonitorTasks by (date, ticket_name, language, visitors)
    and dispatches one check per unique combo.
    """
    try:
        logger.info("🎯 ORCHESTRATOR: Vatican task orchestration")

        tasks = MonitorTask.objects.filter(
            site='vatican',
            is_active=True,
        ).select_related('agency').prefetch_related('agency__telegram_groups')

        if not tasks.exists():
            return "No active tasks"

        task_groups = {}
        for task in tasks:
            dates_list = task.dates if isinstance(task.dates, list) else [task.dates]
            for raw_date in dates_list:
                from monitors.tasks import normalize_date
                date = normalize_date(raw_date)
                if not date:
                    continue
                key = (date, task.ticket_name, task.language, task.visitors)
                if key not in task_groups:
                    task_groups[key] = {
                        'date':        date,
                        'ticket_id':   task.ticket_id,
                        'ticket_name': task.ticket_name,
                        'language':    task.language,
                        'visitors':    task.visitors,
                        'task_ids':    [],
                    }
                task_groups[key]['task_ids'].append(task.id)

        # Seed missing Redis states as 'closed' to avoid silent first-check swallowing
        seeded = 0
        for group in task_groups.values():
            for tid in group['task_ids']:
                k = f"ticket_state:{tid}:{group['date']}"
                if cache.get(k) is None:
                    cache.set(k, 'closed', timeout=86400 * 7)
                    seeded += 1
        if seeded:
            logger.info(f"🌱 Seeded {seeded} missing Redis states as 'closed'")

        dispatched = 0
        for group in task_groups.values():
            try:
                run_search_api_vatican_monitor.delay(
                    date=group['date'],
                    ticket_id=group['ticket_id'],
                    ticket_name=group['ticket_name'],
                    language=group['language'],
                    task_ids=group['task_ids'],
                    visitors=group['visitors'],
                )
                dispatched += 1
            except Exception as e:
                logger.error(f"❌ Dispatch failed: {e}")

        logger.info(f"🎯 Dispatched {dispatched}/{len(task_groups)} checks for {tasks.count()} tasks")
        return f"Dispatched {dispatched} checks"

    except Exception as e:
        logger.error(f"❌ Orchestration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return f"Orchestration failed: {e}"
