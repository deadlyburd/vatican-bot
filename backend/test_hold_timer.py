"""
Hold timer test — polls every 30s until Vatican releases the slot.
Slot 11/04/2026 14:30 (2026*7701) is already locked from previous run.
Just polls and records exact release time.
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

POLL_INTERVAL = 30

# Already locked slot from previous run at 00:45:23
DATE = '11/04/2026'
SLOT_ID = '2026*7701'
SLOT_TIME = '14:30'
LOCK_TIME_STR = '00:45:23'  # when we locked it

def get_slot_status(date, slot_id, visitors=1):
    try:
        s = make_vatican_session()
        r = s.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=H_XHR, timeout=12)
        if r.status_code != 200:
            return 'HTTP_ERR'
        t = next((v for v in r.json().get('visits', [])
                   if 'musei vaticani' in v.get('name','').lower()
                   and 'ingresso' in v.get('name','').lower()), None)
        if not t:
            return 'NO_TICKET'
        tid = t['id']
        r2 = s.get(f'{BASE}/api/visit/timeavail', params={
            'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
            'visitorNum': str(visitors), 'visitDate': date,
        }, headers=H_XHR, timeout=12)
        if r2.status_code != 200:
            return 'HTTP_ERR'
        return next((sl.get('availability') for sl in r2.json().get('timetable', [])
                     if str(sl.get('id')) == str(slot_id)), 'NOT_FOUND')
    except Exception as e:
        return f'ERR:{e.__class__.__name__}'

# ── Initial check ─────────────────────────────────────────────────────────────
print(f"Resuming timer for {DATE} {SLOT_TIME} (locked at {LOCK_TIME_STR})")
t_start = time.time()
initial = get_slot_status(DATE, SLOT_ID, 1)
print(f"Current status: {initial}")
print(f"Browser: https://tickets.museivaticani.va/home/visit/1/1775858400000/1/")
print(f"\n{'─'*55}")
print(f"{'Elapsed':>10} | {'Wall time':>10} | {'Status'}")
print(f"{'─'*55}")

# ── Poll ──────────────────────────────────────────────────────────────────────
while True:
    time.sleep(POLL_INTERVAL)
    elapsed_s = int(time.time() - t_start)
    elapsed_min = elapsed_s / 60
    now_str = datetime.now().strftime('%H:%M:%S')

    status = get_slot_status(DATE, SLOT_ID, 1)
    print(f"{elapsed_min:>8.1f}m | {now_str:>10} | {status}")
    sys.stdout.flush()

    if status in ('AVAILABLE', 'LOW_AVAILABILITY'):
        print(f"\n{'='*55}")
        print(f"🔓 RELEASED at {now_str}")
        print(f"   Locked at:    {LOCK_TIME_STR}")
        print(f"   Released at:  {now_str}")
        print(f"   Since script start: {elapsed_min:.1f} min")
        print(f"   (Add time since original lock for total hold duration)")
        print(f"{'='*55}")
        break

    if elapsed_min > 90:
        print(f"\nTimeout — still {status} after 90 min of polling")
        break
