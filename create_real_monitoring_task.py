#!/usr/bin/env python3
"""
Create Real Vatican Monitoring Task
====================================
This script creates a real monitoring task for Vatican Museums
with actual future dates (not test data).

Usage:
    docker-compose exec backend python /app/create_real_monitoring_task.py
"""

import os
import sys
import django
from datetime import datetime, timedelta

# Setup Django
sys.path.insert(0, '/app/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import Agency, MonitorTask, HeldSlot

def remove_test_data():
    """Remove test data"""
    print("\n🧹 Removing test data...")
    
    # Remove test slots
    test_slots = HeldSlot.objects.filter(slot_id__startswith='TEST')
    count = test_slots.count()
    test_slots.delete()
    print(f"   ✅ Removed {count} test slots")
    
    # Remove test tasks
    test_tasks = MonitorTask.objects.filter(ticket_name__icontains='TEST')
    count = test_tasks.count()
    test_tasks.delete()
    print(f"   ✅ Removed {count} test tasks")

def create_real_task(agency_id=15, start_date_str='2026-06-15', num_days=6):
    """
    Create a real monitoring task for Vatican
    
    Args:
        agency_id: Agency ID (default: 15)
        start_date_str: Start date in YYYY-MM-DD format
        num_days: Number of days to monitor
    """
    print("\n📋 Creating real monitoring task...")
    
    # Get agency
    try:
        agency = Agency.objects.get(id=agency_id)
        print(f"   Agency: {agency.name} (ID: {agency.id})")
    except Agency.DoesNotExist:
        print(f"   ❌ Agency {agency_id} not found")
        return None
    
    # Parse start date
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    
    # Generate dates
    dates = []
    for i in range(num_days):
        date = start_date + timedelta(days=i)
        dates.append(date.strftime('%Y-%m-%d'))
    
    # Create task
    task = MonitorTask.objects.create(
        agency=agency,
        site='vatican',
        area_name='Vatican Museums',
        dates=dates,
        preferred_times=['09:00', '10:00', '11:00', '14:00', '15:00'],
        visitors=2,
        adult_count=2,
        child_count=0,
        ticket_type=0,  # 0 = Standard ticket, 1 = Guided tour
        ticket_name='Vatican Museums - Standard Entry',
        ticket_id=None,  # Will be resolved dynamically by worker
        language=None,  # None for standard tickets
        check_interval=300,  # Check every 5 minutes
        tier='snipe',
        match_strategy='any',
        notification_mode='available_only',
        is_active=True
    )
    
    print(f"\n✅ Created real monitoring task (ID: {task.id})")
    print(f"   📅 Dates: {', '.join(dates)}")
    print(f"   ⏰ Times: {', '.join(task.preferred_times)}")
    print(f"   👥 Visitors: {task.visitors}")
    print(f"   🔄 Check interval: {task.check_interval} seconds ({task.check_interval // 60} minutes)")
    print(f"   🎯 Ticket type: {'Standard Entry' if task.ticket_type == 0 else 'Guided Tour'}")
    
    return task

def print_instructions(task):
    """Print next steps"""
    print("\n" + "=" * 80)
    print("🎉 REAL MONITORING TASK CREATED!")
    print("=" * 80)
    
    print(f"\n📊 Task Details:")
    print(f"   ID: {task.id}")
    print(f"   Agency: {task.agency.name}")
    print(f"   Dates: {len(task.dates)} days")
    print(f"   Status: {'Active' if task.is_active else 'Inactive'}")
    
    print(f"\n🔧 What Happens Next:")
    print(f"   1. Worker monitors Vatican every {task.check_interval // 60} minutes")
    print(f"   2. Calls Search API to get fresh ticket IDs")
    print(f"   3. Checks availability for each date/time")
    print(f"   4. When slot found → Creates HeldSlot")
    print(f"   5. Telegram bot sends notification")
    print(f"   6. Extension detects slot and books")
    
    print(f"\n📝 Monitor Worker:")
    print(f"   # Watch worker logs")
    print(f"   docker-compose logs -f worker_vatican")
    print(f"")
    print(f"   # You should see:")
    print(f"   - 'Checking Vatican availability for task ID: {task.id}'")
    print(f"   - 'Calling Search API for fresh ticket IDs'")
    print(f"   - 'Found X tickets for YYYY-MM-DD'")
    
    print(f"\n🔍 Check for Available Slots:")
    print(f"   # Via API")
    print(f"   curl http://localhost:8000/api/v1/available-slots/?agency_id={task.agency_id}")
    print(f"")
    print(f"   # Via database")
    print(f"   docker-compose exec backend python /app/backend/manage.py shell")
    print(f"   >>> from monitors.models import HeldSlot")
    print(f"   >>> HeldSlot.objects.filter(task_id={task.id}, status='held').count()")
    
    print(f"\n⚠️  Important Notes:")
    print(f"   - Worker uses REAL Vatican API (not test data)")
    print(f"   - Ticket IDs are resolved dynamically (change daily)")
    print(f"   - Slots will have REAL Vatican session data")
    print(f"   - Extension can book these slots successfully")
    print(f"   - No 'General Error' when clicking ACQUISTA")
    
    print("\n" + "=" * 80)

def main():
    """Main function"""
    print("\n" + "=" * 80)
    print("🎫 CREATE REAL VATICAN MONITORING TASK")
    print("=" * 80)
    
    # Remove test data
    remove_test_data()
    
    # Create real task
    # Customize these parameters:
    task = create_real_task(
        agency_id=15,           # Your agency ID
        start_date_str='2026-06-15',  # Start date (YYYY-MM-DD)
        num_days=6              # Number of days to monitor
    )
    
    if task:
        print_instructions(task)
    else:
        print("\n❌ Failed to create task")

if __name__ == '__main__':
    main()
