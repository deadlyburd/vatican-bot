"""
Setup 60-Day Vatican Monitoring for All Agencies
=================================================
This script automatically creates/updates monitoring tasks for all agencies
to monitor the next 60 dates (excluding Sundays when Vatican is closed).

Usage:
    python setup_60_day_monitoring.py
    python setup_60_day_monitoring.py --agency-id 14  # Specific agency only
    python setup_60_day_monitoring.py --dry-run       # Preview without changes
"""
import os
import sys
import django
import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Setup Django
sys.path.insert(0, 'backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import Agency, MonitorTask

ROME_TZ = ZoneInfo('Europe/Rome')


def get_next_60_dates(exclude_sundays=True):
    """Generate next 60 dates, optionally excluding Sundays (Vatican closed)."""
    dates = []
    current = datetime.now(ROME_TZ).date()
    days_added = 0
    offset = 1
    
    while days_added < 60:
        future_date = current + timedelta(days=offset)
        
        # Skip Sundays (weekday 6) if requested
        if exclude_sundays and future_date.weekday() == 6:
            offset += 1
            continue
        
        dates.append(future_date.strftime('%Y-%m-%d'))
        days_added += 1
        offset += 1
    
    return dates


def setup_monitoring_for_agency(agency, dates, dry_run=False, consolidate=False):
    """
    Setup or update monitoring task for an agency.
    
    Strategy:
    - If consolidate=True: Keep only the most recent task, deactivate others
    - If consolidate=False: Update all active tasks
    - If no tasks exist: Create new task with default settings
    """
    print(f"\n{'='*80}")
    print(f"Agency: {agency.name} (ID: {agency.id})")
    print(f"{'='*80}")
    
    # Find existing Vatican monitoring task
    existing_tasks = MonitorTask.objects.filter(
        agency=agency,
        site='vatican',
        is_active=True
    ).order_by('-created_at')
    
    if existing_tasks.exists():
        task_count = existing_tasks.count()
        print(f"\n✓ Found {task_count} active task(s)")
        
        if consolidate and task_count > 1:
            # Keep only the most recent task, deactivate others
            primary_task = existing_tasks.first()
            other_tasks = existing_tasks[1:]
            
            print(f"\n  📋 Consolidating to single task (ID: {primary_task.id})...")
            print(f"     Deactivating {len(other_tasks)} other task(s)")
            
            if not dry_run:
                for task in other_tasks:
                    task.is_active = False
                    task.save()
                    print(f"     ✓ Deactivated task {task.id}")
                
                # Update primary task
                primary_task.dates = dates
                primary_task.save()
                print(f"\n  ✅ Primary task updated to {len(dates)} dates")
            else:
                for task in other_tasks:
                    print(f"     [DRY RUN] Would deactivate task {task.id}")
                print(f"\n  [DRY RUN] Would update primary task to {len(dates)} dates")
        else:
            # Update all existing tasks
            for task in existing_tasks:
                old_dates = task.dates if isinstance(task.dates, list) else []
                print(f"\n  Task ID: {task.id}")
                print(f"    Current dates: {len(old_dates)}")
                print(f"    Ticket type: {task.get_ticket_type_display()}")
                print(f"    Visitors: {task.visitors}")
                print(f"    Tier: {task.tier}")
                
                if not dry_run:
                    task.dates = dates
                    task.save()
                    print(f"    ✅ Updated to {len(dates)} dates")
                else:
                    print(f"    [DRY RUN] Would update to {len(dates)} dates")
    else:
        # Create new task with default settings
        print(f"\n⚠️  No existing Vatican task found")
        print(f"  Creating new task with default settings...")
        
        default_config = {
            'site': 'vatican',
            'area_name': 'Musei Vaticani',
            'dates': dates,
            'preferred_times': ['09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00'],
            'visitors': 1,
            'adult_count': 1,
            'child_count': 0,
            'ticket_type': 0,  # Regular ticket
            'ticket_label': 'Musei Vaticani - Biglietti d\'ingresso',
            'ticket_name': 'Musei Vaticani - Biglietti d\'ingresso',
            'language': None,  # Not needed for regular tickets
            'check_interval': 5,  # 5 seconds (fast monitoring)
            'tier': 'notify',  # Notify only by default
            'pay_mode': 'link',
            'checkout_method': 'api',
            'match_strategy': 'any',
            'notification_mode': 'available_only',
            'is_active': True,
            'remote_worker_needed': False,
        }
        
        if not dry_run:
            task = MonitorTask.objects.create(
                agency=agency,
                **default_config
            )
            print(f"  ✅ Created new task (ID: {task.id})")
            print(f"     - {len(dates)} dates")
            print(f"     - Ticket: Regular Entry")
            print(f"     - Visitors: 1")
            print(f"     - Tier: notify")
            print(f"     - Check interval: 5 seconds")
        else:
            print(f"  [DRY RUN] Would create new task with:")
            print(f"     - {len(dates)} dates")
            print(f"     - Ticket: Regular Entry")
            print(f"     - Visitors: 1")
            print(f"     - Tier: notify")


def main():
    parser = argparse.ArgumentParser(description='Setup 60-day Vatican monitoring for all agencies')
    parser.add_argument('--agency-id', type=int, help='Setup for specific agency only')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    parser.add_argument('--include-sundays', action='store_true', help='Include Sundays (Vatican is closed)')
    parser.add_argument('--consolidate', action='store_true', help='Consolidate multiple tasks into one per agency')
    args = parser.parse_args()
    
    print("="*80)
    print("  Vatican 60-Day Monitoring Setup")
    print("="*80)
    
    # Generate dates
    dates = get_next_60_dates(exclude_sundays=not args.include_sundays)
    print(f"\nGenerated {len(dates)} dates:")
    print(f"  From: {dates[0]}")
    print(f"  To:   {dates[-1]}")
    if not args.include_sundays:
        print(f"  (Sundays excluded - Vatican closed)")
    
    # Get agencies
    if args.agency_id:
        agencies = Agency.objects.filter(id=args.agency_id)
        if not agencies.exists():
            print(f"\n❌ Agency ID {args.agency_id} not found")
            return
    else:
        agencies = Agency.objects.all().order_by('name')
    
    print(f"\nProcessing {agencies.count()} agency/agencies...")
    
    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made\n")
    
    # Process each agency
    for agency in agencies:
        setup_monitoring_for_agency(agency, dates, dry_run=args.dry_run, consolidate=args.consolidate)
    
    print("\n" + "="*80)
    if args.dry_run:
        print("✓ Dry run complete - no changes made")
        print("  Run without --dry-run to apply changes")
    else:
        print("✓ Setup complete!")
        print(f"  {agencies.count()} agency/agencies configured")
        print(f"  Monitoring {len(dates)} dates")
    print("="*80)


if __name__ == '__main__':
    main()
