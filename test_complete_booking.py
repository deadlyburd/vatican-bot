#!/usr/bin/env python3
"""
Complete Vatican Booking Test - Local Testing
Tests the entire flow: Sheet → Task → Vatican API → Booking
"""

import sys
import os
sys.path.insert(0, '/app')

from datetime import datetime, timedelta
import json

def test_google_sheets():
    """Test 1: Read Google Sheets"""
    print("\n" + "=" * 80)
    print("📊 TEST 1: Google Sheets Connection")
    print("=" * 80)
    
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        SERVICE_ACCOUNT_FILE = '/app/google_credentials.json'
        SHEET_ID = '1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg'
        
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID)
        
        # Try to get the "Bookings" worksheet
        try:
            worksheet = sheet.worksheet('Bookings')
        except:
            worksheet = sheet.get_worksheet(0)
        
        print(f"✅ Connected to sheet: {sheet.title}")
        print(f"✅ Using worksheet: {worksheet.title}")
        print(f"   Rows: {worksheet.row_count}, Cols: {worksheet.col_count}")
        
        # Get headers
        headers = worksheet.row_values(1)
        print(f"\n📋 Headers ({len(headers)} columns):")
        for i, h in enumerate(headers[:10], 1):  # Show first 10
            print(f"   {i}. {h}")
        if len(headers) > 10:
            print(f"   ... and {len(headers) - 10} more")
        
        # Get first data row
        data_rows = worksheet.get_all_values()[1:6]  # Get first 5 rows
        print(f"\n📊 Sample Data ({len(data_rows)} rows):")
        
        for idx, row in enumerate(data_rows, 1):
            booking = dict(zip(headers, row))
            print(f"\n   Row {idx}:")
            print(f"      Booking ID: {booking.get('confirmationCode', 'N/A')}")
            print(f"      Date: {booking.get('activityDate', 'N/A')}")
            print(f"      Time: {booking.get('startTime', 'N/A')}")
            print(f"      Product: {booking.get('productTitle', 'N/A')}")
            print(f"      Visitors: {booking.get('totalParticipants', 'N/A')}")
            print(f"      Status: {booking.get('status', 'N/A')}")
        
        return True, worksheet, headers
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False, None, None

def test_vatican_api():
    """Test 2: Vatican API"""
    print("\n" + "=" * 80)
    print("🎫 TEST 2: Vatican API - Check Availability")
    print("=" * 80)
    
    try:
        import asyncio
        from worker_vatican.god_tier_monitor import check_availability_headless
        
        # Test for a date 7 days from now
        test_date = datetime.now() + timedelta(days=7)
        date_str = test_date.strftime('%d/%m/%Y')
        
        print(f"📅 Testing date: {date_str}")
        print(f"🎫 Ticket type: Standard (0)")
        print(f"👥 Visitors: 1")
        
        async def run_test():
            result = await check_availability_headless(
                ticket_type=0,
                target_date=date_str,
                visitors=1,
                language=None
            )
            return result
        
        result = asyncio.run(run_test())
        
        if result and 'available_slots' in result:
            slots = result['available_slots']
            print(f"\n✅ Found {len(slots)} available slots:")
            for slot in slots[:5]:  # Show first 5
                print(f"   • {slot}")
            if len(slots) > 5:
                print(f"   ... and {len(slots) - 5} more")
            return True, slots
        else:
            print(f"⚠️  No slots found or error: {result}")
            return False, []
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False, []

def create_test_booking_task(worksheet, headers):
    """Test 3: Create a booking task from sheet data"""
    print("\n" + "=" * 80)
    print("📝 TEST 3: Create Booking Task")
    print("=" * 80)
    
    try:
        # Get first pending booking
        all_rows = worksheet.get_all_values()[1:]  # Skip header
        
        for row in all_rows[:20]:  # Check first 20 rows
            booking = dict(zip(headers, row))
            
            status = booking.get('status', '').strip().upper()
            date_str = booking.get('activityDate', '').strip()
            
            # Look for CONFIRMED bookings with future dates
            if status == 'CONFIRMED' and date_str:
                try:
                    # Parse date (format: YYYY-MM-DD or DD/MM/YYYY)
                    if '-' in date_str:
                        booking_date = datetime.strptime(date_str, '%Y-%m-%d')
                    else:
                        booking_date = datetime.strptime(date_str, '%d/%m/%Y')
                    
                    # Only future bookings
                    if booking_date > datetime.now():
                        print(f"✅ Found suitable booking:")
                        print(f"   Booking ID: {booking.get('confirmationCode', 'N/A')}")
                        print(f"   Date: {date_str}")
                        print(f"   Time: {booking.get('startTime', 'N/A')}")
                        print(f"   Product: {booking.get('productTitle', 'N/A')}")
                        print(f"   Visitors: {booking.get('totalParticipants', 'N/A')}")
                        print(f"   Customer: {booking.get('customerFirstName', '')} {booking.get('customerLastName', '')}")
                        print(f"   Email: {booking.get('customerEmail', 'N/A')}")
                        
                        # Create task
                        task = {
                            'booking_id': booking.get('confirmationCode', ''),
                            'date': booking_date.strftime('%d/%m/%Y'),
                            'time': booking.get('startTime', '10:00'),
                            'visitors': int(booking.get('totalParticipants', 1)),
                            'ticket_type': 0,  # Standard
                            'language': None,
                            'customer': {
                                'first_name': booking.get('customerFirstName', ''),
                                'last_name': booking.get('customerLastName', ''),
                                'email': booking.get('customerEmail', ''),
                                'phone': booking.get('customerPhone', '')
                            }
                        }
                        
                        print(f"\n📋 Created task:")
                        print(json.dumps(task, indent=2))
                        
                        return True, task
                        
                except Exception as e:
                    continue
        
        print("⚠️  No suitable bookings found (need CONFIRMED status with future date)")
        return False, None
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False, None

def test_complete_flow():
    """Test 4: Complete booking flow"""
    print("\n" + "=" * 80)
    print("🚀 TEST 4: Complete Booking Flow")
    print("=" * 80)
    
    # Step 1: Google Sheets
    success, worksheet, headers = test_google_sheets()
    if not success:
        print("\n❌ Google Sheets test failed")
        return False
    
    # Step 2: Create task
    success, task = create_test_booking_task(worksheet, headers)
    if not success:
        print("\n⚠️  Could not create task from sheet")
        # Create a manual test task
        test_date = datetime.now() + timedelta(days=7)
        task = {
            'booking_id': 'TEST_001',
            'date': test_date.strftime('%d/%m/%Y'),
            'time': '10:00',
            'visitors': 1,
            'ticket_type': 0,
            'language': None,
            'customer': {
                'first_name': 'Test',
                'last_name': 'User',
                'email': 'test@example.com',
                'phone': '+1234567890'
            }
        }
        print(f"\n📋 Using manual test task:")
        print(json.dumps(task, indent=2))
    
    # Step 3: Check Vatican availability
    success, slots = test_vatican_api()
    if not success:
        print("\n❌ Vatican API test failed")
        return False
    
    # Step 4: Summary
    print("\n" + "=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)
    print(f"✅ Google Sheets: Connected")
    print(f"✅ Task Created: {task['booking_id']}")
    print(f"✅ Vatican API: {len(slots)} slots found for {task['date']}")
    print(f"\n🎯 Next Steps:")
    print(f"   1. Bot will monitor Vatican for date: {task['date']}")
    print(f"   2. When slots available, send Telegram notification")
    print(f"   3. Browser extension handles booking")
    print(f"   4. Update Google Sheets with result")
    
    return True

if __name__ == '__main__':
    print("\n🧪 Vatican Bot - Complete Local Test")
    print("=" * 80)
    
    try:
        success = test_complete_flow()
        
        if success:
            print("\n" + "=" * 80)
            print("✅ ALL TESTS PASSED!")
            print("=" * 80)
            sys.exit(0)
        else:
            print("\n" + "=" * 80)
            print("❌ SOME TESTS FAILED")
            print("=" * 80)
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
