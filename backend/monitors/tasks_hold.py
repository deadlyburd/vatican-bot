"""
Hold Manager Celery Tasks — 3-Tier System
==========================================
Tier 1 — notify:  detect → Telegram alert → user books themselves
Tier 2 — hold:    detect → grab slot → send payment link → user pays in browser
Tier 3 — snipe:   detect → grab slot → auto-fill buyer details → auto-pay
"""
import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


@shared_task(name="keepalive_held_slots", queue="vatican")
def keepalive_held_slots():
    """Every 5 min — ping all active holds to keep Vatican sessions alive."""
    from .models import HeldSlot
    from .hold_manager import keepalive_slot
    import json

    active_holds = HeldSlot.objects.filter(status='held')
    if not active_holds.exists():
        return "No active holds"

    count = active_holds.count()
    logger.info(f"💓 Keepalive starting for {count} held slots")
    ok = expired = 0

    from django.core.cache import cache
    for hold in active_holds:
        # Skip holds that are paused (agent is about to click BUY)
        if cache.get(f'hold_recap_paused:{hold.id}'):
            logger.info(f"⏸️ Hold #{hold.id} recap paused — skipping keepalive (agent paying)")
            ok += 1
            continue
        age_h = hold.hold_duration_hours()
        if keepalive_slot(hold):
            try:
                notes = json.loads(hold.notes or '{}')
                if not isinstance(notes, dict):
                    notes = {}
            except Exception:
                notes = {}
            if notes.get('keepalive_failures'):
                notes.pop('keepalive_failures', None)
                hold.notes = json.dumps(notes) if notes else None
                hold.save(update_fields=['notes'])
            ok += 1
        else:
            try:
                notes = json.loads(hold.notes or '{}')
                if not isinstance(notes, dict):
                    notes = {}
            except Exception:
                notes = {}
            failures = int(notes.get('keepalive_failures') or 0) + 1
            notes['keepalive_failures'] = failures
            hold.notes = json.dumps(notes)
            # Expire after 5 failures (~25 min) OR if hold is >24h old
            if failures >= 5 or age_h >= 24:
                hold.status = 'expired'
                hold.save(update_fields=['status', 'notes'])
                expired += 1
                logger.warning(f"💀 Hold #{hold.id} expired (failures={failures}, age={age_h:.1f}h)")
            else:
                hold.save(update_fields=['notes'])
                logger.warning(f"⚠️ Hold #{hold.id} keepalive failure {failures}/5 (age={age_h:.1f}h)")

    logger.info(f"💓 Keepalive done: {ok} alive, {expired} expired out of {count}")
    return f"Keepalive: {ok} alive, {expired} expired"


@shared_task(name="auto_hold_slot", queue="snipe")
def auto_hold_slot(task_id, date, slot_id, slot_time, ticket_id, ticket_name, visitors):
    """
    Triggered when a slot opens.
    Routes to correct tier based on task.tier:
      notify → just send Telegram alert
      hold   → grab slot + send payment link
      snipe  → grab slot + auto-pay with stored buyer profile
    """
    from .models import MonitorTask, HeldSlot

    try:
        task = MonitorTask.objects.select_related('agency').get(id=task_id)
    except MonitorTask.DoesNotExist:
        logger.error(f"Task {task_id} not found")
        return "Task not found"

    tier = task.tier  # 'notify', 'hold', 'snipe'
    logger.info(f"🎯 Slot opened — tier={tier} | {date} {slot_time} | {task.agency.name}")

    if tier == 'notify':
        _send_notify_alert(task, date, slot_time, ticket_name, visitors)
        return f"Notified: {date} {slot_time}"

    # hold or snipe — both need to grab the slot first
    existing = HeldSlot.objects.filter(task=task, date=date, slot_id=slot_id, status='held').first()
    if existing:
        logger.info(f"⏭️ Already held: HeldSlot #{existing.id}")
        return f"Already held: #{existing.id}"

    from .hold_manager import hold_slot
    from .tasks_search_api import get_proxy_str
    proxy_str, _proxy_obj = get_proxy_str('vatican')
    held = hold_slot(
        task=task, date=date, slot_id=slot_id, slot_time=slot_time,
        ticket_id=ticket_id, ticket_name=ticket_name, visitors=visitors,
        proxy_str=proxy_str,
    )

    if not held:
        logger.error(f"❌ Hold failed — falling back to notify")
        _send_notify_alert(task, date, slot_time, ticket_name, visitors, hold_failed=True)
        return "Hold failed"

    if tier == 'hold':
        # Silent — no notification spam. Agency uses /book in Telegram bot.
        return f"Held #{held.id} | {date} {slot_time}"

    if tier == 'snipe':
        checkout_method = getattr(task, 'checkout_method', 'api')
        if checkout_method == 'playwright':
            # Push to browser_pending — local agent opens Chrome
            import base64 as _b64
            from django.core.cache import cache as _cache
            slot_info = _b64.b64encode(
                f"{date}|{slot_time}|{held.slot_id}|{held.visitors}|{held.total_price}|{held.adult_count}|{held.child_count}".encode()
            ).decode()
            job = {
                'data': f'open_browser:{held.id}:{slot_info}',
                'user': f'Auto-snipe task #{task.id}',
                'auto': True,
            }
            agent_target = getattr(task, 'agent_target', None)
            if agent_target:
                key = f'browser_pending_{agent_target}'
                q = _cache.get(key, [])
                q.insert(0, job)
                _cache.set(key, q, timeout=1800)
                logger.info(f"  📲 Browser job queued for agent '{agent_target}'")
            else:
                pending = _cache.get('browser_pending', [])
                pending.insert(0, job)
                _cache.set('browser_pending', pending, timeout=1800)
                logger.info(f"  📲 Browser job queued for any agent")
            return f"Playwright snipe queued: Hold #{held.id} | {date} {slot_time}"
        else:
            # API snipe — use 2captcha + card
            result = _attempt_snipe(task, held)
            return f"Snipe: {result}"

    return "Unknown tier"


def _send_notify_alert(task, date, slot_time, ticket_name, visitors, hold_failed=False):
    """Tier 1 — simple availability alert."""
    from .models import TelegramGroup
    from .notification_utils import send_telegram_signal
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo('Europe/Rome')).strftime('%H:%M:%S')
    warning = "\n⚠️ Auto-hold failed — book manually ASAP!" if hold_failed else ""

    msg = (
        f"🎉 TICKETS AVAILABLE!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 Date: {date}\n"
        f"⏰ Time: {slot_time}\n"
        f"🎫 {ticket_name}\n"
        f"👥 Visitors: {visitors}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{warning}\n"
        f"🔗 Book now:\n"
        f"https://tickets.museivaticani.va/home\n\n"
        f"🕐 Detected: {now} Rome time"
    )
    _send_to_groups(task, msg)


def _send_hold_notification(task, held):
    """Tier 2 — slot held, here's your payment link."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo('Europe/Rome')).strftime('%H:%M:%S')
    checkout_url = f"Hold #{held.id} ready - use API to generate payment link"

    msg = (
        f"🔒 SLOT HELD — PAY NOW!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 Date: {held.date}\n"
        f"⏰ Time: {held.slot_time}\n"
        f"🎫 {held.ticket_name}\n"
        f"👥 Visitors: {held.visitors}\n"
        f"💶 Total: €{held.total_price}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ Slot locked — nobody else can book it.\n\n"
        f"💳 Open this link to pay:\n"
        f"{checkout_url}\n\n"
        f"⚠️ Use this link directly — do NOT open Vatican site separately.\n\n"
        f"🕐 Held at: {now} Rome time | Hold ID: #{held.id}"
    )
    _send_to_groups(task, msg)


def _attempt_snipe(task, held):
    """
    Tier 3 — auto-pay using stored BuyerProfile.
    Needs: reCAPTCHA token (2captcha) + buyer profile.
    """
    from .models import BuyerProfile
    import requests

    # Check buyer profile exists
    try:
        profile = BuyerProfile.objects.get(agency=task.agency)
    except BuyerProfile.DoesNotExist:
        logger.error(f"❌ No BuyerProfile for {task.agency.name} — snipe aborted")
        _send_to_groups(task,
            f"⚠️ Snipe failed: No buyer profile set for {task.agency.name}.\n"
            f"Please set up buyer details to use snipe mode.\n"
            f"Hold #{held.id} is still active — pay manually via the link above."
        )
        return "No buyer profile"

    # Check card details
    if not profile.card_number:
        logger.error(f"❌ No card details for {task.agency.name} — snipe aborted")
        _send_to_groups(task,
            f"⚠️ Snipe failed: No card details stored.\n"
            f"Hold #{held.id} still active — pay manually."
        )
        return "No card details"

    # Get reCAPTCHA token
    recaptcha_token = _solve_recaptcha()
    if not recaptcha_token:
        logger.error("❌ reCAPTCHA solve failed — snipe aborted, hold still active")
        _send_to_groups(task,
            f"⚠️ Snipe failed: Could not solve reCAPTCHA.\n"
            f"Hold #{held.id} still active — pay manually via the checkout link."
        )
        return "reCAPTCHA failed"

    # Build reservation body — use epay SSL adapter so payment redirect works
    BASE = 'https://tickets.museivaticani.va'
    HEADERS = {
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': f'{BASE}/home/checkout',
        'Origin': BASE,
        'Content-Type': 'application/json',
    }

    from .epay_ssl import make_vatican_session
    s = make_vatican_session()
    s.cookies.set('JSESSIONID', held.jsessionid, domain='tickets.museivaticani.va')
    if held.ticketmv:
        s.cookies.set('ticketmv', held.ticketmv, domain='tickets.museivaticani.va')
    try:
        import json as _json
        notes = _json.loads(held.notes or '{}')
        if isinstance(notes, dict) and notes.get('serverid'):
            s.cookies.set('SERVERID', notes['serverid'], domain='tickets.museivaticani.va')
    except Exception:
        pass

    from .hold_manager import _get_services, _build_recap_body
    services = _get_services(s, held.slot_id, int(held.ticket_id), held.visitors)
    recap_body = _build_recap_body(held.slot_id, int(held.ticket_id), held.visitors, services)
    recap_r = s.post(f'{BASE}/api/visit/recap', json=recap_body, headers=HEADERS, timeout=15)
    if recap_r.status_code != 200:
        logger.error(f"Recap refresh failed for snipe: {recap_r.status_code} | {recap_r.text[:200]}")
        _send_to_groups(task, f"⚠️ Snipe failed: recap refresh failed ({recap_r.status_code}). Hold #{held.id} may be expired.")
        return f"Recap failed: {recap_r.status_code}"
    try:
        recap_data = recap_r.json()
        recap_id = recap_data.get('recapId') or recap_data.get('id') or ''
        if recap_id:
            held.recap_id = recap_id
            held.save(update_fields=['recap_id'])
    except Exception:
        pass

    service_ids = []
    if services:
        svc_id = services[0].get('id')
        if svc_id is not None:
            service_ids = [svc_id]

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
        "recaptcha": recaptcha_token,
        "lang": "it",
        "recapId": held.recap_id or '',
        "visitorNum": int(held.visitors),
        "visitId": held.slot_id,
        "visitTypeId": int(held.ticket_id),
        "tickets": [
            {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(held.adult_count)},
            {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": str(held.child_count)},
        ],
        "services": reservation_services,
        "representativeUser": profile.to_representative_user(),
        "participantUser": profile.to_participant_list(held.visitors, adult_count=held.adult_count, child_count=held.child_count, ticket_id=60, service_ids=service_ids),
        "gdpr": [{"id": 1, "check": True}, {"id": 3, "check": False}],
    }

    try:
        r = s.post(f'{BASE}/api/visit/reservation', json=body, headers=HEADERS, timeout=15)
        logger.info(f"Reservation response: {r.status_code} | {r.text[:300]}")

        if r.status_code == 200:
            res_data = r.json()
            # Vatican response: {"total":"2500","referenceOrder":"...","epay":{"url":"https://epay.catholica.va/..."}}
            epay_url = (
                res_data.get('epay', {}).get('url') or
                res_data.get('paymentUrl') or
                res_data.get('redirectUrl') or
                ''
            )
            held.status = 'paying'
            held.payment_url = epay_url or held.payment_url
            held.save(update_fields=['status', 'payment_url'])

            _send_to_groups(task,
                f"✅ RESERVATION CONFIRMED!\n\n"
                f"📅 {held.date} {held.slot_time}\n"
                f"👥 {held.visitors} visitors | €{held.total_price}\n\n"
                f"💳 Complete payment:\n{epay_url or held.payment_url}"
            )
            return f"Reservation OK — payment pending"
        else:
            logger.error(f"Reservation failed: {r.status_code} | {r.text[:200]}")
            _send_to_groups(task,
                f"⚠️ Auto-reservation failed ({r.status_code}).\n"
                f"Hold #{held.id} still active — pay manually."
            )
            return f"Reservation failed: {r.status_code}"

    except Exception as e:
        logger.error(f"Snipe exception: {e}")
        return f"Exception: {e}"


def _solve_recaptcha():
    """
    Get a Turnstile token — from pre-solved pool (instant) or live solve (30s).
    Uses the token pool to eliminate the 30-second bottleneck in the snipe flow.
    """
    from .turnstile_pool import get_token_sync
    return get_token_sync()


def _send_to_groups(task, msg):
    """
    Send message to all approved groups for this agency.
    DISABLED: Only slot monitoring notifications are allowed.
    Hold/snipe/payment notifications are suppressed.
    """
    # ❌ DISABLED: No hold/snipe/payment notifications to agencies
    # Only slot monitoring (run_smart_vatican_monitor / run_god_tier_vatican_monitor) sends notifications
    return


def snipe_with_dynamic_card(held_slot, card_details):
    """
    Complete payment with dynamically injected card details.
    This function processes the payment using the provided card details
    instead of stored profile data.
    """
    from .models import BuyerProfile
    import requests
    
    logger.info(f"🎯 Starting dynamic snipe for Hold #{held_slot.id}")
    
    # Validate card details
    required_fields = ['number', 'expiry', 'cvv']
    for field in required_fields:
        if not card_details.get(field):
            error_msg = f"Missing card field: {field}"
            logger.error(f"❌ {error_msg}")
            return error_msg
    
    # Get reCAPTCHA token
    recaptcha_token = _solve_recaptcha()
    if not recaptcha_token:
        error_msg = "reCAPTCHA solve failed"
        logger.error(f"❌ {error_msg}")
        return error_msg
    
    # Build reservation body using the held slot's session — epay SSL adapter required
    BASE = 'https://tickets.museivaticani.va'
    HEADERS = {
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': f'{BASE}/home/checkout',
        'Origin': BASE,
        'Content-Type': 'application/json',
    }
    
    # Create session with epay SSL adapter + held slot's cookies
    from .epay_ssl import make_vatican_session
    s = make_vatican_session(
        jsessionid=held_slot.jsessionid,
        ticketmv=held_slot.ticketmv if held_slot.ticketmv else None,
    )
    
    # Get profile for participant data (but use dynamic card)
    try:
        profile = BuyerProfile.objects.get(agency=held_slot.task.agency)
    except BuyerProfile.DoesNotExist:
        error_msg = "No buyer profile found for agency"
        logger.error(f"❌ {error_msg}")
        return error_msg
    
    # Build reservation payload
    body = {
        'recaptcha': recaptcha_token,
        'lang': 'it',
        'recapId': held_slot.recap_id or '',
        'visitorNum': held_slot.visitors,
        'visitId': held_slot.slot_id,
        'visitTypeId': int(held_slot.ticket_id) if held_slot.ticket_id.isdigit() else 0,
        'tickets': [
            {
                'id': int(held_slot.ticket_id) if held_slot.ticket_id.isdigit() else 60,
                'name': held_slot.ticket_name or 'Biglietto Intero',
                'price': 20.0,
                'quantity': str(held_slot.visitors)
            }
        ],
        'services': [
            {
                'id': 58,
                'name': 'Diritti di Prevendita',
                'price': 5.0,
                'quantity': held_slot.visitors
            }
        ],
        'representativeUser': {
            'surname': profile.last_name,
            'name': profile.first_name,
            'gender': profile.gender,
            'country': profile.country,
            'city': profile.city,
            'birthDate': profile.birth_date.isoformat() if profile.birth_date else '2000-01-01',
            'email': profile.email,
            'confirmEmail': profile.email,
            'telephoneNumber': profile.phone,
            'language': profile.language or 'it'
        },
        'participantUser': profile.to_participant_list(held_slot.visitors),
        'gdpr': [
            {'id': 1, 'check': True},
            {'id': 3, 'check': False}
        ]
    }
    
    try:
        # Make reservation
        r = s.post(f'{BASE}/api/visit/reservation', json=body, headers=HEADERS, timeout=15)
        logger.info(f"Reservation response: {r.status_code} | {r.text[:300]}")

        if r.status_code == 200:
            res_data = r.json()
            epay_url = (
                res_data.get('epay', {}).get('url') or
                res_data.get('paymentUrl') or
                res_data.get('redirectUrl') or
                ''
            )
            
            # Update held slot status
            held_slot.status = 'paying'
            held_slot.payment_url = epay_url or held_slot.payment_url
            held_slot.save(update_fields=['status', 'payment_url'])
            
            logger.info(f"✅ Reservation confirmed with dynamic card")
            return f"Reservation OK — payment pending at {epay_url}"
        else:
            error_msg = f"Reservation failed: {r.status_code} | {r.text[:200]}"
            logger.error(error_msg)
            return error_msg

    except Exception as e:
        error_msg = f"Snipe exception: {e}"
        logger.error(error_msg)
        return error_msg


@shared_task(name="rotate_hold_sessions", queue="vatican")
def rotate_hold_sessions():
    """
    Proactively rotate hold sessions before 24-hour Vatican expiry.
    Checks holds with < 4 hours remaining and refreshes their sessions.
    Runs every hour to catch holds nearing expiration.
    """
    from .models import HeldSlot
    from .hold_manager import _fresh_re_hold
    import json

    # Find holds with less than 4 hours remaining
    critical_holds = HeldSlot.objects.filter(status='held')
    critical_holds = [h for h in critical_holds if h.hours_until_expiry() < 4]

    if not critical_holds:
        return "No holds nearing expiry"

    logger.info(f"🔄 Session rotation for {len(critical_holds)} holds nearing expiry")
    rotated = failed = 0

    for hold in critical_holds:
        try:
            # Attempt fresh re-hold (updates existing hold in place)
            success = _fresh_re_hold(hold)
            if success:
                rotated += 1
                logger.info(f"✅ Session rotated: Hold #{hold.id}")
                
                # Update notes with rotation history
                notes = json.loads(hold.notes or '{}') if hold.notes else {}
                rotation_history = notes.get('rotation_history', [])
                rotation_history.append({
                    'rotated_at': timezone.now().isoformat(),
                    'hours_remaining': hold.hours_until_expiry(),
                    'session_refreshed': True
                })
                notes['rotation_history'] = rotation_history
                hold.notes = json.dumps(notes)
                hold.save(update_fields=['notes'])
            else:
                failed += 1
                logger.warning(f"❌ Session rotation failed for Hold #{hold.id}")

        except Exception as e:
            failed += 1
            logger.error(f"❌ Session rotation error for Hold #{hold.id}: {e}")

    return f"Session rotation: {rotated} rotated, {failed} failed"
