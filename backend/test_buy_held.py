"""
Test: can we complete a reservation using a recapId from a dead session?
The slot 11/04/2026 14:30 was locked hours ago with recapId=2026/7701/134.
The original session is gone. Can we still buy it?

Two approaches:
A) Use the old recapId directly with a fresh session + new token
B) Re-recap with a fresh session to get a new recapId, then reserve

Also tests: does the slot need to be AVAILABLE for reservation, or can we
reserve a SOLD_OUT slot if we have the recapId?
"""
import os, sys, django, time, json
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.epay_ssl import make_vatican_session
from monitors.models import BuyerProfile, Agency

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
SLOT_ID = '2026*7701'
SLOT_TIME = '14:30'
OLD_RECAP_ID = '2026/7701/134'
VISITORS = 1

agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
profile = BuyerProfile.objects.filter(agency=agency).first()
print(f"Profile: {profile.first_name} {profile.last_name}")

# ── Check current slot status ─────────────────────────────────────────────────
print(f"\nChecking current status of {DATE} {SLOT_TIME}...")
s_check = make_vatican_session()
r = s_check.get(f'{BASE}/api/search/resultPerTag', params={
    'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': DATE,
    'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
}, headers=H_XHR, timeout=10)
ticket = next((v for v in r.json().get('visits', [])
               if 'musei vaticani' in v.get('name','').lower()
               and 'ingresso' in v.get('name','').lower()), None)
tid = ticket['id'] if ticket else None
print(f"Ticket availability: {ticket.get('availability') if ticket else 'NOT FOUND'}")
print(f"tid: {tid}")

if tid:
    r2 = s_check.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
        'visitorNum': str(VISITORS), 'visitDate': DATE,
    }, headers=H_XHR, timeout=10)
    slot_status = next((sl.get('availability') for sl in r2.json().get('timetable', [])
                        if str(sl.get('id')) == SLOT_ID), 'NOT_FOUND')
    print(f"Slot {SLOT_TIME} status: {slot_status}")

# ── Approach A: Use old recapId with fresh session ────────────────────────────
print(f"\n{'='*55}")
print(f"APPROACH A: Old recapId ({OLD_RECAP_ID}) + fresh session")
print(f"(No Turnstile — just test if Vatican accepts the recapId)")
print(f"{'='*55}")

# We need a token to test reservation — check if 2captcha has balance
import requests as req
api_key = os.getenv('TWOCAPTCHA_API_KEY', '')
bal_r = req.get('https://2captcha.com/res.php', params={'key': api_key, 'action': 'getbalance', 'json': 1}, timeout=5)
balance = bal_r.json().get('request', '0')
print(f"2captcha balance: {balance}")

has_balance = float(balance) > 0.01 if balance.replace('.','').replace('-','').isdigit() else False

if has_balance:
    print("Solving Turnstile token...")
    from monitors.turnstile_pool import _solve_one_token
    token = _solve_one_token(api_key)
    if token:
        print(f"Token: prefix={token[:4]} len={len(token)}")
        
        # Try reservation with old recapId + fresh session
        s_fresh = make_vatican_session()
        # Establish session via search
        s_fresh.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': DATE,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=H_XHR, timeout=10)
        
        res_body = {
            "recaptcha": token, "lang": "it",
            "recapId": OLD_RECAP_ID,
            "visitorNum": VISITORS,
            "visitId": SLOT_ID,
            "visitTypeId": int(tid) if tid else 0,
            "tickets": [
                {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(VISITORS)},
                {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
            ],
            "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": VISITORS}],
            "representativeUser": profile.to_representative_user(),
            "participantUser": [
                {"surname": " ", "name": " ", "id": 60, "ticketType": "intero", "services": [58]}
            ],
            "gdpr": [{"id": 1, "check": True}, {"id": 3, "check": True}],
        }
        
        print(f"\nPosting reservation with old recapId...")
        r_res = s_fresh.post(f'{BASE}/api/visit/reservation', json=res_body, headers=HC, timeout=20)
        print(f"HTTP {r_res.status_code}")
        try:
            rd = r_res.json()
            print(f"Response: {json.dumps(rd, indent=2)[:500]}")
            if r_res.status_code == 200:
                print(f"\n✅ APPROACH A WORKS — old recapId is still valid!")
                epay = rd.get('epay', {})
                print(f"epay URL: {epay.get('url')}")
                print(f"reference: {rd.get('referenceOrder')}")
        except:
            print(f"Response text: {r_res.text[:300]}")
    else:
        print("Token solve failed")
else:
    print(f"No 2captcha balance ({balance}) — skipping reservation test")
    print(f"\nManual test: the recapId {OLD_RECAP_ID} may still be valid.")
    print(f"To test: top up 2captcha and run this script again.")

# ── Approach B: Re-recap with fresh session ───────────────────────────────────
print(f"\n{'='*55}")
print(f"APPROACH B: Re-recap with fresh session to get new recapId")
print(f"(Only works if slot is AVAILABLE — currently {slot_status if tid else 'unknown'})")
print(f"{'='*55}")

if tid and slot_status in ('AVAILABLE', 'LOW_AVAILABILITY'):
    s_b = make_vatican_session()
    s_b.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': DATE,
        'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers=H_XHR, timeout=10)
    
    body = {
        "visitId": SLOT_ID, "visitTypeId": int(tid), "visitorNum": VISITORS, "lang": "it",
        "tickets": [
            {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(VISITORS)},
            {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": 0},
        ],
        "additionalCosts": {"service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": VISITORS}},
        "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": VISITORS}],
    }
    rr = s_b.post(f'{BASE}/api/visit/recap', json=body, headers=HC, timeout=10)
    print(f"Re-recap HTTP {rr.status_code}")
    if rr.status_code == 200:
        new_recap_id = rr.json().get('recapId','')
        print(f"New recapId: {new_recap_id}")
        print(f"✅ Got fresh recapId — can now complete reservation with token")
    else:
        try: print(f"Failed: {rr.json().get('message', rr.text[:100])}")
        except: print(f"Failed: {rr.text[:100]}")
else:
    print(f"Slot is {slot_status if tid else 'unknown'} — re-recap not possible right now")
    print(f"(Slot is still locked from original hold)")

print(f"\n{'='*55}")
print(f"SUMMARY:")
print(f"  Slot {DATE} {SLOT_TIME}: {slot_status if tid else 'unknown'}")
print(f"  Old recapId: {OLD_RECAP_ID}")
print(f"  To buy: need Turnstile token + reservation API call")
print(f"  To release: just wait — Vatican releases automatically")
print(f"{'='*55}")
