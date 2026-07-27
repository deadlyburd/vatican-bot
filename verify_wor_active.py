#!/usr/bin/env python
"""Verify WOR monitoring is active"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, 'backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import Agency, MonitorTask

# Get WOR agency
wor = Agency.objects.get(name='WOR')

# Check active tasks
active_tasks = MonitorTask.objects.filter(agency=wor, is_active=True)

print("="*60)
print("WOR MONITORING STATUS")
print("="*60)
print()

if active_tasks.exists():
    print(f"✅ WOR monitoring is ACTIVE")
    print(f"   Active tasks: {active_tasks.count()}")
    print()
    
    for task in active_tasks:
        print(f"📋 Task #{task.id}:")
        print(f"   Dates: {', '.join(task.dates)}")
        print(f"   Ticket: {task.ticket_name}")
        print(f"   Visitors: {task.visitors}")
        print(f"   Tier: {task.tier}")
        print(f"   Check interval: {task.check_interval}s")
        print(f"   Last check: {task.last_checked or 'Never'}")
        print(f"   Last status: {task.last_status or 'Unknown'}")
        print()
    
    print("🚀 What happens next:")
    print("   1. Celery beat will dispatch monitoring tasks every 60s")
    print("   2. Worker will check Vatican API for ticket availability")
    print("   3. When tickets become available, Telegram alerts will be sent")
    print("   4. Check worker logs: docker logs -f travelagenntbot-worker_vatican-1")
    print()
    print("✅ WOR is now being monitored!")
else:
    print(f"❌ WOR monitoring is NOT active")
    print(f"   No active tasks found")
    print()
    print("Run activate_wor_monitoring.py to create a task")

print("="*60)
