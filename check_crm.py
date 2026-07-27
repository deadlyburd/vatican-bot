import sys, os
os.environ["DJANGO_SETTINGS_MODULE"] = "core.settings"
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/backend")
import django
django.setup()

from crm_intelligence.parsers.sheet_parser import SheetParser
from datetime import date, datetime

SHEET_ID = "1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg"
CREDS_FILE = "/app/google_credentials.json"

print("=== CRM: JULY 28 BOOKINGS ===")
parser = SheetParser(sheet_id=SHEET_ID, credentials_file=CREDS_FILE)
parser.connect()

activities = parser.parse_activity_lines(limit=2000)
july28 = []
for a in activities:
    try:
        a_date = datetime.strptime(a.activity_date, "%Y-%m-%d").date()
    except:
        try:
            a_date = datetime.strptime(a.activity_date, "%d/%m/%Y").date()
        except:
            continue
    if a_date == date(2026, 7, 28):
        july28.append(a)

print(f"July 28 activities: {len(july28)}")
for a in july28[:10]:
    print(f"  {a.product_title[:50]} | {a.total_participants}pax | {a.customer_name} | {a.status}")

# Get buyer emails from bookings
bookings = parser.parse_bookings(limit=500)
print("\n=== CUSTOMER PROFILES (for buyer info) ===")
seen = set()
for b in bookings:
    if b.customer and b.customer.email and b.customer.email not in seen:
        seen.add(b.customer.email)
        if len(seen) <= 5:
            phone = b.customer.phone or "no phone"
            country = b.customer.country or "?"
            print(f"  {b.customer.full_name} | {b.customer.email} | {phone} | {country}")

print("\n=== GENERATED RANDOM BUYER PROFILE ===")
# Use first customer from CRM or fallback to random
if seen:
    first = None
    for b in bookings:
        if b.customer and b.customer.email:
            first = b.customer
            break
    if first:
        print(f"  Name: {first.full_name}")
        print(f"  Email: {first.email}")
        print(f"  Phone: {first.phone or '+39 333 1234567'}")
        print(f"  Country: {first.country or 'Italy'}")
else:
    print("  Name: Mario Rossi")
    print("  Email: mario.rossi@email.it")
    print("  Phone: +39 333 1234567")
    print("  Country: Italy")

# Check if there are Vatican bookings on July 28
print("\n=== VATICAN ON JULY 28 ===")
for a in july28:
    title = (a.product_title or "").lower()
    if any(w in title for w in ["vatican", "sistine", "vaticani", "musei"]):
        print(f"  ✅ {a.product_title[:60]} | {a.total_participants}pax | {a.customer_name}")
