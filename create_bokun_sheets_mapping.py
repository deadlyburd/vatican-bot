#!/usr/bin/env python3
"""
Create Bokun → Google Sheets Mapping and Sample Data

This script:
1. Shows the expected Bokun API response format
2. Creates proper column mapping
3. Adds sample data to Google Sheets for testing
"""

import sys
import os
from datetime import datetime

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

# Bokun API Response Format (based on Bokun documentation)
BOKUN_SAMPLE_RESPONSE = {
    "confirmationCode": "BK-2026-001234",
    "id": "12345678",
    "status": "CONFIRMED",
    "createdDate": "2026-05-26T10:30:00Z",
    "startTime": "2026-06-15T10:00:00Z",
    "product": {
        "id": "987654",
        "title": "Vatican Museums and Sistine Chapel - Skip the Line",
        "type": "ACTIVITY"
    },
    "numberOfParticipants": 2,
    "customer": {
        "firstName": "John",
        "lastName": "Doe",
        "email": "john.doe@example.com",
        "phoneNumber": "+39 333 123 4567",
        "nationality": "US"
    },
    "participants": [
        {
            "firstName": "John",
            "lastName": "Doe",
            "dateOfBirth": "1990-01-01",
            "gender": "MALE",
            "email": "john.doe@example.com",
            "phoneNumber": "+39 333 123 4567"
        },
        {
            "firstName": "Jane",
            "lastName": "Doe",
            "dateOfBirth": "1992-05-15",
            "gender": "FEMALE",
            "email": "jane.doe@example.com",
            "phoneNumber": "+39 333 123 4568"
        }
    ],
    "price": {
        "totalPrice": 68.00,
        "currency": "EUR"
    },
    "extras": [],
    "notes": "Please arrive 15 minutes early"
}

def parse_bokun_to_sheets_format(bokun_booking):
    """
    Parse Bokun booking to Google Sheets format
    
    Bokun API fields → Google Sheets columns mapping:
    
    confirmationCode → Booking ID
    startTime → Date + Time
    numberOfParticipants → Visitors
    product.title → Ticket Type
    customer.firstName → First Name
    customer.lastName → Last Name
    customer.email → Email
    customer.phoneNumber → Phone
    status → Status (converted to "Pending" for bot)
    createdDate → Created At
    notes → Notes
    """
    
    # Extract booking ID
    booking_id = bokun_booking.get('confirmationCode', '') or str(bokun_booking.get('id', ''))
    
    # Extract and format date/time
    start_time = bokun_booking.get('startTime', '')
    if start_time:
        try:
            dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            date_formatted = dt.strftime('%d/%m/%Y')
            time_formatted = dt.strftime('%H:%M')
        except:
            date_formatted = start_time.split('T')[0] if 'T' in start_time else start_time
            time_formatted = '10:00'
    else:
        date_formatted = ''
        time_formatted = '10:00'
    
    # Extract visitors count
    visitors = bokun_booking.get('numberOfParticipants', 1)
    
    # Extract product/ticket type
    product = bokun_booking.get('product', {})
    ticket_type = product.get('title', 'Vatican Museums - Standard Entry')
    
    # Extract customer info
    customer = bokun_booking.get('customer', {})
    first_name = customer.get('firstName', '')
    last_name = customer.get('lastName', '')
    email = customer.get('email', '')
    phone = customer.get('phoneNumber', '')
    
    # Extract status and notes
    status = 'Pending'  # Always start as Pending for bot processing
    created_at = bokun_booking.get('createdDate', datetime.now().isoformat())
    notes = bokun_booking.get('notes', '')
    
    # Add price info to notes if available
    if 'price' in bokun_booking:
        price_info = bokun_booking['price']
        total = price_info.get('totalPrice', 0)
        currency = price_info.get('currency', 'EUR')
        notes = f"Price: {total} {currency}. {notes}".strip()
    
    return {
        'Booking ID': booking_id,
        'Date': date_formatted,
        'Time': time_formatted,
        'Visitors': visitors,
        'Ticket Type': ticket_type,
        'First Name': first_name,
        'Last Name': last_name,
        'Email': email,
        'Phone': phone,
        'Status': status,
        'Created At': created_at,
        'Notes': notes
    }

def parse_participants(bokun_booking):
    """Parse participants from Bokun booking"""
    
    booking_id = bokun_booking.get('confirmationCode', '') or str(bokun_booking.get('id', ''))
    participants = bokun_booking.get('participants', [])
    
    result = []
    for idx, participant in enumerate(participants, 1):
        result.append({
            'Booking ID': booking_id,
            'Participant #': idx,
            'First Name': participant.get('firstName', ''),
            'Last Name': participant.get('lastName', ''),
            'Birth Date': participant.get('dateOfBirth', ''),
            'Gender': 'M' if participant.get('gender', '').upper() in ['MALE', 'M'] else 'F',
            'Email': participant.get('email', ''),
            'Phone': participant.get('phoneNumber', ''),
            'Notes': ''
        })
    
    return result

def add_sample_data():
    """Add sample data to Google Sheets"""
    
    print("=" * 80)
    print("📊 Creating Bokun → Google Sheets Mapping with Sample Data")
    print("=" * 80)
    
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
    
    # Get worksheets
    ws_input = sheet.worksheet('Bookings_Input')
    ws_participants = sheet.worksheet('Participants')
    
    print("\n" + "=" * 80)
    print("📋 BOKUN API RESPONSE FORMAT:")
    print("=" * 80)
    print("""
Bokun API returns bookings in this format:

{
  "confirmationCode": "BK-2026-001234",
  "id": "12345678",
  "status": "CONFIRMED",
  "createdDate": "2026-05-26T10:30:00Z",
  "startTime": "2026-06-15T10:00:00Z",
  "product": {
    "title": "Vatican Museums and Sistine Chapel - Skip the Line"
  },
  "numberOfParticipants": 2,
  "customer": {
    "firstName": "John",
    "lastName": "Doe",
    "email": "john.doe@example.com",
    "phoneNumber": "+39 333 123 4567"
  },
  "participants": [
    {
      "firstName": "John",
      "lastName": "Doe",
      "dateOfBirth": "1990-01-01",
      "gender": "MALE"
    }
  ],
  "price": {
    "totalPrice": 68.00,
    "currency": "EUR"
  }
}
""")
    
    print("\n" + "=" * 80)
    print("🔄 FIELD MAPPING:")
    print("=" * 80)
    print("""
Bokun Field                    → Google Sheets Column
─────────────────────────────────────────────────────────────
confirmationCode               → Booking ID
startTime (date part)          → Date (DD/MM/YYYY)
startTime (time part)          → Time (HH:MM)
numberOfParticipants           → Visitors
product.title                  → Ticket Type
customer.firstName             → First Name
customer.lastName              → Last Name
customer.email                 → Email
customer.phoneNumber           → Phone
status (converted)             → Status (always "Pending")
createdDate                    → Created At
notes + price                  → Notes
""")
    
    # Parse sample booking
    sheets_data = parse_bokun_to_sheets_format(BOKUN_SAMPLE_RESPONSE)
    participants_data = parse_participants(BOKUN_SAMPLE_RESPONSE)
    
    print("\n" + "=" * 80)
    print("📝 PARSED DATA FOR GOOGLE SHEETS:")
    print("=" * 80)
    print("\nBookings_Input row:")
    for key, value in sheets_data.items():
        print(f"  {key}: {value}")
    
    print("\nParticipants rows:")
    for idx, participant in enumerate(participants_data, 1):
        print(f"\n  Participant {idx}:")
        for key, value in participant.items():
            print(f"    {key}: {value}")
    
    # Add sample data to sheets
    print("\n" + "=" * 80)
    print("💾 Adding Sample Data to Google Sheets...")
    print("=" * 80)
    
    # Check if sample already exists
    try:
        cell = ws_input.find('BK-2026-001234')
        print("ℹ️ Sample booking already exists, skipping...")
    except:
        # Add to Bookings_Input
        row = [
            sheets_data['Booking ID'],
            sheets_data['Date'],
            sheets_data['Time'],
            sheets_data['Visitors'],
            sheets_data['Ticket Type'],
            sheets_data['First Name'],
            sheets_data['Last Name'],
            sheets_data['Email'],
            sheets_data['Phone'],
            sheets_data['Status'],
            sheets_data['Created At'],
            sheets_data['Notes']
        ]
        ws_input.append_row(row)
        print("✅ Added sample booking to Bookings_Input")
        
        # Add participants
        for participant in participants_data:
            row = [
                participant['Booking ID'],
                participant['Participant #'],
                participant['First Name'],
                participant['Last Name'],
                participant['Birth Date'],
                participant['Gender'],
                participant['Email'],
                participant['Phone'],
                participant['Notes']
            ]
            ws_participants.append_row(row)
        
        print(f"✅ Added {len(participants_data)} participants to Participants worksheet")
    
    # Add more sample bookings
    print("\n📝 Adding more sample bookings...")
    
    sample_bookings = [
        {
            'confirmationCode': 'BK-2026-001235',
            'startTime': '2026-06-20T14:00:00Z',
            'numberOfParticipants': 1,
            'product': {'title': 'Vatican Museums - Standard Entry'},
            'customer': {
                'firstName': 'Maria',
                'lastName': 'Garcia',
                'email': 'maria.garcia@example.com',
                'phoneNumber': '+34 666 777 888'
            },
            'participants': [
                {
                    'firstName': 'Maria',
                    'lastName': 'Garcia',
                    'dateOfBirth': '1985-03-20',
                    'gender': 'FEMALE',
                    'email': 'maria.garcia@example.com'
                }
            ],
            'status': 'CONFIRMED',
            'createdDate': '2026-05-26T11:00:00Z',
            'price': {'totalPrice': 34.00, 'currency': 'EUR'}
        },
        {
            'confirmationCode': 'BK-2026-001236',
            'startTime': '2026-07-05T09:00:00Z',
            'numberOfParticipants': 4,
            'product': {'title': 'Vatican Museums - Guided Tour in English'},
            'customer': {
                'firstName': 'Robert',
                'lastName': 'Smith',
                'email': 'robert.smith@example.com',
                'phoneNumber': '+44 7700 900 123'
            },
            'participants': [
                {
                    'firstName': 'Robert',
                    'lastName': 'Smith',
                    'dateOfBirth': '1975-08-10',
                    'gender': 'MALE'
                },
                {
                    'firstName': 'Sarah',
                    'lastName': 'Smith',
                    'dateOfBirth': '1978-11-25',
                    'gender': 'FEMALE'
                },
                {
                    'firstName': 'Tom',
                    'lastName': 'Smith',
                    'dateOfBirth': '2010-04-15',
                    'gender': 'MALE'
                },
                {
                    'firstName': 'Emma',
                    'lastName': 'Smith',
                    'dateOfBirth': '2012-09-30',
                    'gender': 'FEMALE'
                }
            ],
            'status': 'CONFIRMED',
            'createdDate': '2026-05-26T12:30:00Z',
            'price': {'totalPrice': 136.00, 'currency': 'EUR'}
        }
    ]
    
    added_count = 0
    for booking in sample_bookings:
        try:
            cell = ws_input.find(booking['confirmationCode'])
            print(f"  ℹ️ {booking['confirmationCode']} already exists, skipping...")
        except:
            sheets_data = parse_bokun_to_sheets_format(booking)
            participants_data = parse_participants(booking)
            
            # Add to Bookings_Input
            row = [
                sheets_data['Booking ID'],
                sheets_data['Date'],
                sheets_data['Time'],
                sheets_data['Visitors'],
                sheets_data['Ticket Type'],
                sheets_data['First Name'],
                sheets_data['Last Name'],
                sheets_data['Email'],
                sheets_data['Phone'],
                sheets_data['Status'],
                sheets_data['Created At'],
                sheets_data['Notes']
            ]
            ws_input.append_row(row)
            
            # Add participants
            for participant in participants_data:
                row = [
                    participant['Booking ID'],
                    participant['Participant #'],
                    participant['First Name'],
                    participant['Last Name'],
                    participant['Birth Date'],
                    participant['Gender'],
                    participant['Email'],
                    participant['Phone'],
                    participant['Notes']
                ]
                ws_participants.append_row(row)
            
            added_count += 1
            print(f"  ✅ Added {booking['confirmationCode']}")
    
    print(f"\n✅ Added {added_count} new sample bookings")
    
    print("\n" + "=" * 80)
    print("✅ SETUP COMPLETE!")
    print("=" * 80)
    print(f"""
📊 Your Google Sheets now has sample data:
   - 3 sample bookings in Bookings_Input
   - 7 participants in Participants worksheet

🔗 View your sheet:
   https://docs.google.com/spreadsheets/d/{SHEET_ID}

📋 Column Structure:

Bookings_Input:
  A: Booking ID (from Bokun confirmationCode)
  B: Date (DD/MM/YYYY format)
  C: Time (HH:MM format)
  D: Visitors (number of participants)
  E: Ticket Type (product title)
  F: First Name (customer)
  G: Last Name (customer)
  H: Email (customer)
  I: Phone (customer)
  J: Status (always "Pending" for bot)
  K: Created At (ISO timestamp)
  L: Notes (includes price and notes)

Participants:
  A: Booking ID
  B: Participant # (1, 2, 3, etc.)
  C: First Name
  D: Last Name
  E: Birth Date (YYYY-MM-DD)
  F: Gender (M/F)
  G: Email
  H: Phone
  I: Notes

🤖 Bot Integration:
   The bot will:
   1. Fetch bookings from Bokun API every 5 minutes
   2. Parse using the mapping above
   3. Write to Bookings_Input worksheet
   4. Write participants to Participants worksheet
   5. Create monitoring tasks automatically
   6. Update Bookings_Output when slots found

✅ Ready to deploy!
""")

if __name__ == '__main__':
    try:
        add_sample_data()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
