#!/usr/bin/env python3
"""
Test script to read Google Sheet and create Vatican booking tasks
"""

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = 'google_credentials.json'
SHEET_ID = '1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg'

def get_sheet_data():
    """Fetch data from Google Sheet"""
    print("=" * 80)
    print("📊 Fetching Google Sheet Data")
    print("=" * 80)
    
    # Authenticate
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    
    # Open the sheet
    sheet = client.open_by_key(SHEET_ID)
    
    # Get all worksheets
    worksheets = sheet.worksheets()
    print(f"\n📋 Found {len(worksheets)} worksheets:")
    for ws in worksheets:
        print(f"   - {ws.title} ({ws.row_count} rows x {ws.col_count} cols)")
    
    # Get the first worksheet (or specify by name)
    worksheet = sheet.get_worksheet(0)  # First sheet
    
    # Get all values
    all_values = worksheet.get_all_values()
    
    if not all_values:
        print("\n❌ Sheet is empty!")
        return None
    
    # First row is headers
    headers = all_values[0]
    print(f"\n📋 Headers ({len(headers)} columns):")
    for i, header in enumerate(headers, 1):
        print(f"   {i}. {header}")
    
    # Get data rows
    data_rows = all_values[1:]
    print(f"\n📊 Data: {len(data_rows)} rows")
    
    # Parse into dictionaries
    bookings = []
    for row_idx, row in enumerate(data_rows, 2):  # Start from row 2 (after header)
        if not any(row):  # Skip empty rows
            continue
        
        booking = {}
        for i, header in enumerate(headers):
            value = row[i] if i < len(row) else ''
            booking[header] = value
        
        bookings.append(booking)
    
    print(f"\n✅ Parsed {len(bookings)} bookings")
    
    # Show first booking as example
    if bookings:
        print("\n📝 First Booking Example:")
        print(json.dumps(bookings[0], indent=2))
    
    return bookings

def analyze_booking_structure(bookings):
    """Analyze the booking structure"""
    print("\n" + "=" * 80)
    print("🔍 Analyzing Booking Structure")
    print("=" * 80)
    
    if not bookings:
        print("No bookings to analyze")
        return
    
    # Get all unique keys
    all_keys = set()
    for booking in bookings:
        all_keys.update(booking.keys())
    
    print(f"\n📋 All Fields ({len(all_keys)}):")
    for key in sorted(all_keys):
        # Get sample values
        sample_values = [b.get(key, '') for b in bookings[:3] if b.get(key)]
        sample = sample_values[0] if sample_values else '(empty)'
        print(f"   • {key}: {sample}")
    
    # Identify required fields for Vatican booking
    print("\n🎯 Required Fields for Vatican Booking:")
    required_fields = {
        'Date': 'Booking date (DD/MM/YYYY)',
        'Time': 'Booking time (HH:MM)',
        'Visitors': 'Number of visitors',
        'Ticket Type': 'Standard or Guided Tour',
        'Customer Name': 'Main contact name',
        'Customer Email': 'Main contact email',
        'Status': 'Booking status (Pending/Completed/Failed)'
    }
    
    for field, description in required_fields.items():
        found = field in all_keys
        status = "✅" if found else "❌"
        print(f"   {status} {field}: {description}")
    
    return bookings

def create_vatican_tasks(bookings):
    """Create Vatican monitoring tasks from bookings"""
    print("\n" + "=" * 80)
    print("🎫 Creating Vatican Monitoring Tasks")
    print("=" * 80)
    
    tasks = []
    
    for idx, booking in enumerate(bookings, 1):
        print(f"\n📋 Booking {idx}:")
        print(f"   Booking ID: {booking.get('Booking ID', 'N/A')}")
        print(f"   Date: {booking.get('Date', 'N/A')}")
        print(f"   Time: {booking.get('Time', 'N/A')}")
        print(f"   Visitors: {booking.get('Visitors', 'N/A')}")
        print(f"   Ticket Type: {booking.get('Ticket Type', 'N/A')}")
        print(f"   Status: {booking.get('Status', 'N/A')}")
        
        # Only create tasks for Pending bookings
        status = booking.get('Status', '').strip()
        if status.lower() != 'pending':
            print(f"   ⏭️  Skipping (Status: {status})")
            continue
        
        # Parse date
        date_str = booking.get('Date', '').strip()
        if not date_str:
            print(f"   ❌ Missing date")
            continue
        
        # Parse visitors
        try:
            visitors = int(booking.get('Visitors', '1'))
        except:
            visitors = 1
        
        # Determine ticket type
        ticket_type_str = booking.get('Ticket Type', '').lower()
        if 'guided' in ticket_type_str or 'tour' in ticket_type_str:
            ticket_type = 1  # Guided tour
            language = 'ENG'  # Default to English
        else:
            ticket_type = 0  # Standard ticket
            language = None
        
        task = {
            'booking_id': booking.get('Booking ID', f'MANUAL_{idx}'),
            'date': date_str,
            'time': booking.get('Time', '10:00'),
            'visitors': visitors,
            'ticket_type': ticket_type,
            'language': language,
            'customer': {
                'name': booking.get('Customer Name', ''),
                'email': booking.get('Customer Email', ''),
                'phone': booking.get('Customer Phone', '')
            },
            'status': 'pending'
        }
        
        tasks.append(task)
        print(f"   ✅ Task created")
    
    print(f"\n✅ Created {len(tasks)} tasks")
    return tasks

if __name__ == '__main__':
    try:
        # Fetch sheet data
        bookings = get_sheet_data()
        
        if bookings:
            # Analyze structure
            analyze_booking_structure(bookings)
            
            # Create tasks
            tasks = create_vatican_tasks(bookings)
            
            # Save tasks to file
            if tasks:
                with open('vatican_tasks.json', 'w') as f:
                    json.dump(tasks, f, indent=2)
                print(f"\n💾 Saved {len(tasks)} tasks to vatican_tasks.json")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
