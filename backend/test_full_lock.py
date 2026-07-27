"""
Full slot lock test:
- Find available slot
- Recap it repeatedly with multiple sessions until Session B sees SOLD_OUT
- Each recap consumes N visitor slots from the pool
- Keep going until the slot is fully exhausted
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


def check_slot_status(date, slot_id, tid, visitors=1):
    """Check what a fresh session sees for this slot."""
    s = make_vatican_session()
    # fresh search to get current tid
    r = s.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date,
        'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers=H_XHR, timeout=10)
    if r.status_code == 200:
        t = next((v for v in r.json().get('visits', [])
                  if 'musei vaticani' in v.get('name','').lower()
                  and 'ingresso' in v.get('name','').lower()), None)
        if t:
            tid = t['id']
    r2 = s.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
        'visitorNum': str(visitors), 'visitDate': date,
    }, headers=H_XHR, timeout=10)
    if r2.status_code != 200:
        return 'ERROR', s
    status = next((sl.get('availability') for sl in r2.json().get('timetable', [])
                   if str(sl.get('id')) == str(slot_id)), 'NOT_FOUND')
    return status, s


def do_recap(session, slot_id, tid, visitors):
    """Recap a slot. Returns (ok, recap_id, elapsed_ms)."""
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
    elapsed = int((time.time() - t0) * 1000)
    if r.status_code == 200:
        rd = r.json()
        return True, rd.get('recapId', ''), elapsed, rd.get('total', 0)
    try:
        msg = r.json().get('message', r.text[:100])
    except Exception:
        msg = r.text[:100]
    return False, msg, elapsed, 0


# ── Find available slot ───────────────────────────────────────────────────────
print("Finding available slot...")
s_probe = make_vatican_session()
found = None

for days in range(1, 120):
    d = (datetime.now() + timedelta(days=days)).strftime('%d/%m/%Y')
    r = s_probe.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': '1', 'visitDate': d,
        'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers=H_XHR, timeout=10)
    if r.status_code != 200: continue
    ticket = next((v for v in r.json().get('visits', [])
                   if 'musei vaticani' in v.get('name','').lower()
                   and 'ingresso' in v.get('name','').lower()
                   and v.get('availability') in ('AVAILABLE', 'LOW_AVAILABILITY')), None)
    if not ticket: continue
    tid = ticket['id']
    # Check with 1 visitor to find any available slot
    r2 = s_probe.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
        'visitorNum': '1', 'visitDate': d,
    }, headers=H_XHR, timeout=10)
    if r2.status_code != 200: continue
    slots = [sl for sl in r2.json().get('timetable', [])
             if sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')]
    if slots:
        found = {'date': d, 'tid': tid, 'slot': slots[0]}
        print(f"  Found: {d} {slots[0]['time']} | {slots[0]['availability']} | tid={tid}")
        break
    time.sleep(0.05)

if not found:
    print("No available slots"); sys.exit(1)

date = found['date']
tid = found['tid']
slot = found['slot']
slot_id = str(slot['id'])
slot_time = slot['time']

# ── Check initial status with 1 visitor ──────────────────────────────────────
print(f"\nInitial status (1 visitor view):")
status_1v, _ = check_slot_status(date, slot_id, tid, visitors=1)
print(f"  {slot_time} → {status_1v}")

# ── Hammer with recaps until SOLD_OUT ────────────────────────────────────────
print(f"\nLocking slot {slot_time} on {date} with multiple recaps...")
print(f"Each recap = fresh session + 2 visitors consumed from pool")
print(f"Stopping when Session B sees SOLD_OUT\n")

sessions = []  # keep sessions alive (holds are session-bound)
recap_count = 0
total_visitors_locked = 0
MAX_RECAPS = 20  # safety limit

for i in range(MAX_RECAPS):
    # Use 1 visitor for the last ticket if 2v fails
    visitors = 2
    s_new = make_vatican_session()
    
    # Get fresh tid for this session
    r_search = s_new.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date,
        'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers=H_XHR, timeout=10)
    fresh_tid = tid
    if r_search.status_code == 200:
        t = next((v for v in r_search.json().get('visits', [])
                  if 'musei vaticani' in v.get('name','').lower()
                  and 'ingresso' in v.get('name','').lower()), None)
        if t:
            fresh_tid = t['id']

    ok, recap_id, elapsed, total = do_recap(s_new, slot_id, fresh_tid, visitors)
    recap_count += 1

    if ok:
        sessions.append(s_new)
        total_visitors_locked += visitors
        print(f"  Recap #{recap_count}: ✅ {recap_id} | {visitors}v | {elapsed}ms | total locked: {total_visitors_locked}v")
    else:
        print(f"  Recap #{recap_count}: ❌ {recap_id} | {elapsed}ms")
        # If 2v fails, try 1v
        if 'non dispone' in str(recap_id).lower() or 'biglietti' in str(recap_id).lower():
            visitors = 1
            r_search1 = s_new.get(f'{BASE}/api/search/resultPerTag', params={
                'lang': 'it', 'visitorNum': '1', 'visitDate': date,
                'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
            }, headers=H_XHR, timeout=10)
            if r_search1.status_code == 200:
                t1 = next((v for v in r_search1.json().get('visits', [])
                           if 'musei vaticani' in v.get('name','').lower()
                           and 'ingresso' in v.get('name','').lower()), None)
                if t1:
                    fresh_tid = t1['id']
            ok1, recap_id1, elapsed1, total1 = do_recap(s_new, slot_id, fresh_tid, 1)
            recap_count += 1
            if ok1:
                sessions.append(s_new)
                total_visitors_locked += 1
                print(f"  Recap #{recap_count}: ✅ {recap_id1} | 1v | {elapsed1}ms | total locked: {total_visitors_locked}v")
            else:
                print(f"  Recap #{recap_count}: ❌ {recap_id1} | 1v | {elapsed1}ms")
                print(f"  → Slot fully exhausted")
                break

    # Check status from outside after each recap
    status_check, _ = check_slot_status(date, slot_id, fresh_tid, visitors=1)
    print(f"  → Outside view (1v): {status_check}")

    if status_check == 'SOLD_OUT':
        print(f"\n🔒 FULLY LOCKED after {recap_count} recaps ({total_visitors_locked} visitors consumed)")
        break

    time.sleep(0.2)

# ── Final verification ────────────────────────────────────────────────────────
print(f"\n{'='*60}")
final_status_1v, _ = check_slot_status(date, slot_id, tid, visitors=1)
final_status_2v, _ = check_slot_status(date, slot_id, tid, visitors=2)

print(f"FINAL STATUS:")
print(f"  {slot_time} on {date}")
print(f"  1 visitor view:  {final_status_1v}")
print(f"  2 visitor view:  {final_status_2v}")
print(f"  Total recaps:    {recap_count}")
print(f"  Visitors locked: {total_visitors_locked}")

from zoneinfo import ZoneInfo
rome = ZoneInfo('Europe/Rome')
dt_rome = datetime.strptime(date, '%d/%m/%Y')
ts = int(datetime(dt_rome.year, dt_rome.month, dt_rome.day, 0, 0, 0, tzinfo=rome).timestamp() * 1000)
vatican_url = f"https://tickets.museivaticani.va/home/visit/1/{ts}/1/"

print(f"\n{'='*60}")
print(f"VERIFY IN BROWSER (1 visitor):")
print(f"{vatican_url}")
print(f"{'='*60}")
print(f"Check {date} → {slot_time} slot")
if final_status_1v == 'SOLD_OUT':
    print(f"✅ Should show SOLD OUT — slot is fully locked!")
else:
    print(f"⚠️  Still shows {final_status_1v} — Vatican may have more tickets than we recapped")
print(f"Hold expires ~55 min from last recap")
