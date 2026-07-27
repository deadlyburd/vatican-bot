"""
Test the full snipe chain and generate a real epay link.
Run: docker-compose exec -T backend python /app/backend/test_epay_link.py
"""
import os, sys, django, time, json, secrets
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.epay_ssl import make_vatican_session
from monitors.turnstile_pool import _solve_one_token
from monitors.models import BuyerProfile, Agency
from django.core.cache import cache
from datetime import datetime, timedelta

BASE = 'https://tickets.museivaticani.va'
VISITORS = 2

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

agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
profile = BuyerProfile.objects.filter(agency=agency).first()
print(f"Profile: {profile.first_name} {profile.last_name} | {profile.email}")

# ── Step 1: Find open slot ────────────────────────────────────────────────────
s = make_vatican_session()
print("\n[1] Finding open slot...")
found = None
for days in range(1, 120):
    d = (datetime.now() + timedelta(days=days)).strftime('%d/%m/%Y')
    r = s.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': d,
        'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers=H_XHR, timeout=10)
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
    }, headers=H_XHR, timeout=10)
    if r2.status_code != 200: continue
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
print(f"  Found: {date} {slot_time} | slot_id={slot_id} | tid={tid}")

# ── Step 2: Recap ─────────────────────────────────────────────────────────────
print("\n[2] Recap...")
recap_body = {
    "visitId": slot_id, "visitTypeId": int(tid), "visitorNum": int(VISITORS), "lang": "it",
    "tickets": [
        {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(VISITORS)},
        {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
    ],
    "additionalCosts": {"service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(VISITORS)}},
    "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(VISITORS)}]
}
rr = s.post(f'{BASE}/api/visit/recap', json=recap_body, headers=HC, timeout=10)
if rr.status_code != 200:
    print(f"  Recap failed: {rr.status_code} {rr.text[:200]}"); sys.exit(1)
recap_id = rr.json().get('recapId') or ''
total = rr.json().get('total', 0)
print(f"  recapId={recap_id} | total=€{total}")

# ── Step 3: Turnstile ─────────────────────────────────────────────────────────
# Paste a token grabbed from browser DevTools here to test without 2captcha balance.
# How: open tickets.museivaticani.va/home/checkout → DevTools Network → filter 'reservation'
# → copy the 'recaptcha' field value from the request body (valid ~2 min, act fast)
MANUAL_TOKEN = "PASTE_TOKEN_HERE"

print("\n[3] Turnstile token...")
if MANUAL_TOKEN:
    token = MANUAL_TOKEN
    print(f"  Using manual token: prefix={token[:4]} len={len(token)}")
else:
    print("  Solving via 2captcha (~30s)...")
    token = _solve_one_token(os.getenv('TWOCAPTCHA_API_KEY'))
    if not token:
        print("  Token solve failed — top up 2captcha balance or set MANUAL_TOKEN above")
        sys.exit(1)
    print(f"  Token: prefix={token[:4]} len={len(token)}")

# ── Step 4: Reservation ───────────────────────────────────────────────────────
print("\n[4] Reservation...")
res_body = {
    "recaptcha": token, "lang": "it", "recapId": recap_id,
    "visitorNum": int(VISITORS), "visitId": str(slot_id), "visitTypeId": int(tid),
    "tickets": [
        {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(VISITORS)},
        {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
    ],
    "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(VISITORS)}],
    "representativeUser": profile.to_representative_user(),
    "participantUser": [
        {"surname": " ", "name": " ", "id": 60, "ticketType": "intero", "services": [58]}
        for _ in range(VISITORS)
    ],
    "gdpr": [{"id": 1, "check": True}, {"id": 3, "check": True}],
}
res_r = s.post(f'{BASE}/api/visit/reservation', json=res_body, headers=HC, timeout=20)
print(f"  HTTP {res_r.status_code}")
if res_r.status_code != 200:
    print(f"  FAILED: {res_r.text[:300]}"); sys.exit(1)

res_data = res_r.json()
epay = res_data.get('epay', {})
epay_url = epay.get('url', '')
reference = res_data.get('referenceOrder', '')
mac = epay.get('mac_avvio', '')
print(f"  reference={reference}")
print(f"  epay_url={epay_url}")
print(f"  mac_avvio={mac}")
print(f"  Full epay: {json.dumps(epay, indent=2)}")

# ── Step 5: Store in cache and generate proxy link ────────────────────────────
print("\n[5] Generating proxy link...")
proxy_token = secrets.token_urlsafe(32)
fake_hold_id = 9999  # no DB entry needed for this test

epay_params = {
    'mac_avvio': mac,
    'idnegozio': epay.get('idnegozio', 'SIV001'),
    'valuta': epay.get('valuta', '978'),
    'tcontab': epay.get('tcontab', 'D'),
    'tautor': epay.get('tautor', 'I'),
    'urlMs': epay.get('urlMs', ''),
    'urldone': epay.get('urldone', ''),
    'urlback': epay.get('urlback', ''),
    'referenceOrder': reference,
}

cache.set(f"epay_direct:{fake_hold_id}:{proxy_token}", {
    'epay_url': epay_url,
    'epay_params': epay_params,
    'reference': reference,
}, timeout=3600)

base_url = os.getenv('SERVER_BASE_URL', 'https://hydrabot.it')
link = f"{base_url}/pay/direct/{fake_hold_id}/{proxy_token}/"

print(f"\n{'='*60}")
print(f"✅ OPEN THIS LINK IN YOUR BROWSER:")
print(f"\n  {link}\n")
print(f"{'='*60}")
print(f"Reference: {reference}")
print(f"Date: {date} {slot_time} | {VISITORS} visitors | €{total}")
print(f"Link valid for 1 hour")
