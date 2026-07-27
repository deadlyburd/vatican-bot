"""
Direct reservation API debug script.
Runs the exact flow from epay.catholica.va.txt (confirmed 200 OK):
  search → timeavail → recap → reservation

Key findings from HAR analysis:
- Reservation response body is intentionally blocked by Vatican (bodySize: -1)
- After 200 OK, browser navigates to:
    https://epay.catholica.va/pay/public/init/{sivTransactionId}/{uppRedirectMac}/it
- The sivTransactionId + uppRedirectMac come from the reservation response body
- Token prefix: working token starts with '0.' (NOT '1.') — confirmed from epay.catholica.va.txt
  recaptcha: "0.T38AawwppzAX..." → 200 OK
- The websocket.txt token "1.bu6abhnp..." is from a DIFFERENT session/date

Run: docker-compose exec -T backend python /app/backend/debug_reservation.py
"""
import os, sys, django, time, json, requests
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.epay_ssl import make_vatican_session
from monitors.turnstile_pool import _solve_one_token
from monitors.models import BuyerProfile, Agency

BASE = 'https://tickets.museivaticani.va'

# Exact headers from epay.catholica.va.txt (confirmed working)
H_XHR = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE}/',
    'Origin': BASE,
}
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
    'Content-Type': 'application/json',
    'Referer': f'{BASE}/home/checkout',
    'Origin': BASE,
}

VISITORS = 2

agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
profile = BuyerProfile.objects.filter(agency=agency).first()
print(f"Agency: {agency.name}")
print(f"Profile: {profile.first_name} {profile.last_name} | {profile.email}")

# ── Step 1: Fresh session via search ─────────────────────────────────────────
s = make_vatican_session()
print(f"\n[1] Search API...")
from datetime import datetime, timedelta

found = None
for days in range(1, 90):
    d = (datetime.now() + timedelta(days=days)).strftime('%d/%m/%Y')
    r = s.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': d,
        'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers=H_XHR, timeout=10)
    if r.status_code != 200:
        continue
    t = next((v for v in r.json().get('visits', [])
               if 'musei vaticani' in v.get('name', '').lower()
               and 'ingresso' in v.get('name', '').lower()
               and v.get('availability') == 'AVAILABLE'), None)
    if not t:
        continue
    tid = t['id']
    r2 = s.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
        'visitorNum': str(VISITORS), 'visitDate': d,
    }, headers=H_XHR, timeout=10)
    if r2.status_code != 200:
        continue
    slots = [sl for sl in r2.json().get('timetable', [])
             if sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')]
    if slots:
        found = {'date': d, 'tid': tid, 'slot': slots[0]}
        break
    time.sleep(0.05)

if not found:
    print("No open slots found"); sys.exit(1)

date, tid, slot = found['date'], found['tid'], found['slot']
slot_id, slot_time = str(slot['id']), slot['time']
jsessionid = s.cookies.get('JSESSIONID', '')
ticketmv = s.cookies.get('ticketmv', '')
serverid = s.cookies.get('SERVERID', '')
print(f"  Date: {date} | Time: {slot_time} | slot_id: {slot_id} | tid: {tid}")
print(f"  JSESSIONID: {jsessionid[:30]}...")
print(f"  ticketmv: {ticketmv}")
print(f"  SERVERID: {serverid}")

# ── Step 2: Recap ─────────────────────────────────────────────────────────────
print(f"\n[2] Recap...")
recap_body = {
    "visitId": slot_id,
    "visitTypeId": int(tid),
    "visitorNum": int(VISITORS),
    "lang": "it",
    "tickets": [
        {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(VISITORS)},
        {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
    ],
    "additionalCosts": {
        "service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(VISITORS)}
    },
    "services": [
        {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(VISITORS)}
    ]
}
rr = s.post(f'{BASE}/api/visit/recap', json=recap_body, headers=HC, timeout=10)
if rr.status_code != 200:
    print(f"  ❌ Recap failed: {rr.status_code} | {rr.text[:200]}"); sys.exit(1)
recap_data = rr.json()
recap_id = recap_data.get('recapId') or recap_data.get('id') or ''
total = recap_data.get('total', 0)
print(f"  ✅ recapId: {recap_id} | €{total}")

# ── Step 3: Solve Turnstile ───────────────────────────────────────────────────
print(f"\n[3] Solving Turnstile (this takes ~30s)...")
api_key = os.getenv('TWOCAPTCHA_API_KEY')
token = _solve_one_token(api_key)
if not token:
    print("  ❌ Token solve failed"); sys.exit(1)
print(f"  ✅ Token: prefix={token[:4]} | len={len(token)}")

# ── Step 4: Reservation ───────────────────────────────────────────────────────
print(f"\n[4] Reservation...")
rep = profile.to_representative_user()
participant_list = [
    {"surname": " ", "name": " ", "id": 60, "ticketType": "intero", "services": [58]}
    for _ in range(VISITORS)
]

res_body = {
    "recaptcha": token,
    "lang": "it",
    "recapId": recap_id,
    "visitorNum": int(VISITORS),
    "visitId": str(slot_id),
    "visitTypeId": int(tid),
    "tickets": [
        {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(VISITORS)},
        {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
    ],
    "services": [
        {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(VISITORS)}
    ],
    "representativeUser": rep,
    "participantUser": participant_list,
    "gdpr": [{"id": 1, "check": True}, {"id": 3, "check": True}],
}

print(f"  Payload: {json.dumps(res_body, indent=2)[:800]}")
print(f"\n  Sending reservation request...")

res_r = s.post(f'{BASE}/api/visit/reservation', json=res_body, headers=HC, timeout=20)
print(f"\n  HTTP Status: {res_r.status_code}")
print(f"  Response headers: {dict(res_r.headers)}")
print(f"  Response body: {res_r.text[:1000]}")

if res_r.status_code == 200:
    try:
        data = res_r.json()
        print(f"\n  ✅ SUCCESS!")
        print(f"  Full response: {json.dumps(data, indent=2)}")
        # Extract epay URL
        epay_url = (data.get('epay', {}).get('url') or
                    data.get('paymentUrl') or data.get('redirectUrl') or '')
        siv = data.get('sivTransactionId') or data.get('transactionId') or ''
        mac = data.get('uppRedirectMac') or data.get('mac') or ''
        ref = data.get('referenceOrder') or data.get('reference') or ''
        print(f"\n  epay_url: {epay_url}")
        print(f"  sivTransactionId: {siv}")
        print(f"  uppRedirectMac: {mac}")
        print(f"  referenceOrder: {ref}")
    except Exception as e:
        print(f"  Response (not JSON): {res_r.text[:500]}")
else:
    print(f"\n  ❌ FAILED: {res_r.status_code}")
    # Try to get more info
    try:
        err = res_r.json()
        print(f"  Error JSON: {json.dumps(err, indent=2)}")
    except:
        print(f"  Error text: {res_r.text[:500]}")
    
    # Check if slot is still available
    print(f"\n  Checking slot availability after failure...")
    r_check = s.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
        'visitorNum': str(VISITORS), 'visitDate': date,
    }, headers=H_XHR, timeout=8)
    if r_check.status_code == 200:
        slot_status = next((sl.get('availability') for sl in r_check.json().get('timetable', [])
                            if str(sl.get('id')) == slot_id), 'NOT_FOUND')
        print(f"  Slot {slot_id} status: {slot_status}")
