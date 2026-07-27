"""Extend the current hold by calling recap again with a fresh session."""
import requests

BASE = 'https://tickets.museivaticani.va'
H = {
    'Accept': 'application/json, text/plain, */*',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE}/',
    'Content-Type': 'application/json',
    'Origin': BASE,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}

DATE     = '14/05/2026'
SLOT_ID  = '2026*8243'
VISITORS = 1

s = requests.Session()
s.get(f'{BASE}/home', headers=H, timeout=8)

# Fresh ticket_id
r = s.get(f'{BASE}/api/search/resultPerTag', params={
    'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': DATE,
    'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
}, headers=H, timeout=8)
ticket = next((v for v in r.json().get('visits', [])
               if 'musei vaticani' in v.get('name', '').lower()
               and 'ingresso' in v.get('name', '').lower()), None)
tid = ticket['id'] if ticket else 1274675439
print(f"ticket_id={tid}")

body = {
    "visitId": SLOT_ID,
    "visitTypeId": int(tid),
    "visitorNum": VISITORS,
    "lang": "it",
    "tickets": [
        {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": "1"},
        {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": "0"},
    ],
    "additionalCosts": {
        "service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": 1}
    },
    "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": 1}]
}

r2 = s.post(f'{BASE}/api/visit/recap', json=body, headers=H, timeout=10)
print(f"Recap HTTP {r2.status_code}")
if r2.status_code == 200:
    d = r2.json()
    recap_id = d.get('recapId') or d.get('id')
    total = d.get('total')
    print(f"recap_id = {recap_id}")
    print(f"total    = EUR{total}")
    print(f"JSESSIONID = {s.cookies.get('JSESSIONID', '')[:30]}...")
    print("Hold extended for another ~55 minutes")
else:
    print(f"FAILED: {r2.text[:300]}")
