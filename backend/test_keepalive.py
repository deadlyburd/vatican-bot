"""
Test keepalive behavior:
Q1: Can the SAME session re-recap a locked slot to extend the hold?
Q2: Can a DIFFERENT session re-recap a locked slot?
Q3: After re-recap, does the hold timer reset to ~55 min?
"""
import os, sys, django, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.epay_ssl import make_vatican_session
from datetime import datetime, timedelta

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

def get_tid(session, date, visitors):
    r = session.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date,
        'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers=H_XHR, timeout=10)
    if r.status_code != 200: return None
    t = next((v for v in r.json().get('visits', [])
               if 'musei vaticani' in v.get('name','').lower()
               and 'ingresso' in v.get('name','').lower()), None)
    return t['id'] if t else None

def recap(session, slot_id, tid, visitors):
    body = {
        "visitId": str(slot_id), "visitTypeId": int(tid),
        "visitorNum": int(visitors), "lang": "it",
        "tickets": [
            {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(visitors)},
            {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
        ],
        "additionalCosts": {"service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(visitors)}},
        "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(visitors)}],
    }
    t0 = time.time()
    r = session.post(f'{BASE}/api/visit/recap', json=body, headers=HC, timeout=10)
    ms = int((time.time()-t0)*1000)
    if r.status_code == 200:
        rd = r.json()
        return True, rd.get('recapId',''), ms
    try: msg = r.json().get('message', r.text[:100])
    except: msg = r.text[:100]
    return False, msg, ms

def outside_status(date, slot_id, visitors=1):
    s = make_vatican_session()
    tid = get_tid(s, date, visitors)
    if not tid: return 'NO_TID'
    r2 = s.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
        'visitorNum': str(visitors), 'visitDate': date,
    }, headers=H_XHR, timeout=10)
    return next((sl.get('availability') for sl in r2.json().get('timetable', [])
                 if str(sl.get('id')) == str(slot_id)), 'NOT_FOUND')

# ── Step 1: Find and lock a fresh slot ───────────────────────────────────────
print("Finding fresh available slot...")
sA = make_vatican_session()
found = None
for days in range(1, 120):
    d = (datetime.now() + timedelta(days=days)).strftime('%d/%m/%Y')
    tid = get_tid(sA, d, 1)
    if not tid: continue
    r2 = sA.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
        'visitorNum': '1', 'visitDate': d,
    }, headers=H_XHR, timeout=10)
    if r2.status_code != 200: continue
    slots = [sl for sl in r2.json().get('timetable', [])
             if sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')]
    if slots:
        found = {'date': d, 'tid': tid, 'slot': slots[0]}
        break
    time.sleep(0.05)

if not found:
    print("No available slots"); sys.exit(1)

date, tid, slot = found['date'], found['tid'], found['slot']
slot_id, slot_time = str(slot['id']), slot['time']
print(f"Found: {date} {slot_time} (id={slot_id})")

# Lock it with Session A (1 visitor)
ok, recap_id_1, ms1 = recap(sA, slot_id, tid, 1)
print(f"Initial lock (Session A, 1v): {'✅ ' + recap_id_1 if ok else '❌ ' + recap_id_1} ({ms1}ms)")
if not ok:
    print("Lock failed — slot may already be taken"); sys.exit(1)

jsid_A = sA.cookies.get('JSESSIONID','')
print(f"Session A JSESSIONID: {jsid_A[:20]}...")
print(f"Outside status: {outside_status(date, slot_id, 1)}")

# ── Q1: Same session re-recap ─────────────────────────────────────────────────
print(f"\n--- Q1: Same session (A) re-recaps the locked slot ---")
tid_A2 = get_tid(sA, date, 1)
ok2, recap_id_2, ms2 = recap(sA, slot_id, tid_A2 or tid, 1)
jsid_A2 = sA.cookies.get('JSESSIONID','')
print(f"Same session re-recap: {'✅ ' + recap_id_2 if ok2 else '❌ ' + recap_id_2} ({ms2}ms)")
print(f"Session A JSESSIONID after: {jsid_A2[:20]}... (same={jsid_A==jsid_A2})")
print(f"Outside status: {outside_status(date, slot_id, 1)}")

# ── Q2: Different session re-recap ────────────────────────────────────────────
print(f"\n--- Q2: Different session (B) tries to re-recap the locked slot ---")
sB = make_vatican_session()
tid_B = get_tid(sB, date, 1)
ok3, recap_id_3, ms3 = recap(sB, slot_id, tid_B or tid, 1)
jsid_B = sB.cookies.get('JSESSIONID','')
print(f"Different session recap: {'✅ ' + recap_id_3 if ok3 else '❌ ' + recap_id_3} ({ms3}ms)")
print(f"Session B JSESSIONID: {jsid_B[:20]}...")
print(f"Outside status: {outside_status(date, slot_id, 1)}")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"RESULTS:")
print(f"  Q1 Same session keepalive:    {'✅ WORKS' if ok2 else '❌ FAILS'}")
print(f"  Q2 Different session recap:   {'✅ WORKS' if ok3 else '❌ FAILS'}")
print(f"")
if ok2 and not ok3:
    print(f"  → Keepalive MUST use the ORIGINAL session")
    print(f"  → Store JSESSIONID + ticketmv per held slot")
    print(f"  → Re-recap with same cookies every 30 min")
elif ok2 and ok3:
    print(f"  → Any session can keepalive — simpler!")
    print(f"  → Fresh session every keepalive is fine")
elif not ok2 and not ok3:
    print(f"  → Neither works — slot may have been released already")

from zoneinfo import ZoneInfo
rome = ZoneInfo('Europe/Rome')
dt_rome = datetime.strptime(date, '%d/%m/%Y')
ts = int(datetime(dt_rome.year, dt_rome.month, dt_rome.day, 0, 0, 0, tzinfo=rome).timestamp() * 1000)
print(f"\nVerify: https://tickets.museivaticani.va/home/visit/1/{ts}/1/")
print(f"Check {date} → {slot_time}")
