#!/usr/bin/env python3
"""
Create a test held slot to verify extension auto-booking functionality.

Usage:
    docker-compose exec backend python /app/create_test_slot.py
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/app/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import HeldSlot, MonitorTask, Agency
from django.utils import timezone
from datetime import timedelta

def create_test_slot():
    """Create a test held slot for extension testing."""
    
    print("🧪 Creating test held slot for extension testing...")
    print("=" * 60)
    
    # Get or create a test agency
    agency, created = Agency.objects.get_or_create(
        name="Test Agency",
        defaults={
            'telegram_chat_id': '123456789',
            'is_active': True
        }
    )
    
    if created:
        print(f"✅ Created test agency: {agency.name}")
    else:
        print(f"ℹ️  Using existing agency: {agency.name}")
    
    # Get or create a test task
    task, created = MonitorTask.objects.get_or_create(
        agency=agency,
        site='vatican',
        ticket_name='Musei Vaticani - Biglietti d\'ingresso',
        defaults={
            'dates': ['15/06/2026'],
            'visitors': 2,
            'is_active': True,
            'tier': 'hold'
        }
    )
    
    if created:
        print(f"✅ Created test task: {task.ticket_name}")
    else:
        print(f"ℹ️  Using existing task: {task.ticket_name}")
    
    # Delete any existing test slots
    deleted_count = HeldSlot.objects.filter(slot_id__startswith='TEST').delete()[0]
    if deleted_count > 0:
        print(f"🗑️  Deleted {deleted_count} old test slots")
    
    # Create a test held slot
    held_slot = HeldSlot.objects.create(
        task=task,
        date='15/06/2026',
        slot_time='09:00',
        slot_id='TEST_SLOT_123456',
        ticket_id='2129030053',
        ticket_name='Musei Vaticani - Biglietti d\'ingresso',
        visitors=2,
        adult_count=2,
        child_count=0,
        total_price=35.00,
        status='held',
        hold_started_at=timezone.now(),
        last_keepalive_at=timezone.now()
    )
    
    print("=" * 60)
    print("✅ TEST SLOT CREATED SUCCESSFULLY!")
    print("=" * 60)
    print(f"Slot ID:      {held_slot.id}")
    print(f"Date:         {held_slot.date}")
    print(f"Time:         {held_slot.slot_time}")
    print(f"Ticket:       {held_slot.ticket_name}")
    print(f"Visitors:     {held_slot.visitors}")
    print(f"Status:       {held_slot.status}")
    print(f"Created:      {held_slot.hold_started_at}")
    print("=" * 60)
    print()
    print("🎯 NEXT STEPS:")
    print("1. Open your browser with the extension")
    print("2. Open browser console (F12)")
    print("3. Wait 10 seconds for extension to poll")
    print("4. Look for: '🎉 Found 1 available slots from backend!'")
    print("5. Incognito window should open automatically")
    print()
    print("📊 CHECK API ENDPOINT:")
    print("   curl http://localhost:8000/api/v1/available-slots/")
    print()
    print("🗑️  TO DELETE TEST SLOT:")
    print(f"   docker-compose exec backend python /app/delete_test_slot.py")
    print()
    
    return held_slot

def main():
    try:
        slot = create_test_slot()
        sys.exit(0)
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
