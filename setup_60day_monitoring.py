#!/usr/bin/env python3
"""
Setup 60-day monitoring for agencies with approved Telegram groups
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django
django.setup()

from monitors.models import Agency, MonitorTask, TelegramGroup
from datetime import datetime, timedelta

def setup_monitoring():
    # Get agencies with approved Telegram groups
    agencies = Agency.objects.filter(telegram_groups__status='approved').distinct()
    
    print(f"📊 Found {agencies.count()} agencies with approved Telegram groups\n")
    
    # Generate next 60 days
    today = datetime.now().date()
    dates = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, 61)]
    
    print(f"📅 Date range: {dates[0]} to {dates[-1]}\n")
    
    for agency in agencies:
        print(f"\n{'='*60}")
        print(f"🏢 Agency: {agency.name}")
        print(f"{'='*60}")
        
        # Check existing tasks
        existing_tasks = MonitorTask.objects.filter(agency=agency, is_active=True)
        print(f"   Current active tasks: {existing_tasks.count()}")
        
        # Get Telegram groups
        telegram_groups = agency.telegram_groups.filter(status='approved')
        print(f"   Telegram groups: {telegram_groups.count()}")
        for tg in telegram_groups:
            print(f"      - {tg.chat_title} ({tg.chat_id})")
        
        # Check if agency needs new monitoring tasks
        if existing_tasks.count() == 0:
            print(f"\n   ⚠️  No active tasks found!")
            print(f"   Creating new monitoring task for next 60 days...")
            
            # Create a standard monitoring task
            task = MonitorTask.objects.create(
                agency=agency,
                site='vatican',
                area_name='Musei Vaticani',
                dates=dates,
                preferred_times=['09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00'],
                visitors=1,
                adult_count=1,
                child_count=0,
                ticket_type=0,  # Standard ticket
                ticket_name='Musei Vaticani - Biglietti d\'ingresso',
                check_interval=60,
                tier='notify',
                match_strategy='any',
                notification_mode='available_only',
                is_active=True
            )
            print(f"   ✅ Created task #{task.id} - Monitoring {len(dates)} dates")
        else:
            # Update existing tasks with new dates
            print(f"\n   Updating existing tasks with 60-day date range...")
            updated = 0
            for task in existing_tasks[:5]:  # Update first 5 tasks
                old_dates = len(task.dates) if task.dates else 0
                task.dates = dates
                task.save()
                updated += 1
                print(f"   ✅ Updated task #{task.id}: {old_dates} → {len(dates)} dates")
            
            if updated > 0:
                print(f"\n   📊 Updated {updated} tasks with 60-day monitoring")
    
    print(f"\n{'='*60}")
    print(f"✅ Setup complete!")
    print(f"{'='*60}\n")
    
    # Summary
    print("\n📊 SUMMARY:")
    print(f"   Total agencies: {agencies.count()}")
    print(f"   Total active tasks: {MonitorTask.objects.filter(is_active=True).count()}")
    print(f"   Date range: {dates[0]} to {dates[-1]} (60 days)")
    print(f"   Monitoring: Vatican Museums standard tickets")

if __name__ == '__main__':
    setup_monitoring()
