"""
Vatican Slot Hold Manager
=========================
Holds slots via /api/visit/recap and keeps sessions alive indefinitely.
One session per held slot — keepalive pings every 5 min.
"""
import logging
import requests
import time
from django.utils import timezone
from .epay_ssl import make_vatican_session

logger = logging.getLogger(__name__)

BASE = 'https://tickets.museivaticani.va'
HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE}/',
    'Origin': BASE,
    'Content-Type': 'application/json',
}


def _make_session(jsessionid=None, ticketmv=None, serverid=None):
    """Create a session with epay SSL adapter pre-mounted."""
    s = make_vatican_session(jsessionid, ticketmv, serverid)
    return s


def _get_serverid(held_slot):
    import json
    try:
        data = json.loads(held_slot.notes or '{}')
    except Exception:
        data = {}
    serverid = data.get('serverid')
    return serverid or ''


def _load_notes(held_slot):
    import json
    try:
        data = json.loads(held_slot.notes or '{}')
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_notes(held_slot, data):
    import json
    if not isinstance(data, dict):
        data = {}
    held_slot.notes = json.dumps(data) if data else None
    held_slot.save(update_fields=['notes'])


def _get_services(session, slot_id, ticket_id, visitors):
    """Fetch services (pre-sale fees) for a slot. Always returns a list."""
    try:
        r = session.get(f'{BASE}/api/visit/services', params={
            'lang': 'it', 'visitId': slot_id,
            'visitTypeId': ticket_id, 'visitorNum': str(visitors)
        }, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json().get('services', []) or []
    except Exception as e:
        logger.warning(f"Could not fetch services: {e}")
    return []  # always return list, never None


def _build_recap_body(slot_id, ticket_id, visitors, services, adult_count=None, child_count=None):
    if adult_count is None:
        adult_count = visitors
    if child_count is None:
        child_count = 0
        
    body = {
        "visitId": str(slot_id),
        "visitTypeId": int(ticket_id),
        "visitorNum": int(visitors),
        "lang": "it",
        "tickets": [
            {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(adult_count)},
            {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": str(child_count)},
        ],
        "additionalCosts": {},
        "services": []
    }
    # Add pre-sale fee if present
    for svc in services:
        svc_id = svc.get('id', 58)
        svc_name = svc.get('name', 'Diritti di Prevendita')
        svc_price = svc.get('price', 5)
        body["additionalCosts"]["service-0"] = {
            "id": svc_id, "name": svc_name, "price": svc_price, "quantity": int(visitors)
        }
        body["services"].append({
            "id": svc_id, "name": svc_name, "price": svc_price, "quantity": int(visitors)
        })
        break  # only first service
    return body


def hold_slot(task, date, slot_id, slot_time, ticket_id, ticket_name, visitors, proxy_str=None):
    """
    Hold a Vatican slot via /api/visit/recap.
    Returns HeldSlot instance or None on failure.
    """
    from .models import HeldSlot

    logger.info(f"🔒 Attempting to hold slot {slot_id} ({slot_time}) on {date} for {task.agency.name}")

    # Build fresh session with epay SSL adapter
    s = make_vatican_session()
    req_headers = {**HEADERS}
    if proxy_str:
        s.proxies = {'http': proxy_str, 'https': proxy_str}

    # Init session via homepage
    try:
        s.get(f'{BASE}/home', headers=req_headers, timeout=10)
    except Exception as e:
        logger.warning(f"Homepage init failed: {e}")

    # Get fresh ticket_id via search API (IDs change daily)
    try:
        r = s.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=req_headers, timeout=10)
        fresh_ticket = next(
            (t for t in r.json().get('visits', []) if 'ingresso' in t.get('name', '').lower()),
            None
        )
        if fresh_ticket:
            ticket_id = fresh_ticket['id']
            logger.info(f"  Fresh ticket_id: {ticket_id}")
    except Exception as e:
        logger.warning(f"Could not refresh ticket_id: {e}")

    # Get services
    services = _get_services(s, slot_id, ticket_id, visitors)

    # Build recap body
    body = _build_recap_body(slot_id, ticket_id, visitors, services, 
                             adult_count=task.adult_count, child_count=task.child_count)

    # Call recap — this is the hold
    try:
        r2 = s.post(f'{BASE}/api/visit/recap', json=body, headers=req_headers, timeout=10)
        if r2.status_code != 200:
            logger.error(f"❌ Recap failed: {r2.status_code} | {r2.text[:200]}")
            return None

        recap_data = r2.json()
        total_price = recap_data.get('total', 0)
        recap_id = recap_data.get('recapId') or recap_data.get('id') or ''
        logger.info(f"✅ Slot held! Total: €{total_price} | recapId: {recap_id} | {recap_data.get('visitDateTime')}")

    except Exception as e:
        logger.error(f"❌ Recap exception: {e}")
        return None

    # Save cookies
    jsessionid = s.cookies.get('JSESSIONID', '')
    ticketmv = s.cookies.get('ticketmv', '')
    serverid = s.cookies.get('SERVERID', '')

    if not jsessionid:
        logger.error("❌ No JSESSIONID after recap — hold may not be valid")
        return None

    # Payment URL will be generated after reservation with direct epay link
    payment_url = "Direct epay URL will be generated upon reservation"

    # Save to DB
    notes = None
    if serverid:
        import json
        notes = json.dumps({'serverid': serverid})

    held = HeldSlot.objects.create(
        task=task,
        date=date,
        slot_id=slot_id,
        slot_time=slot_time,
        ticket_id=str(ticket_id),
        ticket_name=ticket_name,
        visitors=visitors,
        adult_count=task.adult_count,
        child_count=task.child_count,
        total_price=total_price,
        jsessionid=jsessionid,
        ticketmv=ticketmv,
        recap_id=recap_id,
        status='held',
        payment_url=payment_url,
        notes=notes,
    )

    # Payment URL will be updated with direct epay link after reservation
    held.save(update_fields=['payment_url'])

    logger.info(f"✅ HeldSlot #{held.id} created for {task.agency.name} | {date} {slot_time}")
    return held


def hold_with_dynamic_injection(task, slot_data, injection_config=None):
    """
    Hold slot with dynamic participant/card injection.
    Uses injection_config for dynamic details, falls back to static profile.
    """
    from .models import BuyerProfile
    
    # Extract slot data
    date = slot_data.get('date')
    slot_id = slot_data.get('slot_id')
    slot_time = slot_data.get('slot_time')
    ticket_id = slot_data.get('ticket_id')
    ticket_name = slot_data.get('ticket_name')
    visitors = slot_data.get('visitors', task.visitors)
    
    # Get base profile
    try:
        profile = BuyerProfile.objects.get(agency=task.agency)
    except BuyerProfile.DoesNotExist:
        logger.error(f"❌ No buyer profile for agency {task.agency.name}")
        return None
    
    # Use dynamic participants or fallback to profile
    if injection_config and injection_config.participant_overrides:
        participants = injection_config.participant_overrides
        logger.info(f"🔧 Using dynamic injection: {len(participants)} participants")
    else:
        # Fallback to profile-based participants
        participants = profile.to_participant_list(visitors)
    
    # Standard hold with the determined participants
    held = hold_slot(task, date, slot_id, slot_time, ticket_id, ticket_name, visitors)
    
    # If we have an injection config and direct snipe is requested
    if held and injection_config and injection_config.action == 'snipe':
        try:
            from .tasks_hold import snipe_with_dynamic_card
            snipe_result = snipe_with_dynamic_card(held, injection_config.card_overrides)
            logger.info(f"🎯 Direct snipe completed: {snipe_result}")
            injection_config.mark_used({'status': 'snipe_completed'})
        except Exception as e:
            logger.error(f"❌ Direct snipe failed: {e}")
            injection_config.mark_used({'status': f'snipe_failed: {e}'})
    
    return held


def _build_dynamic_participant_list(profile, dynamic_participants, visitors):
    """Build participant list merging static profile with dynamic overrides"""
    if dynamic_participants:
        # Use dynamic participants
        return [
            {
                'name': p.get('first_name', profile.first_name),
                'surname': p.get('last_name', profile.last_name),
                'id': 60,  # Default ticket ID
                'ticketType': 'intero',
                'services': [58]  # Diritti di Prevendita
            }
            for p in dynamic_participants[:visitors]
        ]
    else:
        # Fallback to profile-based participants
        return profile.to_participant_list(visitors)


def keepalive_slot(held_slot):
    """
    Ping Vatican API to keep the session alive.
    Returns True if session is still valid, False if expired.
    """
    from .models import HeldSlot

    s = _make_session(held_slot.jsessionid, held_slot.ticketmv, _get_serverid(held_slot))

    try:
        r = s.get(f'{BASE}/api/config/isAgency', headers=HEADERS, timeout=10)
        if r.status_code != 200:
            logger.warning(f"⚠️ Keepalive ping returned {r.status_code} for HeldSlot #{held_slot.id}")

        if _re_hold(held_slot, s):
            logger.info(f"💓 Keepalive OK for HeldSlot #{held_slot.id} ({held_slot.date} {held_slot.slot_time})")
            return True

        logger.warning(f"⚠️ Keepalive recap refresh failed for HeldSlot #{held_slot.id} — attempting fresh re-hold")
        return _fresh_re_hold(held_slot)
    except Exception as e:
        logger.error(f"❌ Keepalive failed for HeldSlot #{held_slot.id}: {e}")
        return False


def _re_hold(held_slot, session=None):
    """
    Re-call recap on existing session to refresh hold.
    Always resolves a fresh ticket_id via Search API first —
    Vatican changes IDs frequently and stale IDs cause 500 errors.
    """
    from .models import HeldSlot

    if session is None:
        session = _make_session(held_slot.jsessionid, held_slot.ticketmv, _get_serverid(held_slot))

    # Always get fresh ticket_id — stale IDs cause 500 errors
    ticket_id = held_slot.ticket_id
    try:
        r_search = session.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(held_slot.visitors),
            'visitDate': held_slot.date, 'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=HEADERS, timeout=10)
        if r_search.status_code == 200:
            fresh = next(
                (v for v in r_search.json().get('visits', [])
                 if 'musei vaticani' in v.get('name', '').lower()
                 and 'ingresso' in v.get('name', '').lower()),
                None
            )
            if fresh:
                ticket_id = fresh['id']
    except Exception:
        pass  # fall back to stored ticket_id

    services = _get_services(session, held_slot.slot_id, ticket_id, held_slot.visitors)
    body = _build_recap_body(held_slot.slot_id, ticket_id, held_slot.visitors, services or [],
                             adult_count=held_slot.adult_count, child_count=held_slot.child_count)

    try:
        r = session.post(f'{BASE}/api/visit/recap', json=body, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            try:
                recap_data = r.json()
                recap_id = recap_data.get('recapId') or recap_data.get('id') or ''
                if recap_id:
                    held_slot.recap_id = recap_id
                held_slot.ticket_id = str(ticket_id)
                # Update session cookies in DB
                new_jsid = session.cookies.get('JSESSIONID', '')
                if new_jsid:
                    held_slot.jsessionid = new_jsid
                    held_slot.ticketmv = session.cookies.get('ticketmv', '') or held_slot.ticketmv
            except Exception:
                pass
            held_slot.last_keepalive_at = timezone.now()
            held_slot.save(update_fields=['last_keepalive_at', 'recap_id', 'ticket_id', 'jsessionid', 'ticketmv'])
            logger.info(f"💓 Re-hold OK for HeldSlot #{held_slot.id} | ticket_id={ticket_id}")
            return True
        else:
            logger.warning(f"⚠️ Re-hold failed {r.status_code}: {r.text[:150]}")
            return False
    except Exception as e:
        logger.error(f"❌ Re-hold exception: {e}")
        return False


def _fresh_re_hold(held_slot):
    """
    Re-hold using a completely fresh session + fresh slot_id resolved via Search API.
    This handles the case where Vatican's slot_id has changed (happens frequently).
    Returns True if re-hold succeeded, False otherwise.
    Marks hold as expired if slot is genuinely gone.
    """
    from .models import HeldSlot

    s = make_vatican_session()

    # Step 1: Get fresh ticket_id via Search API
    try:
        r_search = s.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(held_slot.visitors),
            'visitDate': held_slot.date, 'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=HEADERS, timeout=12)

        if r_search.status_code != 200:
            logger.warning(f"⚠️ Fresh re-hold: Search API {r_search.status_code} for Hold #{held_slot.id}")
            _mark_expired_if_old(held_slot)
            return False

        fresh_ticket = next(
            (v for v in r_search.json().get('visits', [])
             if 'musei vaticani' in v.get('name', '').lower()
             and 'ingresso' in v.get('name', '').lower()
             and v.get('availability') == 'AVAILABLE'),
            None
        )
        if not fresh_ticket:
            logger.warning(f"⚠️ Fresh re-hold: No available ticket for {held_slot.date} v={held_slot.visitors} — slot may be sold out")
            _mark_expired_if_old(held_slot)
            return False

        ticket_id = int(fresh_ticket['id'])

    except Exception as e:
        logger.error(f"❌ Fresh re-hold search exception for Hold #{held_slot.id}: {e}")
        return False

    # Step 2: Get fresh slot_id via Timeavail — find matching time
    try:
        r_time = s.get(f'{BASE}/api/visit/timeavail', params={
            'lang': 'it', 'visitLang': '',
            'visitTypeId': str(ticket_id),
            'visitorNum': str(held_slot.visitors),
            'visitDate': held_slot.date,
        }, headers=HEADERS, timeout=12)

        if r_time.status_code != 200:
            logger.warning(f"⚠️ Fresh re-hold: Timeavail {r_time.status_code} for Hold #{held_slot.id}")
            _mark_expired_if_old(held_slot)
            return False

        timetable = r_time.json().get('timetable', [])
        # Find matching slot by time
        matching_slot = next(
            (sl for sl in timetable
             if sl.get('time') == held_slot.slot_time
             and sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')),
            None
        )

        if not matching_slot:
            # LOW_AVAILABILITY is still bookable — check if it exists at all
            any_slot = next((sl for sl in timetable if sl.get('time') == held_slot.slot_time), None)
            if any_slot:
                avail = any_slot.get('availability', 'UNKNOWN')
                logger.warning(f"⚠️ Fresh re-hold: Slot {held_slot.slot_time} on {held_slot.date} is {avail} for Hold #{held_slot.id}")
            else:
                logger.warning(f"⚠️ Fresh re-hold: Slot {held_slot.slot_time} on {held_slot.date} not found in timetable for Hold #{held_slot.id}")
            _mark_expired_if_old(held_slot)
            return False

        fresh_slot_id = str(matching_slot.get('id', held_slot.slot_id))

    except Exception as e:
        logger.error(f"❌ Fresh re-hold timeavail exception for Hold #{held_slot.id}: {e}")
        return False

    # Step 3: Recap with fresh slot_id + ticket_id on same session
    services = _get_services(s, fresh_slot_id, ticket_id, held_slot.visitors)
    body = _build_recap_body(fresh_slot_id, ticket_id, held_slot.visitors, services,
                             adult_count=held_slot.adult_count, child_count=held_slot.child_count)

    try:
        r = s.post(f'{BASE}/api/visit/recap', json=body, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            logger.warning(f"⚠️ Fresh re-hold recap failed {r.status_code}: {r.text[:150]}")
            _mark_expired_if_old(held_slot)
            return False
        recap_data = r.json()
        recap_id = recap_data.get('recapId') or recap_data.get('id') or ''
    except Exception as e:
        logger.error(f"❌ Fresh re-hold recap exception for Hold #{held_slot.id}: {e}")
        return False

    jsessionid = s.cookies.get('JSESSIONID', '')
    if not jsessionid:
        return False
    ticketmv = s.cookies.get('ticketmv', '')
    serverid = s.cookies.get('SERVERID', '')

    notes = _load_notes(held_slot)
    if serverid:
        notes['serverid'] = serverid

    # Update with fresh IDs
    held_slot.slot_id = fresh_slot_id
    held_slot.ticket_id = str(ticket_id)
    held_slot.jsessionid = jsessionid
    held_slot.ticketmv = ticketmv
    if recap_id:
        held_slot.recap_id = recap_id
    held_slot.status = 'held'
    held_slot.last_keepalive_at = timezone.now()
    held_slot.notes = __import__('json').dumps(notes) if notes else None
    held_slot.save(update_fields=[
        'slot_id', 'ticket_id', 'jsessionid', 'ticketmv',
        'recap_id', 'status', 'last_keepalive_at', 'notes'
    ])
    logger.info(f"🆕 Fresh re-hold OK for Hold #{held_slot.id} | new slot_id={fresh_slot_id} ticket_id={ticket_id}")
    return True


def _mark_expired_if_old(held_slot):
    """Mark hold as expired only if it's been held for a while (not brand new)."""
    age_min = (timezone.now() - held_slot.hold_started_at).total_seconds() / 60
    if age_min > 30:  # only expire if held for >30 min and slot is gone
        held_slot.status = 'expired'
        held_slot.save(update_fields=['status'])
        logger.info(f"💀 Hold #{held_slot.id} marked expired (slot gone, age={age_min:.0f}min)")


def release_slot(held_slot):
    """Mark a held slot as released (session will expire naturally)."""
    from .models import HeldSlot
    held_slot.status = 'released'
    held_slot.released_at = timezone.now()
    held_slot.save(update_fields=['status', 'released_at'])
    logger.info(f"🔓 Released HeldSlot #{held_slot.id} ({held_slot.date} {held_slot.slot_time})")
