#!/usr/bin/env python
"""Activate monitoring for WOR agency"""
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

# Create monitoring task
task = MonitorTask.objects.create(
    agency=wor,
    site='vatican',
    dates=['04/05/2026', '05/05/2026', '06/05/2026'],
    preferred_times=['09:00', '10:00', '14:00'],
    visitors=1,
    ticket_type=0,
    ticket_name="Musei Vaticani - Biglietti d'ingresso",
    tier='notify',
    check_interval=60,
    is_active=True
)

print(f"✅ Created task #{task.id} for WOR agency")
print(f"   Dates: {', '.join(task.dates)}")
print(f"   Ticket: {task.ticket_name}")
print(f"   Visitors: {task.visitors}")
print(f"   Tier: {task.tier}")
print(f"   Check interval: {task.check_interval}s")
print(f"   Status: {'Active' if task.is_active else 'Inactive'}")
print()
print("🚀 WOR monitoring is now active!")
print("   The bot will check for tickets every 60 seconds")
print("   Telegram alerts will be sent when tickets become available")
