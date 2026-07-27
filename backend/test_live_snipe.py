"""
Live Snipe Test
===============
1. Scan all dates for a real open slot
2. Run lightning_snipe on it
3. Print the proxy payment URL
"""
import os, sys, django, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

import requests
from monitors.epay_ssl import make_vatican_session
from monitors.models import MonitorTask, Agency, BuyerProfile

BASE = 'https://tickets.museivaticani.va'
HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE}/',
    'Origin': BASE,
}

def sep(t=''):
    print(f"\n{'━'*60}")
    if t: print(f"  {t}"); print(f"{'━'*60}")

# ── Setup ──────────────────────────────────────────────────────────────────────
sep("SETUP")
agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
task = MonitorTask.objects.filter(is_active=True, site='vatican').first()
profile = BuyerProfile.objects.filter(agency=agency).first() if agency else None

print(f"  Agency:  {agency.name if agency else 'NONE'}")
print(f"  Task:    #{task.id} | tier={task.tier}" if task else "  Task:   NONE")
print(f"  Profile: {profile.first_name} {profile.last_name}" if profile else "  Profile: NONE")

if not profile:
    print("\n❌ No buyer profile — run /setprofile in Telegram bot first")
    sys.exit(1)

# ── Scan for open slot ─────────────────────────────────────────────────────────
sep("SCANNING FOR OPEN SLOT")
print("  Checking April-June 2026 dates...")

from datetime import datetime, timedelta

found_date = found_slot = found_ticket_id = found_session = None

for days in range(1, 120):
    d = (datetime.now() + timedelta(days=days)).strftime('%d/%m/%Y')
    s = make_vatican_session()
    try:
        r = s.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': '1', 'visitDate': d,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            continue

        ticket = next((v for v in r.json().get('visits', [])
                       if 'musei vaticani' in v.get('name', '').lower()
                       and 'ingresso' in v.get('name', '').lower()
                       and v.get('availability') == 'AVAILABLE'), None)
        if not ticket:
            print(f"  ✗ {d} — sold out", end='\r')
            time.sleep(0.1)
            continue

        tid = ticket['id']
        r2 = s.get(f'{BASE}/api/visit/timeavail', params={
            'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
            'visitorNum': '1', 'visitDate': d,
        }, headers=HEADERS, timeout=10)
        if r2.status_code != 200:
            continue

        slots = [sl for sl in r2.json().get('timetable', [])
                 if sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')]
        if slots:
            print(f"\n  ✅ OPEN: {d} — {len(slots)} slots")
            for sl in slots[:5]:
                print(f"     ⏰ {sl.get('time')} | {sl.get('availability')} | id={sl.get('id')}")
            found_date = d
            found_slot = slots[0]
            found_ticket_id = tid
            found_session = s
            break

        time.sleep(0.1)
    except Exception as e:
        print(f"  ⚠ {d}: {e}", end='\r')
        continue

print()

if not found_slot:
    print("❌ No open slots found. Vatican is fully booked right now.")
    sys.exit(0)

slot_id = found_slot.get('id')
slot_time = found_slot.get('time')
ticket_name = "Musei Vaticani - Biglietti d'ingresso"
visitors = 1

sep(f"RUNNING LIGHTNING SNIPE")
print(f"  Date:     {found_date}")
print(f"  Time:     {slot_time}")
print(f"  Slot ID:  {slot_id}")
print(f"  Ticket:   {found_ticket_id}")
print(f"  Visitors: {visitors}")
print(f"  Profile:  {profile.first_name} {profile.last_name}")
print()

# ── Run lightning snipe ────────────────────────────────────────────────────────
import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
for noisy in ['urllib3', 'httpx', 'celery', 'django', 'asyncio']:
    logging.getLogger(noisy).setLevel(logging.WARNING)

# Only solve 1 token for this test — don't waste the pool
import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.turnstile_pool import pool_size, POOL_KEY, POOL_SIZE, _solve_one_token, POOL_CACHE_TTL
from django.core.cache import cache
import time

# Ensure at least 1 token in pool (solve only what's needed)
current = pool_size()
print(f"Pool size: {current}/{POOL_SIZE}")
if current == 0:
    api_key = os.getenv('TWOCAPTCHA_API_KEY')
    if api_key:
        print("Solving 1 token for test...")
        token = _solve_one_token(api_key)
        if token:
            pool = cache.get(POOL_KEY, [])
            pool.append({'token': token, 'solved_at': time.time()})
            cache.set(POOL_KEY, pool, timeout=POOL_CACHE_TTL)
            print(f"✅ 1 token ready (pool: {pool_size()})")
        else:
            print("❌ Token solve failed")
    else:
        print("⚠️ No TWOCAPTCHA_API_KEY — will fail at Turnstile step")

from monitors.lightning_snipe import lightning_snipe

t0 = time.monotonic()
result = lightning_snipe(
    task=task,
    date=found_date,
    slot_id=str(slot_id),
    slot_time=slot_time,
    ticket_id=str(found_ticket_id),
    ticket_name=ticket_name,
    visitors=visitors,
)
elapsed = int((time.monotonic() - t0) * 1000)

sep("RESULT")
if result['success']:
    print(f"  ✅ SNIPE SUCCEEDED in {result['elapsed_ms']}ms")
    print(f"  Hold ID:   #{result['hold_id']}")
    print(f"  Reference: {result['reference']}")
    print(f"  Total:     €{result['total']}")
    print(f"\n  💳 PROXY PAYMENT URL (open in any browser):")
    print(f"  {result['proxy_url']}")
    print(f"\n  Raw epay URL (session-bound, expires ~10min):")
    print(f"  {result['epay_url']}")
    print(f"\n  ⚠️  Open the PROXY URL — it re-fires the chain and works anywhere")
else:
    print(f"  ❌ SNIPE FAILED: {result['error']}")
    print(f"  Elapsed: {result['elapsed_ms']}ms")
