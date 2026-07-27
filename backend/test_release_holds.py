"""
Release all held slots by letting sessions expire.
Vatican has no explicit "release" API — the hold expires when the session
is abandoned and the ~55 min window passes.

BUT: we can force-release by calling recap with 0 visitors or by
simply checking if Vatican has any cancel/release endpoint.

Actually the simplest way: just wait. Sessions are in-memory only.
Since we're not keepaliving, they'll expire in ~55 min naturally.

For IMMEDIATE release: we need to check if Vatican has a cancel endpoint.
Let's probe that, and also show current status.
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

DATE = '11/04/2026'
SLOT_ID = '2026*7702'  # the 15:00 slot we locked

# ── Check current status ──────────────────────────────────────────────────────
print(f"Current status of {DATE} 15:00 slot...")

def check(visitors=1):
    s = make_vatican_session()
    r = s.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(visitors), 'visitDate': DATE,
        'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers=H_XHR, timeout=10)
    ticket = next((v for v in r.json().get('visits', [])
                   if 'musei vaticani' in v.get('name','').lower()
                   and 'ingresso' in v.get('name','').lower()), None)
    if not ticket:
        return 'NO_TICKET', None
    tid = ticket['id']
    r2 = s.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
        'visitorNum': str(visitors), 'visitDate': DATE,
    }, headers=H_XHR, timeout=10)
    status = next((sl.get('availability') for sl in r2.json().get('timetable', [])
                   if str(sl.get('id')) == SLOT_ID), 'NOT_FOUND')
    return status, tid

status_1v, tid = check(1)
status_2v, _ = check(2)
print(f"  1 visitor: {status_1v}")
print(f"  2 visitors: {status_2v}")

# ── Try Vatican's cancel/back endpoint ───────────────────────────────────────
print(f"\nProbing Vatican cancel endpoints...")

s_test = make_vatican_session()
# First get a session going
s_test.get(f'{BASE}/api/search/resultPerTag', params={
    'lang': 'it', 'visitorNum': '1', 'visitDate': DATE,
    'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
}, headers=H_XHR, timeout=10)

# Try known cancel/back endpoints
cancel_endpoints = [
    ('GET',  f'{BASE}/api/visit/cancel'),
    ('POST', f'{BASE}/api/visit/cancel'),
    ('GET',  f'{BASE}/api/visit/back'),
    ('POST', f'{BASE}/api/visit/back'),
    ('GET',  f'{BASE}/api/visit/release'),
    ('POST', f'{BASE}/api/visit/release'),
    ('GET',  f'{BASE}/home/checkout/cancel/it/{SLOT_ID}/SIV001'),
]

for method, url in cancel_endpoints:
    try:
        if method == 'GET':
            r = s_test.get(url, headers=H_XHR, timeout=5)
        else:
            r = s_test.post(url, json={"visitId": SLOT_ID}, headers=HC, timeout=5)
        if r.status_code not in (404, 405):
            print(f"  {method} {url.split(BASE)[1]} → {r.status_code}: {r.text[:80]}")
        else:
            print(f"  {method} {url.split(BASE)[1]} → {r.status_code} (not found)")
    except Exception as e:
        print(f"  {method} {url.split(BASE)[1]} → error: {e}")

# ── The real release: navigate away (back button behavior) ───────────────────
print(f"\nTrying 'back' navigation (what browser does when user clicks back)...")
# From epay.catholica.va.txt: urlback = https://tickets.museivaticani.va/home/checkout/cancel/it/{ref}/SIV001
# This is what Vatican calls when payment is cancelled
# Let's try hitting the checkout/cancel URL pattern

s_back = make_vatican_session()
# First establish session
s_back.get(f'{BASE}/api/search/resultPerTag', params={
    'lang': 'it', 'visitorNum': '1', 'visitDate': DATE,
    'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
}, headers=H_XHR, timeout=10)

# Try the recap cancel via checkout back
back_urls = [
    f'{BASE}/home/checkout/cancel/it/{SLOT_ID}/SIV001',
    f'{BASE}/home/checkout/back',
    f'{BASE}/api/visit/checkout/cancel',
]
for url in back_urls:
    try:
        r = s_back.get(url, headers={**H_XHR, 'Referer': f'{BASE}/home/checkout'}, timeout=5)
        print(f"  GET {url.split(BASE)[1]} → {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"  GET {url.split(BASE)[1]} → {e}")

# ── Check status after probing ────────────────────────────────────────────────
print(f"\nStatus after probing:")
status_1v_after, _ = check(1)
status_2v_after, _ = check(2)
print(f"  1 visitor: {status_1v_after}")
print(f"  2 visitors: {status_2v_after}")

if status_1v_after != status_1v:
    print(f"  ✅ Status changed! {status_1v} → {status_1v_after}")
else:
    print(f"  Status unchanged — hold is still active")
    print(f"\n  Vatican holds expire naturally after ~55 min.")
    print(f"  No explicit release API found.")
    print(f"  The slot will become available again automatically.")

from zoneinfo import ZoneInfo
rome = ZoneInfo('Europe/Rome')
dt_rome = datetime.strptime(DATE, '%d/%m/%Y')
ts = int(datetime(dt_rome.year, dt_rome.month, dt_rome.day, 0, 0, 0, tzinfo=rome).timestamp() * 1000)
print(f"\nBrowser URL to check: https://tickets.museivaticani.va/home/visit/1/{ts}/1/")
