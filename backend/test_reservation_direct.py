"""
Direct reservation test using exact payload from working HAR.
Uses the reserved token from pool (no new solve needed).
Tests multiple service configurations to find what works.
"""
import os, sys, django, time, json
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.epay_ssl import make_vatican_session
from monitors.turnstile_pool import get_token_sync, pool_size, POOL_KEY, _solve_one_token, POOL_CACHE_TTL, RESERVED_KEY
from django.core.cache import cache
from monitors.models import BuyerProfile, Agency
from datetime import datetime, timedelta

BASE = 'https://tickets.museivaticani.va'
HC = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'Origin': BASE,
    'Referer': f'{BASE}/home/checkout',
    'Content-Type': 'application/json',
}

agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
profile = BuyerProfile.objects.filter(agency=agency).first()
print(f"Profile: {profile.first_name} {profile.last_name}")

# ── Get token (from reserved slot or solve 1) ─────────────────────────────────
reserved = cache.get(RESERVED_KEY)
if reserved and time.time() - reserved.get('solved_at', 0) < 90:
    token = reserved['token']
    cache.delete(RESERVED_KEY)
    print(f"✅ Using reserved token (age={int(time.time()-reserved['solved_at'])}s)")
elif pool_size() > 0:
    token = get_token_sync()
    print(f"✅ Using pooled token")
else:
    api_key = os.getenv('TWOCAPTCHA_API_KEY')
    print("Solving 1 token...")
    token = _solve_one_token(api_key)
    if not token:
        print("❌ Token solve failed"); sys.exit(1)
    print(f"✅ Token ready | prefix={token[:4]} | len={len(token)}")

# ── Find open slot ────────────────────────────────────────────────────────────
VISITORS = 2
s = make_vatican_session()
print("\nFinding open slot...")
found = None
for days in range(1, 120):  # Extended range
    d = (datetime.now() + timedelta(days=days)).strftime('%d/%m/%Y')
    r = s.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': d,
        'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers={**HC, 'X-Requested-With': 'XMLHttpRequest'}, timeout=10)
    if r.status_code != 200: continue
    t = next((v for v in r.json().get('visits', [])
               if 'musei vaticani' in v.get('name','').lower()
               and 'ingresso' in v.get('name','').lower()
               and v.get('availability') == 'AVAILABLE'), None)
    if not t: continue
    tid = t['id']
    r2 = s.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
        'visitorNum': str(VISITORS), 'visitDate': d,
    }, headers={**HC, 'X-Requested-With': 'XMLHttpRequest'}, timeout=10)
    if r2.status_code != 200: continue
    slots = [sl for sl in r2.json().get('timetable', [])
             if sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')]
    if slots:
        found = {'date': d, 'tid': tid, 'slot': slots[0]}
        print(f"Found: {d} {slots[0]['time']} | slot={slots[0]['id']} | tid={tid}")
        break
    time.sleep(0.1)

if not found:
    print("No open slots"); sys.exit(0)

date, tid, slot = found['date'], found['tid'], found['slot']
slot_id, slot_time = str(slot['id']), slot['time']

# ── Services ──────────────────────────────────────────────────────────────────
r_svc = s.get(f'{BASE}/api/visit/services', params={
    'lang': 'it', 'visitId': slot_id, 'visitTypeId': tid, 'visitorNum': str(VISITORS)
}, headers={**HC, 'X-Requested-With': 'XMLHttpRequest'}, timeout=8)
services = r_svc.json().get('services', []) if r_svc.status_code == 200 else []
# Filter out null/invalid services
services = [s for s in services if s.get('id') is not None and s.get('id') != 0]
print(f"Services (filtered): {[{'id': s.get('id'), 'name': s.get('name'), 'price': s.get('price')} for s in services]}")

# ── Recap ─────────────────────────────────────────────────────────────────────
recap_body = {
    "visitId": slot_id, "visitTypeId": int(tid), "visitorNum": int(VISITORS), "lang": "it",
    "tickets": [
        {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(VISITORS)},
        {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
    ],
    # CONFIRMED: always service 58, not the optional services from API
    "additionalCosts": {"service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(VISITORS)}},
    "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(VISITORS)}]
}

rr = s.post(f'{BASE}/api/visit/recap', json=recap_body, headers=HC, timeout=10)
if rr.status_code != 200:
    print(f"❌ Recap failed: {rr.status_code} {rr.text[:200]}"); sys.exit(1)
recap_id = rr.json().get('recapId') or rr.json().get('id') or ''
total = rr.json().get('total', 0)
print(f"✅ Recap: {recap_id} | €{total}")

# Verify slot still available after recap
r_check = s.get(f'{BASE}/api/visit/timeavail', params={
    'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
    'visitorNum': str(VISITORS), 'visitDate': date,
}, headers={**HC, 'X-Requested-With': 'XMLHttpRequest'}, timeout=8)
if r_check.status_code == 200:
    slot_status = next((sl.get('availability') for sl in r_check.json().get('timetable', [])
                        if str(sl.get('id')) == slot_id), 'NOT_FOUND')
    print(f"Slot status after recap: {slot_status}")
    if slot_status in ('SOLD_OUT', 'NOT_ALLOWED', 'NOT_FOUND'):
        print(f"⚠️ Slot sold out after recap — this explains the 500!")
        sys.exit(0)

# ── Test 4 reservation variants ───────────────────────────────────────────────
def try_reservation(label, svc_list, participant_services, extra_headers=None):
    hdrs = {**HC, **(extra_headers or {})}
    body = {
        "recaptcha": token, "lang": "it", "recapId": recap_id,
        "visitorNum": int(VISITORS), "visitId": slot_id, "visitTypeId": int(tid),
        "tickets": [
            {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(VISITORS)},
            {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
        ],
        "services": svc_list,
        "representativeUser": profile.to_representative_user(),
        "participantUser": [
            {"name": profile.first_name, "surname": profile.last_name,
             "id": 60, "ticketType": "intero", "services": participant_services}
            for _ in range(VISITORS)
        ],
        "gdpr": [{"id": 1, "check": True}, {"id": 3, "check": True}],
    }
    r = s.post(f'{BASE}/api/visit/reservation', json=body, headers=hdrs, timeout=15)
    status = r.status_code
    try:
        resp = r.json()
        if status == 200:
            epay = resp.get('epay', {}).get('url') or resp.get('paymentUrl') or ''
            ref = resp.get('referenceOrder', '')
            print(f"  ✅ {label}: SUCCESS | ref={ref} | epay={epay[:50]}")
            return True, epay, ref
        else:
            print(f"  ❌ {label}: {status} | {resp.get('message', resp)}")
            print(f"     Full response: {json.dumps(resp)[:400]}")
    except:
        print(f"  ❌ {label}: {status} | {r.text[:200]}")
    return False, None, None

svc_id = services[0].get('id', 58) if services else 58
svc_name = services[0].get('name', 'Diritti di Prevendita') if services else 'Diritti di Prevendita'
svc_price = services[0].get('price', 5) if services else 5

print(f"\n{'='*55}")
print(f"Testing reservation (slot={slot_id} tid={tid})")
print(f"Token prefix={token[:4]} len={len(token)}")
print(f"JSESSIONID={s.cookies.get('JSESSIONID','')[:20]}...")
print(f"ticketmv={s.cookies.get('ticketmv','')[:20]}")
print(f"{'='*55}")

# Single variant: service 58 hardcoded (confirmed from websocket.har)
ok, epay, ref = try_reservation(
    "Service 58 (Diritti di Prevendita) — confirmed working",
    [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(VISITORS)}],
    [58]
)
if ok: sys.exit(0)

print("\n❌ Failed — checking if slot is still available...")
r_check = s.get(f'{BASE}/api/visit/timeavail', params={
    'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
    'visitorNum': str(VISITORS), 'visitDate': date,
}, headers={**HC, 'X-Requested-With': 'XMLHttpRequest'}, timeout=8)
if r_check.status_code == 200:
    slot_status = next((sl.get('availability') for sl in r_check.json().get('timetable', [])
                        if str(sl.get('id')) == slot_id), 'NOT_FOUND')
    print(f"Slot {slot_id} status: {slot_status}")
    if slot_status in ('SOLD_OUT', 'NOT_FOUND'):
        print("→ Slot sold out between recap and reservation — this is the race condition!")
    else:
        print(f"→ Slot still {slot_status} — reservation API is rejecting for another reason")
