"""
Watch a slot and report exactly when it transitions from SOLD_OUT back to AVAILABLE.
This tells us the true hold duration without any keepalive.
Run AFTER hold_and_keepalive.py has locked a slot.
"""
import requests, sys, time
from datetime import datetime

BASE = 'https://tickets.museivaticani.va'
H = {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest',
     'Referer': f'{BASE}/', 'User-Agent': 'Mozilla/5.0'}

# Update these from the last hold_and_keepalive.py run
DATE      = '18/05/2026'
SLOT_TIME = '17:00'
VISITORS  = 1

s = requests.Session()

def get_slot_status():
    # Get fresh ticket_id
    r = s.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': DATE,
        'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers=H, timeout=8)
    if r.status_code != 200:
        return None, None
    ticket = next((v for v in r.json().get('visits', [])
                   if 'musei vaticani' in v.get('name', '').lower()
                   and 'ingresso' in v.get('name', '').lower()), None)
    if not ticket:
        return None, None
    tid = ticket['id']
    r2 = s.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
        'visitorNum': str(VISITORS), 'visitDate': DATE,
    }, headers=H, timeout=8)
    if r2.status_code != 200:
        return None, None
    for sl in r2.json().get('timetable', []):
        if sl.get('time') == SLOT_TIME:
            return sl.get('availability'), sl.get('id')
    return 'NOT_FOUND', None

print(f"Watching {DATE} {SLOT_TIME} — checking every 30s")
print(f"Will report when slot transitions from SOLD_OUT to AVAILABLE\n")

start = time.time()
last_status = None

while True:
    status, slot_id = get_slot_status()
    elapsed = int(time.time() - start)
    now = datetime.now().strftime('%H:%M:%S')

    if status != last_status:
        print(f"\n[{now}] STATUS CHANGED: {last_status} → {status} (after {elapsed}s / {elapsed//60}m{elapsed%60}s)")
        if status in ('AVAILABLE', 'LOW_AVAILABILITY') and last_status == 'SOLD_OUT':
            print(f"\n✅ HOLD EXPIRED after {elapsed} seconds ({elapsed/60:.1f} minutes)")
            print(f"Slot {slot_id} is now available again.")
            break
        last_status = status
    else:
        sys.stdout.write(f'\r  [{now}] {status} | elapsed {elapsed}s ({elapsed//60}m{elapsed%60}s)   ')
        sys.stdout.flush()

    time.sleep(30)
