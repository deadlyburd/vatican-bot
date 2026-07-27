"""
Test reservation for May 2 holds using 2captcha auto-solve.
"""
import os, sys, django, requests, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import HeldSlot, BuyerProfile

BASE = 'https://tickets.museivaticani.va'

# Test hold #512 (May 2, 09:00, 1 visitor)
hold = HeldSlot.objects.get(id=512)
profile = BuyerProfile.objects.filter(agency=hold.task.agency).first()

print(f"Hold #{hold.id} | {hold.date} {hold.slot_time} | v={hold.visitors}")
print(f"recapId: {hold.recap_id}")
print(f"slot_id: {hold.slot_id}")
print(f"ticket_id: {hold.ticket_id}")
print(f"Profile: {profile.first_name} {profile.last_name}" if profile else "No profile")

# Step 1: Try re-doing recap to get fresh recapId
print("\n--- Re-doing recap to get fresh recapId ---")
s = requests.Session()
s.cookies.set('JSESSIONID', hold.jsessionid, domain='tickets.museivaticani.va')
if hold.ticketmv:
    s.cookies.set('ticketmv', hold.ticketmv, domain='tickets.museivaticani.va')

body = {
    "visitId": str(hold.slot_id),
    "visitTypeId": int(hold.ticket_id),
    "visitorNum": hold.visitors,
    "lang": "it",
    "tickets": [{"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": hold.visitors}],
    "additionalCosts": {},
    "services": [],
}
headers = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': f'{BASE}/',
    'Origin': BASE,
    'Content-Type': 'application/json',
}

r = s.post(f'{BASE}/api/visit/recap', json=body, headers=headers, timeout=15)
print(f"Recap status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    new_recap_id = data.get('recapId', '')
    print(f"New recapId: {new_recap_id}")
    # Update in DB
    hold.recap_id = new_recap_id
    hold.save(update_fields=['recap_id'])
    print(f"✅ recapId updated in DB")
else:
    print(f"❌ Recap failed: {r.text[:200]}")
    sys.exit(1)

# Step 2: Solve Turnstile
print("\n--- Solving Turnstile via 2captcha ---")
api_key = os.getenv('TWOCAPTCHA_API_KEY')
if not api_key:
    print("❌ No TWOCAPTCHA_API_KEY")
    sys.exit(1)

r2 = requests.post('https://2captcha.com/in.php', data={
    'key': api_key,
    'method': 'turnstile',
    'sitekey': '0x4AAAAAAB2Edz1zEK7o5Rj1',
    'pageurl': f'{BASE}/home/checkout',
    'json': 1,
}, timeout=10)
data2 = r2.json()
if data2.get('status') != 1:
    print(f"❌ 2captcha submit failed: {data2}")
    sys.exit(1)

task_id = data2['request']
print(f"Task submitted: {task_id}. Waiting...")

token = None
for _ in range(24):
    time.sleep(5)
    r3 = requests.get('https://2captcha.com/res.php', params={
        'key': api_key, 'action': 'get', 'id': task_id, 'json': 1
    }, timeout=10)
    res = r3.json()
    if res.get('status') == 1:
        token = res['request']
        print(f"✅ Turnstile solved: {token[:40]}...")
        break
    if res.get('request') != 'CAPCHA_NOT_READY':
        print(f"❌ 2captcha error: {res}")
        sys.exit(1)

if not token:
    print("❌ Timeout")
    sys.exit(1)

# Step 3: Fire reservation
print("\n--- Firing reservation ---")
res_body = {
    "recaptcha": token,
    "lang": "it",
    "recapId": hold.recap_id,
    "visitorNum": hold.visitors,
    "visitId": hold.slot_id,
    "visitTypeId": int(hold.ticket_id),
    "tickets": [{"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": hold.visitors}],
    "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": hold.visitors}],
    "representativeUser": profile.to_representative_user() if profile else {
        "surname": "sekar", "name": "abiilesh", "gender": "M",
        "country": "Italia", "city": "ROMA",
        "birthDate": "2001-06-11T22:00:00.000Z",
        "email": "your-email@example.com",
        "confirmEmail": "your-email@example.com",
        "telephoneNumber": "your-phone-number", "language": "en"
    },
    "participantUser": profile.to_participant_list(hold.visitors) if profile else [
        {"surname": "sekar", "name": "abiilesh", "id": 60, "ticketType": "intero", "services": [58]}
    ],
    "gdpr": [{"id": 1, "check": True}, {"id": 3, "check": True}],
}

res_headers = {**headers, 'Referer': f'{BASE}/home/checkout'}
r4 = s.post(f'{BASE}/api/visit/reservation', json=res_body, headers=res_headers, timeout=20)
print(f"Status: {r4.status_code}")
print(f"Response: {r4.text[:600]}")

if r4.status_code == 200:
    data4 = r4.json()
    epay_url = data4.get('epay', {}).get('url', '')
    ref = data4.get('referenceOrder', '')
    print(f"\n✅ RESERVATION CONFIRMED!")
    print(f"  Reference: {ref}")
    print(f"  Payment URL: {epay_url}")
    hold.status = 'paying'
    hold.payment_url = epay_url
    hold.save(update_fields=['status', 'payment_url'])
