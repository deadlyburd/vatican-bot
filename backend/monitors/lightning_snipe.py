"""
⚡ LIGHTNING SNIPE ENGINE
=========================
CONFIRMED FLOW (from live testing + reverse engineering):

KEY DISCOVERY: /api/visit/recap LOCKS the slot server-side for ~55 minutes.
  - After recap: other sessions see the slot as SOLD_OUT
  - Other sessions cannot recap the same slot (500 error)
  - This is a real server-side hold, not just a UI trick

STRATEGY:
  1. Search → fresh ticket_id + JSESSIONID          (~0.2s)
  2. Timeavail → find target slot                   (~0.2s)
  3. Recap → LOCKS the slot for ~55 min             (~0.2s) ← THE HOLD
  4. Solve Turnstile                                (~30s)  ← safe, slot is locked
  5. Reservation → get epay params                  (~1s)
  6. Generate payment link / auto-pay

Total time to lock: ~0.6s
Total time to complete: ~32s
Hold window: ~55 minutes
"""
import logging
import time
import json
import os
import secrets as _secrets
from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger(__name__)

BASE = 'https://tickets.museivaticani.va'
# Headers matching the exact working browser request from HAR capture
# CRITICAL: NO X-Requested-With header — Vatican rejects it on reservation
H = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Chromium";v="123", "Google Chrome";v="123", "Not-A.Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'Origin': BASE,
    'Content-Type': 'application/json',
}
# For search/timeavail/services — these use XHR so X-Requested-With is OK
H_XHR = {**H, 'X-Requested-With': 'XMLHttpRequest', 'Referer': f'{BASE}/'}
# For recap and reservation — match exact browser headers
HC = {**H, 'Referer': f'{BASE}/home/checkout'}


def lightning_snipe(task, date: str, slot_id: str, slot_time: str,
                    ticket_id: str, ticket_name: str, visitors: int) -> dict:
    """
    ⚡ Snipe flow:
    1. Search + timeavail  (~0.4s)
    2. Recap               (~0.2s) ← SLOT LOCKED for ~55 min
    3. Solve Turnstile     (~30s)  ← safe, nobody can steal the slot
    4. Reservation         (~1s)   ← get epay params
    5. Notify / pay
    """
    from .epay_ssl import make_vatican_session
    from .models import BuyerProfile, HeldSlot, TelegramGroup
    from .notification_utils import send_telegram_signal
    from .turnstile_pool import get_token_sync, return_unused_token
    from datetime import datetime
    from zoneinfo import ZoneInfo

    t0 = time.monotonic()
    def ms(): return int((time.monotonic() - t0) * 1000)

    logger.info(f"⚡ SNIPE: {date} {slot_time} | {visitors}v")

    # Profile
    try:
        profile = BuyerProfile.objects.get(agency=task.agency)
    except BuyerProfile.DoesNotExist:
        return {'success': False, 'error': 'No buyer profile', 'elapsed_ms': ms()}

    s = make_vatican_session()

    # Quantities
    adult_count = getattr(task, 'adult_count', visitors)
    child_count = getattr(task, 'child_count', 0)
    total_visitors = adult_count + child_count

    # ── 1. Search → fresh ticket_id + JSESSIONID ──────────────────────────────
    try:
        r = s.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(total_visitors), 'visitDate': date,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=H_XHR, timeout=8)
        if r.status_code != 200:
            return {'success': False, 'error': f'Search {r.status_code}', 'elapsed_ms': ms()}
        t = next((v for v in r.json().get('visits', [])
                  if 'musei vaticani' in v.get('name', '').lower()
                  and 'ingresso' in v.get('name', '').lower()), None)
        tid = int(t['id']) if t else int(ticket_id)
        logger.info(f"  [{ms()}ms] Search: ticket_id={tid}")
    except Exception as e:
        return {'success': False, 'error': f'Search: {e}', 'elapsed_ms': ms()}

    # ── 2. Fresh timeavail → get current slot IDs ─────────────────────────────
    # CRITICAL: Get fresh slot IDs right now — don't use stale ones from detection
    fresh_slots = []
    try:
        r2 = s.get(f'{BASE}/api/visit/timeavail', params={
            'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
            'visitorNum': str(visitors), 'visitDate': date,
        }, headers=H_XHR, timeout=8)
        if r2.status_code == 200:
            fresh_slots = [
                sl for sl in r2.json().get('timetable', [])
                if sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')
            ]
            logger.info(f"  [{ms()}ms] Timeavail: {len(fresh_slots)} slots available")
    except Exception as e:
        logger.warning(f"  Timeavail failed: {e}")

    # Build slot priority: requested slot first, then others
    def slot_key(sl):
        return (0 if str(sl.get('id')) == str(slot_id) else 1, sl.get('time', ''))
    fresh_slots.sort(key=slot_key)

    # If timeavail failed or empty, fall back to the original slot_id
    if not fresh_slots:
        fresh_slots = [{'id': slot_id, 'time': slot_time}]

    # ── 3. Services ───────────────────────────────────────────────────────────
    services = []
    try:
        r_svc = s.get(f'{BASE}/api/visit/services', params={
            'lang': 'it', 'visitId': str(fresh_slots[0]['id']),
            'visitTypeId': tid, 'visitorNum': str(visitors)
        }, headers=H_XHR, timeout=6)
        if r_svc.status_code == 200:
            services = r_svc.json().get('services', [])
    except Exception:
        pass

    # ── 4. Recap — try each fresh slot until one succeeds ─────────────────────
    recap_id = total_price = working_slot_id = None

    for sl in fresh_slots:
        sid = str(sl.get('id', ''))
        if not sid:
            continue

        # Fixed quantity mapping
        body = {
            "visitId": sid,
            "visitTypeId": int(tid),
            "visitorNum": int(total_visitors),
            "lang": "it",
            "tickets": [
                {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(adult_count)},
                {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": str(child_count)},
            ],
            "additionalCosts": {
                "service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(total_visitors)}
            },
            "services": [
                {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(total_visitors)}
            ]
        }

        try:
            rr = s.post(f'{BASE}/api/visit/recap', json=body, headers=HC, timeout=10)
            if rr.status_code == 200:
                d = rr.json()
                recap_id = d.get('recapId') or d.get('id') or ''
                total_price = d.get('total', 0)
                working_slot_id = sid
                logger.info(f"  [{ms()}ms] 🔒 SLOT LOCKED via recap: {sid} → {recap_id} €{total_price} (~55 min hold)")
                break
            else:
                logger.debug(f"  Recap {rr.status_code} for {sid}: {rr.text[:100]}")
        except Exception as e:
            logger.debug(f"  Recap exception {sid}: {e}")

    if not recap_id:
        return {
            'success': False,
            'error': f'Recap failed for all {len(fresh_slots)} slots — all sold out',
            'elapsed_ms': ms()
        }

    # ── 5. Turnstile token (only needed for API method) ──────────────────────
    checkout_method = getattr(task, 'checkout_method', 'api')
    token = None

    if checkout_method == 'api':
        token = get_token_sync()
        if not token:
            return {'success': False, 'error': 'No Turnstile token available', 'elapsed_ms': ms()}
        logger.info(f"  [{ms()}ms] Token ready (prefix={token[:2]} len={len(token)})")
    else:
        logger.info(f"  [{ms()}ms] Playwright method — no token needed")

    # ── 6. Build participant list from task.participants_json ─────────────────
    # tier='notify' never reaches here. tier='snipe' uses task.participants_json
    # if set, otherwise falls back to profile (spaces " " are accepted by Vatican)
    task_participants = []
    if getattr(task, 'participants_json', None):
        try:
            task_participants = json.loads(task.participants_json)
        except Exception:
            pass

    # Correct mapping for mixed quantities
    participant_list = []
    task_p_idx = 0
    
    # 1. Fill Adults (Intero)
    for _ in range(adult_count):
        first, last = " ", " "
        if task_p_idx < len(task_participants):
            p = task_participants[task_p_idx]
            first = (p.get('first_name') or p.get('name') or '').strip() or profile.first_name
            last = (p.get('last_name') or p.get('surname') or '').strip() or profile.last_name
            task_p_idx += 1
        participant_list.append({"surname": last, "name": first, "id": 60, "ticketType": "intero", "services": [58]})
        
    # 2. Fill Children (Ridotto)
    for _ in range(child_count):
        first, last = " ", " "
        if task_p_idx < len(task_participants):
            p = task_participants[task_p_idx]
            first = (p.get('first_name') or p.get('name') or '').strip() or profile.first_name
            last = (p.get('last_name') or p.get('surname') or '').strip() or profile.last_name
            task_p_idx += 1
        participant_list.append({"surname": last, "name": first, "id": 61, "ticketType": "ridotto", "services": [58]})

    # ── 7. Reservation — API or Playwright ───────────────────────────────────
    epay_url = None
    reference = ''
    epay_params = {}

    if checkout_method == 'playwright':
        # Full UI flow — no token needed, browser solves Turnstile natively
        logger.info(f"  [{ms()}ms] Playwright checkout...")
        try:
            from .playwright_checkout import checkout_ui_sync
            pw_result = checkout_ui_sync(
                date=date,
                slot_time=slot_time,
                visitors=visitors,
                profile=profile,
                timeout_s=180,
            )
            if pw_result.get('success'):
                epay_url = pw_result.get('epay_url', '')
                reference = pw_result.get('reference', '')
                epay_params = pw_result.get('epay_params') or {}
                # If we got siv/mac from navigation, build epay_params
                if pw_result.get('siv_transaction_id') and not epay_params.get('mac_avvio'):
                    epay_params = {
                        'siv_transaction_id': pw_result['siv_transaction_id'],
                        'upp_redirect_mac': pw_result.get('upp_redirect_mac', ''),
                    }
                logger.info(f"  [{ms()}ms] ✅ Playwright success: ref={reference}")
            else:
                return_unused_token(token) if token else None
                return {'success': False, 'error': f"Playwright: {pw_result.get('error')}", 'elapsed_ms': ms()}
        except Exception as e:
            return {'success': False, 'error': f'Playwright exception: {e}', 'elapsed_ms': ms()}

    else:
        # API reservation — fast, needs Turnstile token
        res_body = {
            "recaptcha": token,
            "lang": "it",
            "recapId": recap_id,
            "visitorNum": int(visitors),
            "visitId": str(working_slot_id),
            "visitTypeId": int(tid),
            "tickets": [
                {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(visitors)},
                {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
            ],
            "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(visitors)}],
            "representativeUser": profile.to_representative_user(),
            "participantUser": participant_list,
            "gdpr": [{"id": 1, "check": True}, {"id": 3, "check": True}],
        }
        try:
            r_res = s.post(f'{BASE}/api/visit/reservation', json=res_body, headers=HC, timeout=15)
            logger.info(f"  [{ms()}ms] Reservation HTTP {r_res.status_code}")
            if r_res.status_code == 200:
                res_data = r_res.json()
                epay_data = res_data.get('epay', {})
                epay_url = epay_data.get('url') or ''
                reference = res_data.get('referenceOrder', '')
                epay_params = {
                    'mac_avvio': epay_data.get('mac_avvio', ''),
                    'idnegozio': epay_data.get('idnegozio', 'SIV001'),
                    'valuta': epay_data.get('valuta', '978'),
                    'tcontab': epay_data.get('tcontab', 'D'),
                    'tautor': epay_data.get('tautor', 'I'),
                    'urlMs': epay_data.get('urlMs', ''),
                    'urldone': epay_data.get('urldone', ''),
                    'urlback': epay_data.get('urlback', ''),
                    'referenceOrder': reference,
                }
            else:
                return_unused_token(token)
                return {'success': False, 'error': f'Reservation {r_res.status_code}: {r_res.text[:200]}', 'elapsed_ms': ms()}
        except Exception as e:
            return_unused_token(token)
            return {'success': False, 'error': f'Reservation exception: {e}', 'elapsed_ms': ms()}

    if not epay_url:
        return {'success': False, 'error': 'No epay URL from reservation', 'elapsed_ms': ms()}

    total_ms = ms()
    logger.info(f"⚡ SNIPE DONE {total_ms}ms | ref={reference} | pay_mode={getattr(task,'pay_mode','link')}")

    # ── Save to DB ────────────────────────────────────────────────────────────
    held = HeldSlot.objects.create(
        task=task, date=date, slot_id=str(working_slot_id), slot_time=slot_time,
        ticket_id=str(tid), ticket_name=ticket_name, visitors=visitors,
        total_price=total_price, jsessionid=s.cookies.get('JSESSIONID', ''),
        ticketmv=s.cookies.get('ticketmv', ''), recap_id=recap_id,
        status='paying', payment_url=epay_url,
        notes=json.dumps({
            'serverid': s.cookies.get('SERVERID', ''),
            'reference': reference,
            'method': 'api',
            'epay': epay_params,
        }),
    )

    pay_mode = getattr(task, 'pay_mode', 'link')
    now_str = datetime.now(ZoneInfo('Europe/Rome')).strftime('%H:%M:%S')

    # ── Mode: "link" — generate shareable POST-form URL ──────────────────────
    # The epay params from the reservation are already complete.
    # We store them in cache and serve a POST form page — no second token needed.
    if pay_mode == 'link':
        proxy_token = _secrets.token_urlsafe(32)
        cache.set(f"epay_direct:{held.id}:{proxy_token}", {
            'epay_url': epay_url,
            'epay_params': epay_params,
            'reference': reference,
        }, timeout=3600)
        proxy_url = f"{os.getenv('SERVER_BASE_URL', 'https://hydrabot.it')}/pay/direct/{held.id}/{proxy_token}/"

        msg = (
            f"⚡ SLOT SNIPED — PAY NOW!\n\n"
            f"📅 {date} {slot_time}\n"
            f"🎫 {ticket_name}\n"
            f"👥 {visitors} visitors | €{total_price}\n"
            f"🔖 Ref: {reference}\n\n"
            f"💳 OPEN TO PAY (any browser):\n{proxy_url}\n\n"
            f"⏱ Link valid 1 hour | ⚡ {total_ms}ms | 🕐 {now_str}"
        )

    # ── Mode: "auto" — Playwright fills card automatically ───────────────────
    else:
        proxy_url = None
        auto_result = _auto_pay(epay_url, epay_params, profile)
        if auto_result.get('success'):
            msg = (
                f"✅ AUTO-PAID!\n\n"
                f"📅 {date} {slot_time}\n"
                f"🎫 {ticket_name}\n"
                f"👥 {visitors} visitors | €{total_price}\n"
                f"🔖 Ref: {reference}\n"
                f"⚡ {total_ms}ms | 🕐 {now_str}"
            )
            held.status = 'paid'
            held.save(update_fields=['status'])
        else:
            # Auto-pay failed — fall back to link
            proxy_token = _secrets.token_urlsafe(32)
            cache.set(f"epay_direct:{held.id}:{proxy_token}", {
                'epay_url': epay_url, 'epay_params': epay_params, 'reference': reference,
            }, timeout=3600)
            proxy_url = f"{os.getenv('SERVER_BASE_URL', 'https://hydrabot.it')}/pay/direct/{held.id}/{proxy_token}/"
            msg = (
                f"⚡ SNIPED — Auto-pay failed, pay manually!\n\n"
                f"📅 {date} {slot_time} | 👥 {visitors}v | €{total_price}\n"
                f"🔖 {reference}\n\n"
                f"💳 {proxy_url}\n\n"
                f"⚠️ Auto-pay error: {auto_result.get('error','unknown')}"
            )

    groups = TelegramGroup.objects.filter(agency=task.agency, status='approved', notification_enabled=True)
    # ❌ DISABLED: snipe/payment notifications suppressed — only slot monitoring sends to agencies
    sent = 0
    logger.info(f"📢 Snipe notification suppressed for {task.agency.name} | pay_mode={pay_mode}")

    return {
        'success': True, 'epay_url': epay_url, 'proxy_url': proxy_url,
        'reference': reference, 'total': float(total_price),
        'elapsed_ms': total_ms, 'hold_id': held.id, 'pay_mode': pay_mode,
    }


def _auto_pay(epay_url: str, epay_params: dict, profile) -> dict:
    """
    Playwright auto-pay: POST to start.page, navigate to card form, fill card.
    Returns {'success': True} or {'success': False, 'error': '...'}
    """
    try:
        from .playwright_checkout import auto_pay_sync
        return auto_pay_sync(epay_url, epay_params, profile)
    except ImportError:
        return {'success': False, 'error': 'Playwright not available'}
    except Exception as e:
        return {'success': False, 'error': str(e)}



def keepalive_recap(held_slot_id: int) -> bool:
    """
    Re-call recap on the held slot to extend the ~55 min lock.
    Call every 30 min to keep the slot locked indefinitely.
    Returns True if keepalive succeeded.
    """
    from .models import HeldSlot
    from .epay_ssl import make_vatican_session

    try:
        held = HeldSlot.objects.get(id=held_slot_id, status__in=['held', 'paying'])
    except HeldSlot.DoesNotExist:
        return False

    s = make_vatican_session()

    # Refresh ticket_id via search
    try:
        r = s.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(held.visitors),
            'visitDate': held.date, 'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=H_XHR, timeout=8)
        t = next((v for v in r.json().get('visits', [])
                  if 'musei vaticani' in v.get('name', '').lower()
                  and 'ingresso' in v.get('name', '').lower()), None)
        tid = int(t['id']) if t else int(held.ticket_id)
    except Exception:
        tid = int(held.ticket_id)

    body = {
        "visitId": str(held.slot_id),
        "visitTypeId": tid,
        "visitorNum": int(held.visitors),
        "lang": "it",
        "tickets": [
            {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(held.adult_count)},
            {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": str(held.child_count)},
        ],
        "additionalCosts": {
            "service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(held.visitors)}
        },
        "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(held.visitors)}]
    }

    try:
        rr = s.post(f'{BASE}/api/visit/recap', json=body, headers=HC, timeout=10)
        if rr.status_code == 200:
            rd = rr.json()
            new_recap_id = rd.get('recapId') or rd.get('id') or held.recap_id
            held.recap_id = new_recap_id
            held.ticket_id = str(tid)
            new_jsid = s.cookies.get('JSESSIONID', '')
            if new_jsid:
                held.jsessionid = new_jsid
                held.ticketmv = s.cookies.get('ticketmv', '') or held.ticketmv
            from django.utils import timezone
            held.last_keepalive_at = timezone.now()
            held.save(update_fields=['recap_id', 'ticket_id', 'jsessionid', 'ticketmv', 'last_keepalive_at'])
            logger.info(f"💓 Keepalive OK for Hold #{held_slot_id} — slot still locked")
            return True
        else:
            logger.warning(f"⚠️ Keepalive recap failed {rr.status_code} for Hold #{held_slot_id}: {rr.text[:100]}")
            return False
    except Exception as e:
        logger.error(f"Keepalive exception for Hold #{held_slot_id}: {e}")
        return False


@shared_task(name='lightning_snipe_task')
def lightning_snipe_task(held_slot_id: int):
    """
    Celery wrapper for lightning_snipe. 
    Starts from an existing HeldSlot (recap'd but not reservation'd).
    """
    from .models import HeldSlot
    try:
        held = HeldSlot.objects.select_related('task__agency').get(id=held_slot_id)
    except HeldSlot.DoesNotExist:
        return {'success': False, 'error': 'Hold not found'}

    # Trigger the snipe flow (reservation + Turnstile)
    return lightning_snipe(
        task=held.task,
        date=held.date,
        slot_id=held.slot_id,
        slot_time=held.slot_time,
        ticket_id=held.ticket_id,
        ticket_name=held.ticket_name,
        visitors=held.visitors
    )
