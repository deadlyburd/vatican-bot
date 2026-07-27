"""
Hold a slot and keep it alive with the SAME session.
Prints the slot status every 30s so you can verify it stays SOLD_OUT.
Ctrl+C to stop.
"""
import requests, sys, time
from datetime import datetime, timedelta

BASE = 'https://tickets.museivaticani.va'
H = {
    'Accept': 'application/json, text/plain, */*',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE}/',
    'Content-Type': 'application/json',
    'Origin': BASE,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}
VISITORS = 1

# ── Find open slot ────────────────────────────────────────────────────────────
print("Finding open slot...")
s = requests.Session()
s.get(f'{BASE}/home', headers=H, timeout=10)

slot_found = None
for i in range(1, 120):
    d = (datetime.now() + timedelta(days=i)).strftime('%d/%m/%Y')
    if datetime.strptime(d, '%d/%m/%Y').weekday() == 6:
        continue
    r = s.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': d,
        'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers=H, timeout=8)
    if r.status_code != 200:
        continue
    ticket = next((v for v in r.json().get('visits', [])
                   if 'musei vaticani' in v.get('name', '').lower()
                   and 'ingresso' in v.get('name', '').lower()
                   and v.get('availability') in ('AVAILABLE', 'LOW_AVAILABILITY')), None)
    if not ticket:
        sys.stdout.write(f'\r  Scanning {d}...')
        sys.stdout.flush()
        continue
    tid = ticket['id']
    r2 = s.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
        'visitorNum': str(VISITORS), 'visitDate': d,
    }, headers=H, timeout=8)
    if r2.status_code != 200:
        continue
    slots = [sl for sl in r2.json().get('timetable', [])
             if sl.get('availability') in ('AVAILABLE', 'LOW_AVAILABILITY')]
    if slots:
        slot_found = {'date': d, 'slot': slots[0], 'ticket_id': tid}
        print(f'\n  Found: {d} {slots[0]["time"]} id={slots[0]["id"]}')
        break
    time.sleep(0.1)

if not slot_found:
    print('No open slots found.')
    sys.exit(1)

date      = slot_found['date']
slot_id   = str(slot_found['slot']['id'])
slot_time = slot_found['slot']['time']
tid       = slot_found['ticket_id']

# ── Get services ──────────────────────────────────────────────────────────────
services = []
r_svc = s.get(f'{BASE}/api/visit/services', params={
    'lang': 'it', 'visitId': slot_id, 'visitTypeId': tid, 'visitorNum': str(VISITORS)
}, headers=H, timeout=8)
if r_svc.status_code == 200:
    services = r_svc.json().get('services', []) or []

def build_recap_body(slot_id, tid, existing_recap_id=None):
    body = {
        "visitId": slot_id,
        "visitTypeId": int(tid),
        "visitorNum": VISITORS,
        "lang": "it",
        "tickets": [
            {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": "1"},
            {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": "0"},
        ],
        "additionalCosts": {},
        "services": []
    }
    if existing_recap_id:
        body["recapId"] = existing_recap_id  # required for keepalive on existing hold
    for svc in services[:1]:
        body["additionalCosts"]["service-0"] = {
            "id": svc.get('id', 58), "name": svc.get('name', 'Diritti di Prevendita'),
            "price": svc.get('price', 5), "quantity": VISITORS
        }
        body["services"].append({
            "id": svc.get('id', 58), "name": svc.get('name', 'Diritti di Prevendita'),
            "price": svc.get('price', 5), "quantity": VISITORS
        })
    return body

# ── Initial recap ─────────────────────────────────────────────────────────────
print(f"\nHolding slot {slot_id} ({date} {slot_time})...")
r_recap = s.post(f'{BASE}/api/visit/recap', json=build_recap_body(slot_id, tid, None), headers=H, timeout=15)
print(f"Recap HTTP {r_recap.status_code}")
if r_recap.status_code != 200:
    print(f"FAILED: {r_recap.text[:200]}")
    sys.exit(1)

d = r_recap.json()
recap_id   = d.get('recapId') or d.get('id')
total      = d.get('total')
jsessionid = s.cookies.get('JSESSIONID', '')

print(f"\n{'='*55}")
print(f"  SLOT HELD!")
print(f"  Date      : {date} {slot_time}")
print(f"  Slot ID   : {slot_id}")
print(f"  recap_id  : {recap_id}")
print(f"  Total     : EUR{total}")
print(f"  JSESSIONID: {jsessionid[:25]}...")
print(f"{'='*55}")
print(f"\nGo check Vatican website — this slot should show SOLD OUT.")
print(f"Keepalive running every 4 minutes. Ctrl+C to release.\n")

# ── Keepalive loop ────────────────────────────────────────────────────────────
def check_status():
    """Check if slot still shows SOLD_OUT in timeavail."""
    r = s.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
        'visitorNum': str(VISITORS), 'visitDate': date,
    }, headers=H, timeout=8)
    if r.status_code != 200:
        return f"timeavail {r.status_code}"
    for sl in r.json().get('timetable', []):
        if str(sl.get('id')) == slot_id:
            return sl.get('availability', '?')
        if sl.get('time') == slot_time:
            return f"{sl.get('availability')} (id changed to {sl.get('id')})"
    return "NOT FOUND"

def get_fresh_tid():
    r = s.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': date,
        'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers=H, timeout=8)
    if r.status_code == 200:
        t = next((v for v in r.json().get('visits', [])
                  if 'musei vaticani' in v.get('name', '').lower()
                  and 'ingresso' in v.get('name', '').lower()), None)
        if t:
            return t['id']
    return tid

start = time.time()
last_keepalive = time.time()
KEEPALIVE_INTERVAL = 240  # 4 minutes

try:
    while True:
        elapsed = int(time.time() - start)
        next_ka = int(KEEPALIVE_INTERVAL - (time.time() - last_keepalive))

        # Check status
        status = check_status()
        icon = "✅" if status == "SOLD_OUT" else "❌"
        print(f"\r  {icon} {date} {slot_time} → {status:<25} | held {elapsed}s | next keepalive in {next_ka}s   ", end='', flush=True)

        # Keepalive — reuse same session + same recap_id
        if time.time() - last_keepalive >= KEEPALIVE_INTERVAL:
            fresh_tid = get_fresh_tid()
            r_ka = s.post(f'{BASE}/api/visit/recap',
                          json=build_recap_body(slot_id, fresh_tid, recap_id),
                          headers=H, timeout=10)
            if r_ka.status_code == 200:
                d2 = r_ka.json()
                recap_id = d2.get('recapId') or d2.get('id') or recap_id  # update if changed
                last_keepalive = time.time()
                print(f"\n  💓 Keepalive OK (recap_id={recap_id})")
            else:
                print(f"\n  ⚠️  Keepalive failed {r_ka.status_code}: {r_ka.text[:200]}")

        time.sleep(10)

except KeyboardInterrupt:
    print(f"\n\nStopped. Slot will expire naturally in ~55 minutes.")
    print(f"Final status: {check_status()}")
