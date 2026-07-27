#!/usr/bin/env python3
"""
Check Telegram Groups Notification Status
==========================================
Verifies which groups are configured and receiving notifications.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import TelegramGroup, Agency

print('='*80)
print('TELEGRAM GROUPS - NOTIFICATION STATUS')
print('='*80)

agencies = Agency.objects.all().order_by('id')

for agency in agencies:
    print(f'\n📋 Agency: {agency.name} (ID: {agency.id})')
    legacy_chat = agency.telegram_chat_id or 'None'
    print(f'   Legacy Chat ID: {legacy_chat}')
    
    groups = TelegramGroup.objects.filter(agency=agency).order_by('id')
    
    if not groups.exists():
        print('   ⚠️  No Telegram groups configured')
        continue
    
    print(f'   Groups: {groups.count()}')
    
    for group in groups:
        status_icon = '✅' if group.status == 'approved' else '⚠️'
        notif_icon = '🔔' if group.notification_enabled else '🔕'
        
        print(f'   {status_icon} {notif_icon} {group.group_name}')
        print(f'      Chat ID: {group.chat_id}')
        print(f'      Status: {group.status}')
        notif_status = 'Enabled' if group.notification_enabled else 'Disabled'
        print(f'      Notifications: {notif_status}')
        print(f'      Added: {group.added_at.strftime("%Y-%m-%d %H:%M")}')

print('\n' + '='*80)
print('SUMMARY')
print('='*80)

total_groups = TelegramGroup.objects.count()
approved_groups = TelegramGroup.objects.filter(status='approved').count()
enabled_groups = TelegramGroup.objects.filter(status='approved', notification_enabled=True).count()

print(f'Total Groups: {total_groups}')
print(f'Approved Groups: {approved_groups}')
print(f'Notification Enabled: {enabled_groups}')

if enabled_groups == 0:
    print('\n⚠️  WARNING: No groups have notifications enabled!')
elif enabled_groups < approved_groups:
    print(f'\n⚠️  WARNING: {approved_groups - enabled_groups} approved groups have notifications disabled!')
else:
    print('\n✅ All approved groups have notifications enabled')

# Check for active tasks
print('\n' + '='*80)
print('ACTIVE MONITORING TASKS')
print('='*80)

from monitors.models import MonitorTask

for agency in agencies:
    active_tasks = MonitorTask.objects.filter(
        agency=agency,
        is_active=True,
        site='vatican'
    ).count()
    
    if active_tasks > 0:
        print(f'{agency.name}: {active_tasks} active tasks')

# Check recent notifications
print('\n' + '='*80)
print('RECENT NOTIFICATION ACTIVITY (Last 24 hours)')
print('='*80)

from django.utils import timezone
from datetime import timedelta

cutoff = timezone.now() - timedelta(hours=24)

from monitors.models import CheckResult

recent_available = CheckResult.objects.filter(
    check_time__gte=cutoff,
    status='available'
).count()

recent_checks = CheckResult.objects.filter(
    check_time__gte=cutoff
).count()

print(f'Total checks (24h): {recent_checks}')
print(f'Available slots found: {recent_available}')

if recent_available > 0:
    print(f'\n✅ {recent_available} availability events in last 24 hours')
    print('   Check if notifications were sent for these events')
else:
    print('\nℹ️  No availability found in last 24 hours')
    print('   This is normal if all dates are sold out')
