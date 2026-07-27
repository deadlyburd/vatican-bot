"""
Bulk Hold Manager
=================
Locks Vatican slots in bulk via recap (confirmed ~55 min server-side hold).
No Turnstile needed — recap is free. Only reservation needs a token.

Flow:
  bulk_hold_scan   (every 5 min) — find available slots, recap them all
  bulk_hold_keepalive (every 25 min) — re-recap all held slots to extend lock

Each recap call: ~200ms, no captcha, no cost.
"""
import logging
import time
from datetime import datetime
from celery import shared_task
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger(__name__)

BASE = 'https://tickets.museivaticani.va'
H_XHR = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-origin',
    'X-Requested-With': 'XMLHttpRequest', 'Referer': f'{BASE}/', 'Origin': BASE,
}
HC = {k: v for k, v in H_XHR.items() if k != 'X-Requested-With'}
HC['Referer'] = f'{BASE}/home/checkout'
HC['Content-Type'] = 'application/json'


def _recap_slot(session, slot_id, ticket_id, visitors):
    """Call recap. Returns (ok, recap_id, total, elapsed_ms)."""
    t0 = time.time()
    body = {
        "visitId": str(slot_id), "visitTypeId": int(ticket_id),
        "visitorNum": int(visitors), "lang": "it",
        "tickets": [
            {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(visitors)},
            {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
        ],
        "additionalCosts": {"service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(visitors)}},
        "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(visitors)}],
    }
    try:
        # Default standard tickets
        tickets = body.get('tickets', [
            {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(visitors)},
            {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
        ])
        additional_costs = body.get('additionalCosts', {"service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(visitors)}})
        services = body.get('services', [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(visitors)}])
        
        # In a real scenario, we might want to fetch these from the ticket info, 
        # but for bulk-blocking, standard tickets usually work to "hold" the session.

        r = session.post(f'{BASE}/api/visit/recap', json=body, headers=HC, timeout=10)
        elapsed = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            rd = r.json()
            return True, rd.get('recapId', ''), rd.get('total', 0), elapsed
        else:
            try:
                msg = r.json().get('message', r.text[:80])
            except Exception:
                msg = r.text[:80]
            return False, msg, 0, elapsed
    except Exception as e:
        return False, str(e), 0, int((time.time() - t0) * 1000)


def _get_available_slots(session, date, visitors):
    """
    Search + timeavail. Returns (ticket_id, slots_list).
    Checks both Standard Admission and Guided Tours.
    """
    # 1. Try Standard Admission (MV-Biglietti)
    try:
        r = session.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=H_XHR, timeout=10)
        if r.status_code == 200:
            ticket = next((v for v in r.json().get('visits', [])
                           if 'musei vaticani' in v.get('name', '').lower()
                           and 'ingresso' in v.get('name', '').lower()
                           and v.get('availability') in ('AVAILABLE', 'LOW_AVAILABILITY')), None)
            if ticket:
                tid = ticket['id']
                r2 = session.get(f'{BASE}/api/visit/timeavail', params={
                    'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
                    'visitorNum': str(visitors), 'visitDate': date,
                }, headers=H_XHR, timeout=10)
                if r2.status_code == 200:
                    slots = [sl for sl in r2.json().get('timetable', [])
                             if sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')]
                    if slots:
                        return tid, slots

        # 2. Try Guided Tours (MV-VisiteGuidate) if Standard is empty
        r = session.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-VisiteGuidate'
        }, headers=H_XHR, timeout=10)
        if r.status_code == 200:
            ticket = next((v for v in r.json().get('visits', [])
                           if 'musei vaticani' in v.get('name', '').lower()
                           and 'visita guidata' in v.get('name', '').lower()
                           and v.get('availability') in ('AVAILABLE', 'LOW_AVAILABILITY')), None)
            if ticket:
                tid = ticket['id']
                r2 = session.get(f'{BASE}/api/visit/timeavail', params={
                    'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
                    'visitorNum': str(visitors), 'visitDate': date,
                }, headers=H_XHR, timeout=10)
                if r2.status_code == 200:
                    slots = [sl for sl in r2.json().get('timetable', [])
                             if sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')]
                    if slots:
                        return tid, slots
        
        return None, []
    except Exception as e:
        logger.warning(f"get_available_slots error {date}: {e}")
        return None, []
    except Exception as e:
        logger.warning(f"get_available_slots error {date}: {e}")
        return None, []


@shared_task(name="bulk_hold_scan", queue="vatican")
def bulk_hold_scan():
    """
    Runs every 5 minutes.
    For each active BulkHoldConfig:
      - Scan all dates in range
      - Recap every available slot within the time window
      - Skip slots already held
    """
    from .models import BulkHoldConfig, HeldSlot, MonitorTask, Agency
    from .epay_ssl import make_vatican_session

    configs = list(BulkHoldConfig.objects.filter(is_active=True).select_related('agency'))
    if not configs:
        return "No active bulk hold configs"

    total_new = 0

    for cfg in configs:
        target = cfg.target_total
        current_locked = cfg.total_locked or 0
        
        if current_locked >= target:
            logger.info(f"✅ BulkHold #{cfg.id} target reached ({current_locked}/{target}) - skipping")
            continue

        logger.info(f"🔍 BulkHold #{cfg.id} scan: {cfg.date_from}→{cfg.date_to} "
                    f"Target: {target} (Current: {current_locked})")

        # Get already-held slot_ids to skip
        held_slot_ids = set(
            HeldSlot.objects.filter(
                status__in=['held', 'paying'],
            ).values_list('slot_id', flat=True)
        )

        # Use one session per config scan with proxy rotation
        s = make_vatican_session(use_proxy=True)
        locked_this_scan = 0

        # Optimization: Shuffle dates and take a subset if the range is large.
        # This ensures we eventually cover the whole month without timing out a 15s scan.
        all_dates = list(cfg.date_range())
        import random
        random.shuffle(all_dates)
        
        # Limit to 5 dates per scan cycle to keep it under 10 seconds
        active_dates = all_dates[:5]

        for count in fallback_counts:
            # Re-check total_locked inside count loop to avoid over-holding
            if cfg.total_locked >= cfg.target_total:
                break
                
            for date in active_dates:
                # Re-check target
                if cfg.total_locked >= cfg.target_total:
                    break

                # Skip past dates
                try:
                    d_obj = datetime.strptime(date, '%d/%m/%Y').date()
                    if d_obj < datetime.now().date():
                        continue
                except Exception:
                    continue

                tid, slots = _get_available_slots(s, date, count)
                if not slots:
                    continue

                # Filter to time window
                window_slots = [sl for sl in slots if cfg.time_in_window(sl.get('time', ''))]
                if not window_slots:
                    continue

                for slot in window_slots:
                    slot_id = str(slot['id'])
                    slot_time = slot['time']

                    # Skip already held
                if slot_id in held_slot_ids:
                    logger.debug(f"  {date} {slot_time} already held — skip")
                    continue

                ok, recap_id, total, elapsed = _recap_slot(s, slot_id, tid, count)

                if ok:
                    # Save to HeldSlot — need a task FK, use/create a system task
                    task = _get_or_create_system_task(cfg.agency)
                    jsessionid = s.cookies.get('JSESSIONID', '')
                    ticketmv = s.cookies.get('ticketmv', '')

                    HeldSlot.objects.create(
                        task=task,
                        date=date,
                        slot_id=slot_id,
                        slot_time=slot_time,
                        ticket_id=str(tid),
                        ticket_name="Musei Vaticani - Biglietti d'ingresso",
                        visitors=count,
                        total_price=total,
                        jsessionid=jsessionid,
                        ticketmv=ticketmv,
                        recap_id=recap_id,
                        status='held',
                        notes=f'{{"bulk_hold_config": {cfg.id}}}',
                    )
                    held_slot_ids.add(slot_id)
                    locked_this_scan += 1
                    total_new += 1
                    
                    # Update config counter immediately to avoid over-holding concurrent dates
                    cfg.total_locked += count
                    cfg.save(update_fields=['total_locked'])
                    
                    logger.info(f"  🔒 Locked {date} {slot_time} | {count}px | recapId={recap_id} €{total} ({elapsed}ms)")
                else:
                    logger.debug(f"  ❌ Recap failed {date} {slot_time}: {recap_id}")

                time.sleep(0.05)  # tiny delay between recaps

        # Update stats
        cfg.last_scan_at = timezone.now()
        cfg.save(update_fields=['last_scan_at'])

        if locked_this_scan:
            logger.info(f"✅ BulkHold #{cfg.id}: locked {locked_this_scan} new slots this scan")

    return f"Bulk hold scan: {total_new} new slots locked across {len(configs)} configs"


@shared_task(name="bulk_hold_keepalive", queue="vatican")
def bulk_hold_keepalive():
    """
    Runs every 25 minutes.
    Re-locks slots by fetching fresh slot_ids from timeavail and recapping them.
    
    KEY INSIGHT from testing:
    - Once a slot is fully locked (all tickets consumed), re-recap fails with "non dispone"
    - The lock lasts ~55 min from the last successful recap
    - To extend: fetch fresh slot_id from timeavail (Vatican rotates IDs) and recap again
    - If Vatican hasn't released the slot yet, timeavail returns SOLD_OUT → nothing to do
    - If Vatican released it (after ~55 min), timeavail returns available → recap to re-lock
    """
    from .models import HeldSlot, BulkHoldConfig
    from .epay_ssl import make_vatican_session

    # Find slots held for 30-55 min (approaching expiry, need re-lock)
    now = timezone.now()
    expiry_window_start = now - timezone.timedelta(minutes=55)
    expiry_window_end = now - timezone.timedelta(minutes=30)

    # Also find slots that may have already expired (>55 min) — re-lock if Vatican released them
    expired_cutoff = now - timezone.timedelta(minutes=56)

    held_slots = list(HeldSlot.objects.filter(
        status__in=['held', 'paying'],
        last_keepalive_at__lte=expiry_window_end,  # not keepalived in last 30 min
    ).order_by('last_keepalive_at'))

    if not held_slots:
        return "No slots need keepalive"

    logger.info(f"💓 Keepalive: checking {len(held_slots)} slots approaching expiry")

    refreshed = 0
    still_locked = 0
    released = 0

    # Group by date for efficiency
    from collections import defaultdict
    by_date = defaultdict(list)
    for h in held_slots:
        by_date[h.date].append(h)

    for date, slots in by_date.items():
        s = make_vatican_session(use_proxy=True)

        for h in slots:
            # Try to get fresh slot_id for this time on this date
            tid = get_tid_for_date(s, date, h.visitors)
            if not tid:
                logger.debug(f"  {h.date} {h.slot_time}: no ticket found")
                continue

            # Check timeavail for this specific time
            try:
                r2 = s.get(f'{BASE}/api/visit/timeavail', params={
                    'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
                    'visitorNum': str(h.visitors), 'visitDate': date,
                }, headers=H_XHR, timeout=10)
                if r2.status_code != 200:
                    continue
                timetable = r2.json().get('timetable', [])
            except Exception as e:
                logger.warning(f"  Timeavail error {h.date} {h.slot_time}: {e}")
                continue

            # Find slot matching our time
            matching = [sl for sl in timetable if sl.get('time') == h.slot_time]
            if not matching:
                logger.debug(f"  {h.date} {h.slot_time}: time not in timetable")
                continue

            slot_avail = matching[0].get('availability')
            fresh_slot_id = str(matching[0].get('id', h.slot_id))

            if slot_avail == 'SOLD_OUT':
                # Still locked — update keepalive timestamp
                h.last_keepalive_at = now
                h.save(update_fields=['last_keepalive_at'])
                still_locked += 1
                logger.debug(f"  {h.date} {h.slot_time}: still SOLD_OUT ✅")

            elif slot_avail in ('AVAILABLE', 'LOW_AVAILABILITY'):
                # Vatican released it — re-lock immediately
                logger.info(f"  {h.date} {h.slot_time}: released by Vatican, re-locking...")
                ok, recap_id, elapsed, total = _recap_slot(s, fresh_slot_id, tid, h.visitors)
                if ok:
                    h.slot_id = fresh_slot_id
                    h.ticket_id = str(tid)
                    h.recap_id = recap_id
                    h.last_keepalive_at = now
                    new_jsid = s.cookies.get('JSESSIONID', '')
                    if new_jsid:
                        h.jsessionid = new_jsid
                        h.ticketmv = s.cookies.get('ticketmv', '') or h.ticketmv
                    h.save(update_fields=['slot_id', 'ticket_id', 'recap_id',
                                          'jsessionid', 'ticketmv', 'last_keepalive_at'])
                    refreshed += 1
                    logger.info(f"  ✅ Re-locked {h.date} {h.slot_time} ({elapsed}ms)")
                else:
                    logger.warning(f"  ❌ Re-lock failed {h.date} {h.slot_time}: {recap_id}")
                    released += 1
            else:
                logger.debug(f"  {h.date} {h.slot_time}: {slot_avail}")

            time.sleep(0.05)

    logger.info(f"💓 Keepalive done: {still_locked} still locked, {refreshed} re-locked, {released} lost")
    return f"Keepalive: {still_locked} locked, {refreshed} re-locked, {released} lost"


def get_tid_for_date(session, date, visitors):
    """Get fresh ticket_id for a date."""
    try:
        r = session.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=H_XHR, timeout=10)
        if r.status_code != 200:
            return None
        t = next((v for v in r.json().get('visits', [])
                  if 'musei vaticani' in v.get('name', '').lower()
                  and 'ingresso' in v.get('name', '').lower()), None)
        return t['id'] if t else None
    except Exception:
        return None


def _get_or_create_system_task(agency):
    """Get or create a system MonitorTask for bulk holds."""
    from .models import MonitorTask
    task = MonitorTask.objects.filter(
        agency=agency, tier='hold', area_name='__bulk_hold__', is_active=True
    ).first()
    if not task:
        task = MonitorTask.objects.create(
            agency=agency, site='vatican',
            area_name='__bulk_hold__',
            dates=[], preferred_times=[],
            visitors=2, tier='hold',
            is_active=True,
            last_status='bulk',
        )
    return task
