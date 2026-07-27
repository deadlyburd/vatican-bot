"""
Find one available slot, recap it (lock it), then show:
1. The slot details
2. Proof it's locked (Session B sees SOLD_OUT)
3. Vatican website URL to verify in browser
"""
import os, sys, django, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.epay_ssl import make_vatican_session
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

# ── Find first available slot ─────────────────────────────────────────────────
print("Scanning for available slot...")
sA = make_vatican_session()
found = None

for days in range(1, 120):
    d = (datetime.now() + timedelta(days=days)).strftime('%d/%m/%Y')
    r = sA.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': d,
        'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers=H_XHR, timeout=10)
    if r.status_code != 200: continue
    ticket = next((v for v in r.json().get('visits', [])
                   if 'musei vaticani' in v.get('name','').lower()
                   and 'ingresso' in v.get('name','').lower()
                   and v.get('availability') in ('AVAILABLE','LOW_AVAILABILITY')), None)
    if not ticket: continue
    tid = ticket['id']
    r2 = sA.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
        'visitorNum': str(VISITORS), 'visitDate': d,
    }, headers=H_XHR, timeout=10)
    if r2.status_code != 200: continue
    slots = [sl for sl in r2.json().get('timetable', [])
             if sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')]
    if slots:
        found = {'date': d, 'tid': tid, 'slot': slots[0]}
        print(f"Found: {d} {slots[0]['time']} | availability={slots[0]['availability']}")
        break
    time.sleep(0.05)

if not found:
    print("No available slots found right now"); sys.exit(1)

date = found['date']
tid = found['tid']
slot = found['slot']
slot_id = str(slot['id'])
slot_time = slot['time']

# ── Recap (lock it) ───────────────────────────────────────────────────────────
print(f"\nRecapping slot {slot_time} on {date}...")
body = {
    "visitId": slot_id, "visitTypeId": int(tid), "visitorNum": VISITORS, "lang": "it",
    "tickets": [
        {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(VISITORS)},
        {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
    ],
    "additionalCosts": {"service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": VISITORS}},
    "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": VISITORS}],
}
t0 = time.time()
rr = sA.post(f'{BASE}/api/visit/recap', json=body, headers=HC, timeout=10)
elapsed = int((time.time()-t0)*1000)

if rr.status_code != 200:
    print(f"Recap failed: {rr.status_code} {rr.text[:200]}"); sys.exit(1)

rd = rr.json()
recap_id = rd.get('recapId','')
total = rd.get('total', 0)
print(f"✅ Recap OK in {elapsed}ms | recapId={recap_id} | €{total}")

# ── Verify lock from Session B ────────────────────────────────────────────────
print(f"\nVerifying lock from fresh session...")
sB = make_vatican_session()
rB = sB.get(f'{BASE}/api/search/resultPerTag', params={
    'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': date,
    'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
}, headers=H_XHR, timeout=10)
ticketB = next((v for v in rB.json().get('visits',[])
                if 'musei vaticani' in v.get('name','').lower()
                and 'ingresso' in v.get('name','').lower()), None)
tidB = ticketB['id'] if ticketB else tid

rB2 = sB.get(f'{BASE}/api/visit/timeavail', params={
    'lang': 'it', 'visitLang': '', 'visitTypeId': str(tidB),
    'visitorNum': str(VISITORS), 'visitDate': date,
}, headers=H_XHR, timeout=10)

slot_status_B = next(
    (sl.get('availability') for sl in rB2.json().get('timetable',[])
     if str(sl.get('id')) == slot_id),
    'NOT_FOUND'
)

# ── Build Vatican website URL ─────────────────────────────────────────────────
from zoneinfo import ZoneInfo
rome = ZoneInfo('Europe/Rome')
dt_rome = datetime.strptime(date, '%d/%m/%Y')
ts = int(datetime(dt_rome.year, dt_rome.month, dt_rome.day, 0, 0, 0, tzinfo=rome).timestamp() * 1000)
vatican_url = f"https://tickets.museivaticani.va/home/visit/{VISITORS}/{ts}/1/"

print(f"\n{'='*60}")
print(f"SLOT LOCKED ✅")
print(f"{'='*60}")
print(f"Date:      {date}")
print(f"Time:      {slot_time}")
print(f"Visitors:  {VISITORS}")
print(f"Total:     €{total}")
print(f"recapId:   {recap_id}")
print(f"slot_id:   {slot_id}")
print(f"")
print(f"Session B sees slot as: {slot_status_B}")
if slot_status_B == 'SOLD_OUT':
    print(f"🔒 CONFIRMED LOCKED — nobody else can book this slot")
else:
    print(f"⚠️  Slot shows {slot_status_B} from outside")
print(f"")
print(f"{'='*60}")
print(f"OPEN IN BROWSER TO VERIFY:")
print(f"{vatican_url}")
print(f"{'='*60}")
print(f"")
print(f"On that page, select {VISITORS} visitors and check {date}")
print(f"The {slot_time} slot should show as SOLD OUT / unavailable")
print(f"Hold expires in ~55 minutes from now")
