#!/usr/bin/env python3
"""
Test script to check Vatican availability and test hold functionality
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from monitors.tasks_search_api import search_date

def test_availability():
    print("🔍 Testing Vatican availability for April 1st, 2026...")
    
    # Test date with known availability
    test_date = "01/04/2026"
    visitors = 2
    
    try:
        result = search_date(test_date, visitors, 'MV-Biglietti')
        
        print(f"\n📅 Availability for {test_date} ({visitors} visitors):")
        
        if not result or 'visits' not in result:
            print("❌ No availability data found")
            return
            
        available_visits = []
        for visit in result.get('visits', []):
            if visit.get('available') and visit.get('timeSlots'):
                available_visits.append(visit)
        
        if not available_visits:
            print("❌ No available time slots found")
            return
            
        print(f"✅ Found {len(available_visits)} available visit types")
        
        for visit in available_visits:
            print(f"\n🎫 {visit.get('name', 'Unknown')}")
            print(f"   ID: {visit.get('id')}")
            print(f"   Available time slots: {len(visit.get('timeSlots', []))}")
            
            # Show first 5 time slots
            for i, slot in enumerate(visit.get('timeSlots', [])[:5]):
                print(f"   {i+1}. {slot.get('time')} - {slot.get('availableTickets')} tickets (ID: {slot.get('id')})")
    
    except Exception as e:
        print(f"❌ Error testing availability: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_availability()