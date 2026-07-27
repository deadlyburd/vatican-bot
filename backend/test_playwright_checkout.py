"""
Test Playwright checkout flow.
Does Search → Timeavail → Services → Recap → Browser Checkout → Epay URL
"""
import os, sys, django, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.epay_ssl import make_vatican_session
from monitors.models import BuyerProfile, Agency
from monitors.playwright_checkout import checkout_sync
from datetime import datetime, timedelta

BASE = 'https://tickets.museivaticani.va'
H_XHR = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE}/',
    'Origin': BASE,
    'Content-Type': 'application/json',
}
HC = {**H_XHR, 'Referer': f'{BASE}/home/checkout'}
del HC['X-Requested-With']

agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
profile = BuyerProfile.objects.filter(agency=agency).first()
print(f"Profile: {profile.first_name} {profile.last_name} | {profile.email}")

VISITORS = 2
s = make_vatican_session()

print("Finding open slot...")
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
        print(f"Found: {d} {slots[0]['time']} | slot={slots[0]['id']} | tid={tid}")
        break
    time.sleep(0.1)

if not found:
    print("No open slots"); sys.exit(0)

date, tid, slot = found['date'], found['tid'], found['slot']
slot_id = str(slot['id'])

# Services
r_svc = s.get(f'{BASE}/api/visit/services', params={
    'lang': 'it', 'visitId': slot_id, 'visitTypeId': tid, 'visitorNum': str(VISITORS)
}, headers=H_XHR, timeout=8)
services = [sv for sv in (r_svc.json().get('services', []) if r_svc.status_code == 200 else [])
            if sv.get('id') is not None]
print(f"Services: {[s.get('name') for s in services]}")

# Recap
recap_body = {
    "visitId": slot_id, "visitTypeId": int(tid), "visitorNum": int(VISITORS), "lang": "it",
    "tickets": [
        {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(VISITORS)},
        {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
    ],
    "additionalCosts": {}, "services": []
}
for svc in services[:1]:
    recap_body["additionalCosts"]["service-0"] = {
        "id": svc.get('id',58), "name": svc.get('name','Diritti di Prevendita'),
        "price": svc.get('price',5), "quantity": int(VISITORS)
    }
    recap_body["services"].append({
        "id": svc.get('id',58), "name": svc.get('name','Diritti di Prevendita'),
        "price": svc.get('price',5), "quantity": int(VISITORS)
    })

rr = s.post(f'{BASE}/api/visit/recap', json=recap_body, headers=HC, timeout=10)
if rr.status_code != 200:
    print(f"❌ Recap failed: {rr.status_code}"); sys.exit(1)
recap_id = rr.json().get('recapId') or rr.json().get('id') or ''
total = rr.json().get('total', 0)
print(f"✅ Recap: {recap_id} | €{total}")
print(f"Session: JSESSIONID={s.cookies.get('JSESSIONID','')[:30]}...")

# Playwright checkout
print("\n🌐 Opening browser checkout...")
t0 = time.monotonic()
epay_url = checkout_sync(
    jsessionid=s.cookies.get('JSESSIONID', ''),
    ticketmv=s.cookies.get('ticketmv', ''),
    serverid=s.cookies.get('SERVERID', ''),
    profile=profile,
    visitors=VISITORS,
    timeout_ms=90000,
)
elapsed = int((time.monotonic() - t0) * 1000)

print(f"\n{'='*55}")
if epay_url:
    print(f"✅ SUCCESS in {elapsed}ms!")
    print(f"Epay URL: {epay_url}")
else:
    print(f"❌ FAILED in {elapsed}ms — no epay URL captured")
    print("Check /tmp/checkout_error.png for screenshot")
