#!/usr/bin/env python3
"""
Simple test script - No Docker required
Tests Google Sheets connection and shows booking data
"""

print("🧪 Simple Vatican Bot Test (No Docker)")
print("=" * 80)

# Test imports
print("\n1️⃣ Testing imports...")
try:
    import gspread
    print("   ✅ gspread")
except ImportError:
    print("   ❌ gspread not installed")
    print("   Run: pip install gspread google-auth")
    exit(1)

try:
    from google.oauth2.service_account import Credentials
    print("   ✅ google-auth")
except ImportError:
    print("   ❌ google-auth not installed")
    print("   Run: pip install google-auth")
    exit(1)

import json
from datetime import datetime

# Test Google Sheets
print("\n2️⃣ Testing Google Sheets connection...")

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = 'google_credentials.json'
SHEET_ID = '1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg'

try:
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    print("   ✅ Authenticated with Google")
except Exception as e:
    print(f"   ❌ Authentication failed: {e}")
    exit(1)

try:
    sheet = client.open_by_key(SHEET_ID)
    print(f"   ✅ Opened sheet: {sheet.title}")
except Exception as e:
    print(f"   ❌ Could not open sheet: {e}")
    exit(1)

# List worksheets
print("\n3️⃣ Worksheets:")
worksheets = sheet.worksheets()
for i, ws in enumerate(worksheets, 1):
    print(f"   {i}. {ws.title} ({ws.row_count} rows × {ws.col_count} cols)")

# Get Bookings worksheet
print("\n4️⃣ Reading 'Bookings' worksheet...")
try:
    worksheet = sheet.worksheet('Bookings')
except:
    print("   ⚠️  'Bookings' not found, using first worksheet")
    worksheet = sheet.get_worksheet(0)

print(f"   ✅ Using: {worksheet.title}")

# Get headers
headers = worksheet.row_values(1)
print(f"\n5️⃣ Headers ({len(headers)} columns):")
for i, h in enumerate(headers[:15], 1):
    print(f"   {i:2d}. {h}")
if len(headers) > 15:
    print(f"   ... and {len(headers) - 15} more")

# Get sample data
print("\n6️⃣ Sample Bookings (first 5 CONFIRMED):")
all_rows = worksheet.get_all_values()[1:]  # Skip header

confirmed_count = 0
for row in all_rows:
    if confirmed_count >= 5:
        break
    
    booking = dict(zip(headers, row))
    status = booking.get('status', '').strip().upper()
    
    if status == 'CONFIRMED':
        confirmed_count += 1
        print(f"\n   📋 Booking #{confirmed_count}:")
        print(f"      ID: {booking.get('confirmationCode', 'N/A')}")
        print(f"      Date: {booking.get('activityDate', 'N/A')}")
        print(f"      Time: {booking.get('startTime', 'N/A')}")
        print(f"      Product: {booking.get('productTitle', 'N/A')[:50]}")
        print(f"      Visitors: {booking.get('totalParticipants', 'N/A')}")
        print(f"      Customer: {booking.get('customerFirstName', '')} {booking.get('customerLastName', '')}")
        print(f"      Email: {booking.get('customerEmail', 'N/A')}")
        print(f"      Status: {status}")

if confirmed_count == 0:
    print("   ⚠️  No CONFIRMED bookings found")

# Create a test task
print("\n7️⃣ Creating test Vatican booking task...")

# Find a future CONFIRMED booking
test_task = None
for row in all_rows:
    booking = dict(zip(headers, row))
    status = booking.get('status', '').strip().upper()
    date_str = booking.get('activityDate', '').strip()
    
    if status == 'CONFIRMED' and date_str:
        try:
            if '-' in date_str:
                booking_date = datetime.strptime(date_str, '%Y-%m-%d')
            else:
                booking_date = datetime.strptime(date_str, '%d/%m/%Y')
            
            if booking_date > datetime.now():
                test_task = {
                    'booking_id': booking.get('confirmationCode', 'TEST'),
                    'date': booking_date.strftime('%d/%m/%Y'),
                    'time': booking.get('startTime', '10:00'),
                    'visitors': int(booking.get('totalParticipants', 1) or 1),
                    'ticket_type': 0,  # Standard
                    'language': None,
                    'customer': {
                        'first_name': booking.get('customerFirstName', ''),
                        'last_name': booking.get('customerLastName', ''),
                        'email': booking.get('customerEmail', ''),
                        'phone': booking.get('customerPhone', '')
                    }
                }
                break
        except:
            continue

if test_task:
    print("   ✅ Created task from sheet:")
    print(json.dumps(test_task, indent=6))
    
    # Save to file
    with open('test_task.json', 'w') as f:
        json.dump(test_task, f, indent=2)
    print("\n   💾 Saved to test_task.json")
else:
    print("   ⚠️  No future CONFIRMED bookings found")
    print("   💡 Add a test booking with:")
    print("      - status: CONFIRMED")
    print("      - activityDate: future date (YYYY-MM-DD)")
    print("      - totalParticipants: 1")

# Summary
print("\n" + "=" * 80)
print("✅ TEST COMPLETE!")
print("=" * 80)
print("\n📊 Summary:")
print(f"   • Google Sheets: Connected ✅")
print(f"   • Worksheet: {worksheet.title}")
print(f"   • Total rows: {len(all_rows)}")
print(f"   • CONFIRMED bookings: {confirmed_count}")
if test_task:
    print(f"   • Test task created: {test_task['booking_id']}")

print("\n🚀 Next Steps:")
print("   1. Verify the booking data looks correct")
print("   2. Run the full test on server:")
print("      ssh -i hetzner_key root@178.105.157.86")
print("      cd /root/vatican-bot")
print("      docker-compose -f docker-compose.server.yml exec backend python /app/test_complete_booking.py")
print("\n" + "=" * 80)
