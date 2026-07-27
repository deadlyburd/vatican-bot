#!/usr/bin/env python3
"""
Simple test to check Vatican availability and test hold functionality
"""
import os
import sys

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django
django.setup()

from monitors.models import Agency, MonitorTask
from monitors.tasks_sweep import _search_and_timeavail
from monitors.hold_manager import hold_slot

def simple_test():
    print("🔍 Simple Vatican Availability Test")
    print("=" * 40)
    
    # Test date
    test_date = "01/04/2026"
    visitors = 2
    
    print(f"Checking availability for {test_date} with {visitors} visitors...")
    
    # Search for available slots
    session, ticket_id, open_slots = _search_and_timeavail(test_date, visitors)
    
    if not open_slots:
        print("❌ No open slots found")
        return
    
    print(f"✅ Found {len(open_slots)} open slots:")
    for i, slot in enumerate(open_slots[:5]):  # Show first 5
        print(f"   {i+1}. {slot.get('time')} - {slot.get('availableTickets')} tickets")
    
    # Get first agency
    agency = Agency.objects.filter(is_active=True).first()
    if not agency:
        print("❌ No active agencies")
        return
    
    # Create test task
    task, created = MonitorTask.objects.get_or_create(
        agency=agency,
        defaults={
            'tier': 'hold',
            'language': 'it',
            'visitors': visitors,
            'is_active': True
        }
    )
    
    # Try to hold the first slot
    slot = open_slots[0]
    print(f"\n🔒 Attempting to hold: {slot.get('time')}")
    
    held_slot = hold_slot(
        task=task,
        date=test_date,
        slot_id=slot.get('id'),
        slot_time=slot.get('time'),
        ticket_id=ticket_id,
        ticket_name="Test Ticket",
        visitors=visitors
    )
    
    if held_slot:
        print(f"✅ Success! Hold ID: #{held_slot.id}")
        print(f"   JSESSIONID: {held_slot.jsessionid[:30]}...")
        print(f"   Recap ID: {held_slot.recap_id}")
        
        # Test session rotation
        print(f"\n🔄 Session rotation test:")
        print(f"   Hours until expiry: {held_slot.hours_until_expiry()}")
        print(f"   Hold duration: {held_slot.hold_duration_minutes()} minutes")
        
        # EPay test info
        print(f"\n💰 EPay test endpoint:")
        print(f"   http://localhost:8000/holds/{held_slot.id}/checkout/")
        print(f"   Add ?token=TURNSTILE_TOKEN for direct access")
        
        return held_slot
    else:
        print("❌ Hold failed")
        return None

if __name__ == "__main__":
    try:
        result = simple_test()
        if result:
            print("\n🎉 Test completed successfully!")
        else:
            print("\n❌ Test failed")
    except Exception as e:
        print(f"\n💥 Error: {e}")
        import traceback
        traceback.print_exc()