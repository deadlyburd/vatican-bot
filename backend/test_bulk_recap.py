"""
Test bulk recap capabilities:
1. Can we recap multiple slots on the SAME date from one session?
2. Can we recap slots across MULTIPLE dates from one session?
3. Does each recap need a fresh session/JSESSIONID?
4. What happens when we try to recap 5+ slots concurrently?
5. Does Vatican rate-limit or block bulk recaps?

This tells us the real limits for locking 40 tickets/day across 30-60 days.
"""
import os, sys, django, time, json
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.epay_ssl import make_vatican_session

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

def get_slots(session, date, visitors=2):
    """Get available slots for a date."""
    r = session.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date,
        'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers=H_XHR, timeout=10)
    if r.status_code != 200:
        return None, []
    ticket = next((v for v in r.json().get('visits', [])
                   if 'musei vaticani' in v.get('name','').lower()
                   and 'ingresso' in v.get('name','').lower()), None)
    if not ticket or ticket.get('availability') not in ('AVAILABLE', 'LOW_AVAILABILITY'):
        return None, []
    tid = ticket['id']
    r2 = session.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
        'visitorNum': str(visitors), 'visitDate': date,
    }, headers=H_XHR, timeout=10)
    if r2.status_code != 200:
        return tid, []
    slots = [sl for sl in r2.json().get('timetable', [])
             if sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')]
    return tid, slots

def do_recap(session, slot_id, tid, visitors=2):
    """Call recap for a slot. Returns (success, recap_id, elapsed_ms)."""
    t0 = time.time()
    body = {
        "visitId": str(slot_id), "visitTypeId": int(tid),
        "visitorNum": int(visitors), "lang": "it",
        "tickets": [
            {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(visitors)},
            {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
        ],
        "additionalCosts": {"service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(visitors)}},
        "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(visitors)}]
    }
    r = session.post(f'{BASE}/api/visit/recap', json=body, headers=HC, timeout=10)
    elapsed = int((time.time() - t0) * 1000)
    if r.status_code == 200:
        rd = r.json()
        return True, rd.get('recapId',''), elapsed, rd.get('total', 0)
    else:
        try:
            msg = r.json().get('message', r.text[:100])
        except:
            msg = r.text[:100]
        return False, msg, elapsed, 0

# ─────────────────────────────────────────────────────────────────────────────
# Find dates with available slots
# ─────────────────────────────────────────────────────────────────────────────
from datetime import datetime, timedelta

print("Finding dates with available slots...")
available_dates = []
s_probe = make_vatican_session()
for days in range(1, 90):
    d = (datetime.now() + timedelta(days=days)).strftime('%d/%m/%Y')
    tid, slots = get_slots(s_probe, d)
    if slots:
        available_dates.append((d, tid, slots))
        print(f"  {d}: {len(slots)} slots available (tid={tid})")
    if len(available_dates) >= 3:
        break
    time.sleep(0.1)

if not available_dates:
    print("No available dates found"); sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Multiple slots on SAME date, SAME session
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("TEST 1: Multiple slots on SAME date, SAME session")
print('='*60)

date1, tid1, slots1 = available_dates[0]
print(f"Date: {date1} | {len(slots1)} available slots")

s1 = make_vatican_session()
tid1_fresh, slots1_fresh = get_slots(s1, date1)
if not slots1_fresh:
    print("No slots available for test 1"); 
else:
    recap_results = []
    for i, slot in enumerate(slots1_fresh[:4]):  # try up to 4 slots
        sid = slot['id']
        stime = slot['time']
        ok, recap_id, elapsed, total = do_recap(s1, sid, tid1_fresh)
        recap_results.append((stime, sid, ok, recap_id, elapsed))
        status = f"✅ recapId={recap_id} €{total}" if ok else f"❌ {recap_id}"
        print(f"  Slot {i+1}: {stime} (id={sid}) → {status} ({elapsed}ms)")
        time.sleep(0.1)

    locked = sum(1 for _, _, ok, _, _ in recap_results if ok)
    print(f"\n  Result: {locked}/{len(recap_results)} slots locked on {date1} from ONE session")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: Same slot, DIFFERENT sessions (can 2 sessions recap same slot?)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("TEST 2: Same slot, TWO different sessions")
print('='*60)

if len(slots1_fresh) >= 2:
    # Use a slot we haven't recapped yet
    unused_slots = [sl for sl in slots1_fresh if sl['id'] not in [r[1] for r in recap_results if r[2]]]
    if unused_slots:
        test_slot = unused_slots[0]
        print(f"Testing slot {test_slot['time']} (id={test_slot['id']})")
        
        sA = make_vatican_session()
        tidA, _ = get_slots(sA, date1)
        
        sB = make_vatican_session()
        tidB, _ = get_slots(sB, date1)
        
        okA, ridA, elA, _ = do_recap(sA, test_slot['id'], tidA or tid1_fresh)
        okB, ridB, elB, _ = do_recap(sB, test_slot['id'], tidB or tid1_fresh)
        
        print(f"  Session A: {'✅ ' + ridA if okA else '❌ ' + ridA} ({elA}ms)")
        print(f"  Session B: {'✅ ' + ridB if okB else '❌ ' + ridB} ({elB}ms)")
        
        if okA and okB:
            print(f"\n  ⚠️  BOTH sessions got recap — Vatican allows concurrent recaps on same slot!")
            print(f"  This means recap does NOT exclusively lock — first to pay wins")
        elif okA and not okB:
            print(f"\n  🔒 Session A locked it, Session B blocked — exclusive lock confirmed")
        else:
            print(f"\n  Unexpected result")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: Multiple dates, SAME session
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("TEST 3: Multiple DATES, same session")
print('='*60)

s3 = make_vatican_session()
multi_date_results = []

for date, tid, slots in available_dates[:3]:
    tid_fresh, slots_fresh = get_slots(s3, date)
    if not slots_fresh:
        print(f"  {date}: no slots")
        continue
    slot = slots_fresh[0]
    ok, recap_id, elapsed, total = do_recap(s3, slot['id'], tid_fresh or tid)
    multi_date_results.append((date, slot['time'], ok, recap_id, elapsed))
    status = f"✅ {recap_id}" if ok else f"❌ {recap_id}"
    print(f"  {date} {slot['time']}: {status} ({elapsed}ms)")
    time.sleep(0.2)

locked3 = sum(1 for _, _, ok, _, _ in multi_date_results if ok)
print(f"\n  Result: {locked3}/{len(multi_date_results)} dates locked from ONE session")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("SUMMARY — Bulk Recap Capabilities")
print('='*60)
print(f"Test 1 (multi-slot, same date, same session): {locked}/{len(recap_results)} locked")
print(f"Test 3 (multi-date, same session): {locked3}/{len(multi_date_results)} locked")
print()
print("Extrapolation for 40 tickets/day × 30 days:")
print(f"  = 40 recap calls per day × 30 days = 1,200 total recaps needed")
print(f"  Each recap: ~0.2s → 1,200 recaps = ~4 min total")
print(f"  Keepalive every 30 min: 1,200 × 2 keepalives/hour × 24h = 57,600 keepalives/day")
print(f"  (keepalive = just another recap call, no token needed)")
