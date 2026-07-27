"""
Fire Vatican reservation for hold #6221 using provided Turnstile token.
"""
import sys, os, requests, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()

from monitors.models import HeldSlot

HOLD_ID = 6221
TURNSTILE_TOKEN = "1.rSkxs-2be50molPAdY9UwcqjzRdJbDqlumT8UkXaDFM8qJAIDJr3BPrhzeEzzWTv8xRKpI0IVhL7GdGWOqn4HIwJCSJaXrg_q4tgzL-mGtvu_C3roe4EZwYDOTNCvFXd8LSIJwlu9tHfewlemK2sKeCbpdVMkNWTIjzKuumdd6nedzXJRDTSN2ebTyKB4kp-yGMrlV7KEqJlO6fzB6lIiQdTjTGmc3ikG_24Pqc3jJqFacech-zQh90DjdMjfr0t8MhkOvqYr3ECKAN1dqv8JVG-xxp0nuuSawcxD3z9Ce4vC8wgwijRYnryrDH-pOz0snSfNXNj9JrcwcWABezsxOtOf1CY-tPX5KnPIL8YUk1C8WCv-hSwUmnqnhritPeqPSOLaHNG-KwNA1qWV_mFEUMQqPtFqvOfsZ-nFunjF9zZlWH6rVIrFA9qoVVR8UqK2uQkwmVx3uirV4o2PDr_gLMMOqVlzqLKEUDe_PRkt99KAZ0ai4krWIz5XX7X-4HzKnbOIeLJIra0WCpT6rCBxiaGFZZ6RR1oPg87gt0nfR0aPCnGN0YfN-8_hf-o1uY71eaBVIBS2N0w4FXGFMBOYqpVUvyzWy9N98w6qRJJ2amPhVJ-Wf1nj0YdXv-hsZE8t0X_sAK_noei1_wppNMaDp8b9K4ErOAeoiwkGPg6atM1yupdfrRTw_JBIL9WVspk.241x_kjAJHaGLqIzNHFJ1g.aff4ad24da0fdc4e55e2bd137390466704884ff10581217c72da8b61d2fdbb8c"

BASE = 'https://tickets.museivaticani.va'

held = HeldSlot.objects.get(id=HOLD_ID)
print(f"Hold #{held.id} | {held.date} {held.slot_time} | {held.visitors}v | recap={held.recap_id}")
print(f"JSESSIONID: {held.jsessionid}")
print(f"slot_id: {held.slot_id} | ticket_id: {held.ticket_id}")

# Build session with hold's cookies
s = requests.Session()
s.cookies.set('JSESSIONID', held.jsessionid, domain='tickets.museivaticani.va')
if held.ticketmv:
    s.cookies.set('ticketmv', held.ticketmv, domain='tickets.museivaticani.va')
try:
    notes = json.loads(held.notes or '{}')
    if isinstance(notes, dict) and notes.get('serverid'):
        s.cookies.set('SERVERID', notes['serverid'], domain='tickets.museivaticani.va')
except Exception:
    pass

HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': f'{BASE}/home/checkout',
    'Origin': BASE,
    'Content-Type': 'application/json',
}

# Build reservation body for 20 visitors
# Using your representative user details from the provided payload
body = {
    "recaptcha": TURNSTILE_TOKEN,
    "lang": "it",
    "recapId": held.recap_id,
    "visitorNum": int(held.visitors),
    "visitId": held.slot_id,
    "visitTypeId": int(held.ticket_id),
    "tickets": [
        {"id": 60, "name": "Biglietto Intero",  "price": 20, "quantity": str(held.visitors)},
        {"id": 61, "name": "Biglietto Ridotto",  "price": 10, "quantity": "0"},
    ],
    "services": [
        {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": int(held.visitors)}
    ],
    "representativeUser": {
        "surname": "sekar",
        "name": "abiilesh",
        "gender": "M",
        "country": "Albania",
        "city": "ROMA",
        "birthDate": "1997-09-21T22:00:00.000Z",
        "email": "your-email@example.com",
        "confirmEmail": "your-email@example.com",
        "telephoneNumber": "your-phone-number",
        "language": "en"
    },
    "participantUser": [
        {"surname": f"Guest{i+1}", "name": f"Visitor{i+1}",
         "id": 60, "ticketType": "intero", "services": [58]}
        for i in range(int(held.visitors))
    ],
    "gdpr": [{"id": 1, "check": True}, {"id": 3, "check": True}]
}

print(f"\nFiring reservation for {held.visitors} visitors...")
r = s.post(f'{BASE}/api/visit/reservation', json=body, headers=HEADERS, timeout=20)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:1000]}")

if r.status_code == 200:
    data = r.json()
    epay_url = data.get('epay', {}).get('url') or data.get('paymentUrl') or data.get('redirectUrl', '')
    reference = data.get('referenceOrder', '')
    total = data.get('total', '')
    print(f"\n✅ RESERVATION OK!")
    print(f"Reference: {reference}")
    print(f"Total: €{total}")
    print(f"Payment URL: {epay_url}")

    # Update hold status
    held.status = 'paying'
    held.payment_url = epay_url
    held.save(update_fields=['status', 'payment_url'])
    print(f"\nHold #{held.id} updated to 'paying'")
else:
    print(f"\n❌ FAILED: {r.text[:500]}")
