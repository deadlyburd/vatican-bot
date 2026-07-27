#!/usr/bin/env python3
"""
Setup Google Sheets Structure for Bokun Integration
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError as e:
    print(f"❌ Missing package: {e}")
    sys.exit(1)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

SHEET_ID = '1MLEb4tKzCF3KWsgUiHGyqn-GaMgPIN0scEAWxFQvJT0'
SERVICE_ACCOUNT_FILE = 'google_credentials.json'

def setup_worksheets():
    """Setup the required worksheets for Bokun integration"""
    
    print("=" * 60)
    print("📊 Setting Up Google Sheets Structure")
    print("=" * 60)
    
    # Initialize credentials
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )
    
    # Authorize client
    client = gspread.authorize(creds)
    
    # Open sheet
    sheet = client.open_by_key(SHEET_ID)
    print(f"✅ Connected to: {sheet.title}")
    
    # Worksheet 1: Bookings_Input (where Bokun writes)
    print("\n📝 Setting up 'Bookings_Input' worksheet...")
    try:
        ws_input = sheet.worksheet('Bookings_Input')
        print("   ℹ️ Worksheet already exists")
    except:
        ws_input = sheet.add_worksheet(title='Bookings_Input', rows=1000, cols=15)
        print("   ✅ Created worksheet")
    
    # Set headers
    headers_input = [
        'Booking ID', 'Date', 'Time', 'Visitors', 'Ticket Type',
        'First Name', 'Last Name', 'Email', 'Phone',
        'Status', 'Created At', 'Notes'
    ]
    ws_input.update('A1:L1', [headers_input])
    
    # Format header row
    ws_input.format('A1:L1', {
        'backgroundColor': {'red': 0.2, 'green': 0.5, 'blue': 0.8},
        'textFormat': {'bold': True, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}},
        'horizontalAlignment': 'CENTER'
    })
    
    print("   ✅ Headers configured")
    
    # Worksheet 2: Bookings_Output (where bot updates)
    print("\n📝 Setting up 'Bookings_Output' worksheet...")
    try:
        ws_output = sheet.worksheet('Bookings_Output')
        print("   ℹ️ Worksheet already exists")
    except:
        ws_output = sheet.add_worksheet(title='Bookings_Output', rows=1000, cols=10)
        print("   ✅ Created worksheet")
    
    # Set headers
    headers_output = [
        'Booking ID', 'Date', 'Time', 'Status', 'Payment Link',
        'Booked At', 'Marked', 'Notes'
    ]
    ws_output.update('A1:H1', [headers_output])
    
    # Format header row
    ws_output.format('A1:H1', {
        'backgroundColor': {'red': 0.2, 'green': 0.5, 'blue': 0.8},
        'textFormat': {'bold': True, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}},
        'horizontalAlignment': 'CENTER'
    })
    
    print("   ✅ Headers configured")
    
    # Worksheet 3: Participants (for multi-visitor bookings)
    print("\n📝 Setting up 'Participants' worksheet...")
    try:
        ws_participants = sheet.worksheet('Participants')
        print("   ℹ️ Worksheet already exists")
    except:
        ws_participants = sheet.add_worksheet(title='Participants', rows=1000, cols=10)
        print("   ✅ Created worksheet")
    
    # Set headers
    headers_participants = [
        'Booking ID', 'Participant #', 'First Name', 'Last Name',
        'Birth Date', 'Gender', 'Email', 'Phone', 'Notes'
    ]
    ws_participants.update('A1:I1', [headers_participants])
    
    # Format header row
    ws_participants.format('A1:I1', {
        'backgroundColor': {'red': 0.2, 'green': 0.5, 'blue': 0.8},
        'textFormat': {'bold': True, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}},
        'horizontalAlignment': 'CENTER'
    })
    
    print("   ✅ Headers configured")
    
    # Add example data to Bookings_Input
    print("\n📝 Adding example booking...")
    example_row = [
        'BK_EXAMPLE_001',
        '15/06/2026',
        '10:00',
        '2',
        'Vatican Museums - Standard Entry',
        'John',
        'Doe',
        'john@example.com',
        '+393331234567',
        'Pending',
        '2026-05-26T10:30:00Z',
        'Example booking for testing'
    ]
    
    # Check if example already exists
    try:
        cell = ws_input.find('BK_EXAMPLE_001')
        print("   ℹ️ Example booking already exists")
    except:
        ws_input.append_row(example_row)
        print("   ✅ Added example booking")
    
    print("\n" + "=" * 60)
    print("✅ SETUP COMPLETE!")
    print("=" * 60)
    print("\n📊 Your Google Sheets structure is ready:")
    print("   1. Bookings_Input - Where Bokun bookings are written")
    print("   2. Bookings_Output - Where bot updates booking status")
    print("   3. Participants - Where participant details are stored")
    print(f"\n🔗 View your sheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}")
    print("\n✅ Next step: Deploy the bot to Hetzner!")

if __name__ == '__main__':
    try:
        setup_worksheets()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
