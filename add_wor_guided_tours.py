#!/usr/bin/env python
"""
Add guided tour monitoring tasks for WOR agency
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django
django.setup()

from monitors.models import MonitorTask, Agency

def add_guided_tour_monitoring():
    print("=" * 60)
    print("ADDING GUIDED TOUR MONITORING FOR WOR")
    print("=" * 60)
    print()
    
    # Get WOR agency
    try:
        wor = Agency.objects.get(name='WOR')
        print(f"✅ Found WOR agency (ID: {wor.id})")
    except Agency.DoesNotExist:
        print("❌ WOR agency not found!")
        return
    
    # Get existing standard ticket tasks
    standard_tasks = MonitorTask.objects.filter(
        agency=wor,
        is_active=True,
        ticket_type=0  # Standard tickets
    ).order_by('id')
    
    print(f"✅ Found {standard_tasks.count()} standard ticket tasks")
    print()
    
    # Check if guided tours already exist
    existing_guided = MonitorTask.objects.filter(
        agency=wor,
        is_active=True,
        ticket_type=1  # Guided tours
    ).count()
    
    if existing_guided > 0:
        print(f"⚠️  WOR already has {existing_guided} guided tour tasks!")
        print("   Skipping creation to avoid duplicates.")
        return
    
    # Create guided tour tasks for same dates
    print("Creating guided tour monitoring tasks...")
    print()
    
    created_count = 0
    languages = ['ENG']  # Start with English, can add more later
    
    for task in standard_tasks:
        for lang in languages:
            new_task = MonitorTask.objects.create(
                agency=wor,
                site='vatican',
                area_name='Musei Vaticani',
                dates=task.dates,  # Same dates as standard tickets
                preferred_times=task.preferred_times,  # Same times
                visitors=task.visitors,
                adult_count=task.adult_count,
                child_count=task.child_count,
                ticket_type=1,  # Guided tour
                ticket_name='Musei Vaticani - Visite Guidate',
                language=lang,  # English tours
                check_interval=60,
                tier=task.tier,  # Same tier as standard
                notification_mode='available_only',  # Only notify when available
                match_strategy=task.match_strategy,
                is_active=True
            )
            created_count += 1
            
            # Show first 5 and last 5
            if created_count <= 5 or created_count > standard_tasks.count() - 5:
                print(f"✅ Created: {new_task.ticket_name} [{lang}] - {task.dates[0]}")
            elif created_count == 6:
                print(f"   ... creating {standard_tasks.count() - 10} more tasks ...")
    
    print()
    print("=" * 60)
    print(f"✅ CREATED {created_count} GUIDED TOUR MONITORING TASKS")
    print("=" * 60)
    print()
    
    # Show summary
    print("📊 WOR MONITORING SUMMARY:")
    print()
    
    standard_count = MonitorTask.objects.filter(
        agency=wor, is_active=True, ticket_type=0
    ).count()
    
    guided_count = MonitorTask.objects.filter(
        agency=wor, is_active=True, ticket_type=1
    ).count()
    
    print(f"  Standard Entry Tickets: {standard_count} tasks")
    print(f"  Guided Tours (English):  {guided_count} tasks")
    print(f"  Total Active Tasks:      {standard_count + guided_count} tasks")
    print()
    
    # Show date range
    all_tasks = MonitorTask.objects.filter(
        agency=wor, is_active=True
    ).order_by('id')
    
    if all_tasks.exists():
        first_date = all_tasks.first().dates[0] if all_tasks.first().dates else 'N/A'
        last_date = all_tasks.last().dates[0] if all_tasks.last().dates else 'N/A'
        print(f"  Date Range: {first_date} to {last_date}")
    
    print()
    print("✅ WOR will now receive notifications for:")
    print("   - Standard entry tickets (Musei Vaticani - Biglietti d'ingresso)")
    print("   - English guided tours (Musei Vaticani - Visite Guidate)")
    print()
    print("🔔 Notifications will be sent to WOR Bot Telegram group")
    print("   when slots become available!")
    print()

if __name__ == '__main__':
    add_guided_tour_monitoring()
