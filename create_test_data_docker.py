#!/usr/bin/env python3
"""
Create Test Data in Docker PostgreSQL Database
===============================================
This script creates test data directly in the Docker PostgreSQL database
so the extension can detect available slots via the API.

Usage:
    docker-compose exec backend python /app/create_test_data_docker.py
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/app/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import Agency, MonitorTask, HeldSlot, BuyerProfile
from django.utils import timezone
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

def create_test_agency():
    """Create or get test agency"""
    agency, created = Agency.objects.get_or_create(
        name="Test Agency",
        defaults={
            'telegram_chat_id': '123456789',
            'plan': 'pro',
            'is_active': True,
            'google_sheet_url': 'https://docs.google.com/spreadsheets/d/test'
        }
    )
    
    if created:
        print(f"✅ Created test agency: {agency.name} (ID: {agency.id})")
    else:
        print(f"✅ Using existing test agency: {agency.name} (ID: {agency.id})")
    
    return agency

def create_test_buyer_profile(agency):
    """Create or get test buyer profile"""
    profile, created = BuyerProfile.objects.get_or_create(
        agency=agency,
        first_name="John",
        last_name="Doe",
        defaults={
            'email': 'john.doe@example.com',
            'phone': '+393331234567',  # Italian format
            'birth_date': '1990-01-01',
            'city': 'Rome',
            'country': 'IT',
            'participants_json': '[{"first_name": "John", "last_name": "Doe"}, {"first_name": "Jane", "last_name": "Doe"}]'
        }
    )
    
    if created:
        print(f"✅ Created test buyer profile: {profile.first_name} {profile.last_name}")
    else:
        print(f"✅ Using existing buyer profile: {profile.first_name} {profile.last_name}")
    
    return profile

def create_test_tasks(agency, num_tasks=5):
    """Create test monitoring tasks for August"""
    print(f"\n📋 Creating {num_tasks} test tasks for August...")
    
    # Start from August 25, 2026 (end of month)
    base_date = datetime(2026, 8, 25, tzinfo=ZoneInfo("Europe/Rome"))
    
    tasks = []
    for i in range(num_tasks):
        date = base_date + timedelta(days=i)
        date_str = date.strftime('%Y-%m-%d')
        
        # Check if task already exists
        existing_tasks = MonitorTask.objects.filter(
            agency=agency,
            ticket_name__icontains='TEST'
        )
        
        existing = None
        for task in existing_tasks:
            if date_str in task.dates:
                existing = task
                break
        
        if existing:
            print(f"   ⏭️  Task already exists: {date_str} (ID: {existing.id})")
            tasks.append(existing)
            continue
        
        task = MonitorTask.objects.create(
            agency=agency,
            site='vatican',
            area_name='Vatican Museums',
            dates=[date_str],
            preferred_times=['09:00', '10:00', '14:00'],
            visitors=2,
            adult_count=2,
            child_count=0,
            ticket_type=0,  # Standard ticket
            ticket_name=f'TEST - Vatican Museums - Standard Entry {i+1}',
            ticket_id=None,
            language=None,
            check_interval=60,
            tier='snipe',
            match_strategy='any',
            notification_mode='available_only',
            is_active=True
        )
        
        print(f"   ✅ Created task {i+1}: {date_str} (ID: {task.id})")
        tasks.append(task)
    
    return tasks

def create_test_slots(tasks):
    """Create test available slots (HeldSlot records)"""
    print(f"\n🎫 Creating test available slots...")
    
    slots = []
    slot_count = 0
    
    for task in tasks:
        # Get date from task and convert to DD/MM/YYYY format for HeldSlot
        task_date_str = task.dates[0]  # YYYY-MM-DD format
        # Convert to DD/MM/YYYY for Vatican API
        from datetime import datetime
        date_obj = datetime.strptime(task_date_str, '%Y-%m-%d')
        date_str = date_obj.strftime('%d/%m/%Y')  # DD/MM/YYYY format
        
        # Create 2-3 slots per task
        num_slots = 2 if slot_count % 2 == 0 else 3
        times = ['09:00', '10:00', '11:00'][:num_slots]
        
        for time in times:
            # Check if slot already exists
            existing = HeldSlot.objects.filter(
                task=task,
                date=date_str,
                slot_time=time  # Fixed: use slot_time instead of time
            ).first()
            
            if existing:
                print(f"   ⏭️  Slot already exists: {date_str} {time}")
                slots.append(existing)
                continue
            
            slot = HeldSlot.objects.create(
                task=task,
                date=date_str,  # DD/MM/YYYY format
                slot_id=f'TEST_{slot_count+1}',  # Fixed: use TEST prefix
                slot_time=time,  # Fixed: use slot_time instead of time
                ticket_id='TEST_TICKET_123',
                ticket_name='Vatican Museums - Standard Entry',
                visitors=2,
                adult_count=2,
                child_count=0,
                total_price=34.00,
                jsessionid='TEST_SESSION',
                ticketmv='TEST_TICKETMV',
                recap_id=f'TEST_RECAP_{slot_count+1}',
                status='held',
                payment_ready=True,
                payment_url=f'https://tickets.museivaticani.va/payment/test_{slot_count+1}'
            )
            
            print(f"   ✅ Created slot: {date_str} {time} (ID: {slot.id})")
            slots.append(slot)
            slot_count += 1
    
    return slots

def print_summary(agency, tasks, slots):
    """Print test setup summary"""
    print("\n" + "=" * 80)
    print("🎉 TEST SETUP COMPLETE!")
    print("=" * 80)
    
    print(f"\n📊 Summary:")
    print(f"   Agency: {agency.name} (ID: {agency.id})")
    print(f"   Tasks: {len(tasks)}")
    print(f"   Available Slots: {len(slots)}")
    
    # Group slots by date
    from collections import defaultdict
    slots_by_date = defaultdict(list)
    for slot in slots:
        slots_by_date[slot.date].append(slot.slot_time)  # Fixed: use slot_time
    
    print(f"\n📅 Test Dates:")
    for date in sorted(slots_by_date.keys()):
        times = ', '.join(sorted(slots_by_date[date]))
        print(f"   {date}: {len(slots_by_date[date])} slots at {times}")
    
    print(f"\n🔧 Extension Configuration:")
    print(f"   Backend URL: http://localhost:8000")
    print(f"   Agency ID: {agency.id}")
    print(f"   Backend Listener: ON")
    
    print(f"\n🧪 Testing Steps:")
    print(f"   1. Configure extension with Agency ID: {agency.id}")
    print(f"   2. Enable Backend Listener Mode")
    print(f"   3. Extension will detect {len(slots)} available slots")
    print(f"   4. Extension will open 10 incognito windows")
    print(f"   5. Watch the magic happen! 🎉")
    
    print(f"\n📝 API Endpoint to Test:")
    print(f"   GET http://localhost:8000/api/v1/available-slots/?agency_id={agency.id}")
    
    print("\n" + "=" * 80)

def main():
    print("\n" + "=" * 80)
    print("🧪 TEST EXTENSION FLOW - AUGUST SLOTS (DOCKER)")
    print("=" * 80)
    
    # Create test data
    agency = create_test_agency()
    buyer_profile = create_test_buyer_profile(agency)
    tasks = create_test_tasks(agency, num_tasks=5)
    slots = create_test_slots(tasks)
    
    # Print summary
    print_summary(agency, tasks, slots)

if __name__ == '__main__':
    main()
