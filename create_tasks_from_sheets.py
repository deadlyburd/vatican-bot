#!/usr/bin/env python3
"""
Create Vatican monitoring tasks from Google Sheets
Reads Activity_Lines and creates tasks in database
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import VaticanTask
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

print("🚀 Creating Vatican Tasks from Google Sheets")
print("=" * 80)

# Configuration
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE', '/app/google_credentials.json')
SHEET_ID = os.getenv('GOOGLE_SHEET_ID', '1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg')

# Connect to Google Sheets
print("\n1️⃣ Connecting to Google Sheets...")
try:
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID)
    print(f"   ✅ Connected to: {sheet.title}")
except Exception as e:
    print(f"   ❌ Connection failed: {e}")
    sys.exit(1)

# Get worksheets
print("\n2️⃣ Reading worksheets...")
try:
    activity_ws = sheet.worksheet('Activity_Lines')
    bookings_ws = sheet.worksheet('Bookings')
    print(f"   ✅ Activity_Lines: {activity_ws.row_count} rows")
    print(f"   ✅ Bookings: {bookings_ws.row_count} rows")
except Exception as e:
    print(f"   ❌ Could not read worksheets: {e}")
    sys.exit(1)

# Get data
activity_headers = activity_ws.row_values(1)
activity_rows = activity_ws.get_all_values()[1:]

bookings_headers = bookings_ws.row_values(1)
bookings_rows = bookings_ws.get_all_values()[1:]

# Create booking lookup
print("\n3️⃣ Creating booking lookup...")
bookings_dict = {}
for row in bookings_rows:
    booking = dict(zip(bookings_headers, row))
    conf_code = booking.get('confirmationCode', '').strip()
    if conf_code:
        bookings_dict[conf_code] = booking
print(f"   ✅ Indexed {len(bookings_dict)} bookings")

# Find future Vatican bookings
print("\n4️⃣ Finding future Vatican bookings...")
today = datetime.now()
future_activities = []

for row in activity_rows:
    activity = dict(zip(activity_headers, row))
    
    # Check status
    status = activity.get('status', '').strip().upper()
    if status != 'CONFIRMED':
        continue
    
    # Check date
    date_str = activity.get('activityDate', '').strip()
    if not date_str:
        continue
    
    try:
        # Parse date (YYYY-MM-DD format)
        activity_date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Only future dates
        if activity_date <= today:
            continue
        
        # Check if it's a Vatican ticket
        product_title = activity.get('productTitle', '').lower()
        if 'vatican' not in product_title and 'musei vaticani' not in product_title:
            continue
        
        # Get customer info from Bookings
        conf_code = activity.get('confirmationCode', '').strip()
        booking = bookings_dict.get(conf_code, {})
        
        # Determine ticket type
        # 0 = Standard ticket (hosted entry, skip-the-line)
        # 1 = Guided tour (has "guided" in title)
        ticket_type = 1 if 'guided' in product_title or 'guidata' in product_title else 0
        
        # Get language for guided tours
        language = None
        if ticket_type == 1:
            guided_langs = activity.get('guidedLanguages', '').strip().upper()
            if guided_langs:
                # Map to Vatican API language codes
                lang_map = {
                    'ENGLISH': 'ENG',
                    'ITALIAN': 'ITA',
                    'FRENCH': 'FRA',
                    'GERMAN': 'DEU',
                    'SPANISH': 'SPA'
                }
                for key, val in lang_map.items():
                    if key in guided_langs:
                        language = val
                        break
        
        future_activities.append({
            'booking_id': conf_code,
            'date': activity_date,
            'date_str': activity_date.strftime('%d/%m/%Y'),
            'time': activity.get('startTime', '10:00'),
            'visitors': int(activity.get('totalParticipants', 1) or 1),
            'ticket_type': ticket_type,
            'language': language,
            'product': activity.get('productTitle', 'Unknown'),
            'customer_name': activity.get('customerName', booking.get('customerFirstName', '') + ' ' + booking.get('customerLastName', '')),
            'customer_email': booking.get('customerEmail', ''),
            'customer_phone': booking.get('customerPhone', '')
        })
        
    except Exception as e:
        continue

print(f"   ✅ Found {len(future_activities)} future Vatican bookings")

if not future_activities:
    print("\n⚠️  No future Vatican bookings found!")
    print("   Add bookings to Google Sheet with:")
    print("   - status: CONFIRMED")
    print("   - activityDate: future date (YYYY-MM-DD)")
    print("   - productTitle: contains 'vatican' or 'musei vaticani'")
    sys.exit(0)

# Create tasks in database
print("\n5️⃣ Creating tasks in database...")
created = 0
updated = 0
skipped = 0

for activity in future_activities:
    try:
        # Check if task already exists
        task, created_new = VaticanTask.objects.get_or_create(
            booking_id=activity['booking_id'],
            defaults={
                'target_date': activity['date'],
                'target_time': activity['time'],
                'visitors': activity['visitors'],
                'ticket_type': activity['ticket_type'],
                'language': activity['language'],
                'customer_name': activity['customer_name'],
                'customer_email': activity['customer_email'],
                'customer_phone': activity['customer_phone'],
                'status': 'new',
                'priority': 1
            }
        )
        
        if created_new:
            created += 1
            print(f"   ✅ Created: {activity['booking_id']} - {activity['date_str']} - {activity['product'][:50]}")
        else:
            # Update existing task
            task.target_date = activity['date']
            task.target_time = activity['time']
            task.visitors = activity['visitors']
            task.ticket_type = activity['ticket_type']
            task.language = activity['language']
            task.customer_name = activity['customer_name']
            task.customer_email = activity['customer_email']
            task.customer_phone = activity['customer_phone']
            
            # Only update if status is new, pending, or monitoring
            if task.status in ['new', 'pending', 'monitoring', 'checking', 'awaiting_info']:
                task.save()
                updated += 1
                print(f"   🔄 Updated: {activity['booking_id']} - {activity['date_str']}")
            else:
                skipped += 1
                print(f"   ⏭️  Skipped: {activity['booking_id']} - Status: {task.status}")
    
    except Exception as e:
        print(f"   ❌ Error creating task {activity['booking_id']}: {e}")

# Summary
print("\n" + "=" * 80)
print("✅ TASK CREATION COMPLETE!")
print("=" * 80)
print(f"\n📊 Summary:")
print(f"   • Total bookings found: {len(future_activities)}")
print(f"   • Tasks created: {created}")
print(f"   • Tasks updated: {updated}")
print(f"   • Tasks skipped: {skipped}")

# Show task breakdown
print(f"\n📋 Task Breakdown:")
standard_count = sum(1 for a in future_activities if a['ticket_type'] == 0)
guided_count = sum(1 for a in future_activities if a['ticket_type'] == 1)
print(f"   • Standard tickets: {standard_count}")
print(f"   • Guided tours: {guided_count}")

# Show date range
dates = sorted([a['date'] for a in future_activities])
print(f"\n📅 Date Range:")
print(f"   • First booking: {dates[0].strftime('%d/%m/%Y')}")
print(f"   • Last booking: {dates[-1].strftime('%d/%m/%Y')}")

# Show visitor stats
total_visitors = sum(a['visitors'] for a in future_activities)
avg_visitors = total_visitors / len(future_activities)
print(f"\n👥 Visitor Stats:")
print(f"   • Total visitors: {total_visitors}")
print(f"   • Average per booking: {avg_visitors:.1f}")

print("\n🚀 Next Steps:")
print("   1. Start monitoring: docker-compose -f docker-compose.server.yml up -d")
print("   2. Check logs: docker-compose -f docker-compose.server.yml logs -f worker_vatican")
print("   3. Monitor Telegram for notifications")

print("\n" + "=" * 80)
