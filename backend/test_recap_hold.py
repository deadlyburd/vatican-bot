"""
Test: does calling /api/visit/recap lock the slot for ~55 min?
1. Find available slot on April 15
2. Call recap
3. Immediately check availability from a DIFFERENT session
4. Report what the second session sees
"""
import os, sys, django, time, json
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.epay_ssl import make_vatican_session

BASE = 'https://tickets.museivaticani.va'
VISITORS = 2
DATE = '15/04/2026'

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

# ── Session A: find slot + call recap ────────────────────────────────────────
print(f"=== SESSION A: Finding slot on {DATE} ===")
sA = make_vatican_session()

r = sA.get(f'{BASE}/api/search/resultPerTag', params={
    'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': DATE,
    'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
}, headers=H_XHR, timeout=10)

if r.status_code != 200:
    print(f"Search failed: {r.status_code}"); sys.exit(1)

ticket = next((v for v in r.json().get('visits', [])
               if 'musei vaticani' in v.get('name','').lower()
               and 'ingresso' in v.get('name','').lower()), None)

if not ticket:
    print(f"No standard entry ticket found for {DATE}"); sys.exit(1)

tid = ticket['id']
avail = ticket.get('availability')
print(f"Ticket: {ticket['name']} | availability={avail} | id={tid}")

if avail not in ('AVAILABLE', 'LOW_AVAILABILITY'):
    print(f"Ticket is {avail} — nothing to test"); sys.exit(0)

# Get timeavail
r2 = sA.get(f'{BASE}/api/visit/timeavail', params={
    'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
    'visitorNum': str(VISITORS), 'visitDate': DATE,
}, headers=H_XHR, timeout=10)

timetable = r2.json().get('timetable', [])
available_slots = [sl for sl in timetable if sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')]
print(f"\nAvailable slots BEFORE recap ({len(available_slots)}):")
for sl in available_slots[:5]:
    print(f"  {sl['time']} → {sl['availability']} (id={sl['id']})")

if not available_slots:
    print("No available slots on April 15"); sys.exit(0)

target = available_slots[0]
slot_id = str(target['id'])
slot_time = target['time']
print(f"\nTarget slot: {slot_time} (id={slot_id})")

# ── Call recap from Session A ─────────────────────────────────────────────────
print(f"\n=== CALLING RECAP (Session A) ===")
recap_body = {
    "visitId": slot_id,
    "visitTypeId": int(tid),
    "visitorNum": int(VISITORS),
    "lang": "it",
    "tickets": [
        {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(VISITORS)},
        {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
    ],
    "additionalCosts": {
        "service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(VISITORS)}
    },
    "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(VISITORS)}]
}

t_recap = time.time()
rr = sA.post(f'{BASE}/api/visit/recap', json=recap_body, headers=HC, timeout=10)
elapsed = time.time() - t_recap

print(f"Recap HTTP {rr.status_code} ({elapsed:.2f}s)")
if rr.status_code == 200:
    rd = rr.json()
    print(f"recapId: {rd.get('recapId')}")
    print(f"total: €{rd.get('total')}")
    print(f"visitDateTime: {rd.get('visitDateTime')}")
    jsessionid_A = sA.cookies.get('JSESSIONID','')
    print(f"Session A JSESSIONID: {jsessionid_A[:20]}...")
else:
    print(f"Recap failed: {rr.text[:200]}"); sys.exit(1)

# ── Session B: check same slot immediately ────────────────────────────────────
print(f"\n=== SESSION B: Checking same slot immediately (fresh session) ===")
sB = make_vatican_session()

# Fresh search
rB = sB.get(f'{BASE}/api/search/resultPerTag', params={
    'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': DATE,
    'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
}, headers=H_XHR, timeout=10)

ticketB = next((v for v in rB.json().get('visits', [])
                if 'musei vaticani' in v.get('name','').lower()
                and 'ingresso' in v.get('name','').lower()), None)

if ticketB:
    tidB = ticketB['id']
    availB = ticketB.get('availability')
    print(f"Search API sees ticket as: {availB}")

# Fresh timeavail
rB2 = sB.get(f'{BASE}/api/visit/timeavail', params={
    'lang': 'it', 'visitLang': '', 'visitTypeId': str(tidB),
    'visitorNum': str(VISITORS), 'visitDate': DATE,
}, headers=H_XHR, timeout=10)

timetableB = rB2.json().get('timetable', [])
print(f"\nAll slots from Session B:")
for sl in timetableB:
    marker = " ← TARGET" if str(sl['id']) == slot_id else ""
    print(f"  {sl['time']} → {sl['availability']}{marker}")

target_in_B = next((sl for sl in timetableB if str(sl['id']) == slot_id), None)
if target_in_B:
    status_B = target_in_B.get('availability')
    print(f"\n{'='*50}")
    print(f"RESULT: Slot {slot_time} (id={slot_id})")
    print(f"  Before recap: {target['availability']}")
    print(f"  After recap (Session B sees): {status_B}")
    if status_B in ('SOLD_OUT', 'NOT_ALLOWED'):
        print(f"\n🔒 CONFIRMED: recap LOCKS the slot from other sessions!")
        print(f"   This is a server-side hold mechanism.")
    elif status_B == 'LOW_AVAILABILITY':
        print(f"\n⚠️  Slot shows LOW_AVAILABILITY — may be partially locked")
    else:
        print(f"\n❌ Slot still shows {status_B} — no lock detected from this check")
        print(f"   (Vatican may use a different mechanism or delay)")
else:
    print(f"\nSlot {slot_id} not found in Session B timetable!")

# ── Try recap from Session B on same slot ────────────────────────────────────
print(f"\n=== SESSION B: Trying to recap the SAME slot ===")
rr2 = sB.post(f'{BASE}/api/visit/recap', json=recap_body, headers=HC, timeout=10)
print(f"Session B recap HTTP {rr2.status_code}")
if rr2.status_code == 200:
    rd2 = rr2.json()
    print(f"Session B recapId: {rd2.get('recapId')}")
    print(f"Session B total: €{rd2.get('total')}")
    print(f"\n⚠️  Both sessions got a recap — Vatican allows concurrent recaps!")
    print(f"   First to complete reservation wins.")
else:
    print(f"Session B recap FAILED: {rr2.status_code} {rr2.text[:200]}")
    print(f"\n🔒 CONFIRMED: recap from Session A blocks Session B from recapping!")
