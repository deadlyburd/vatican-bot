#!/usr/bin/env python3
"""
Check Notification Status for All Groups
=========================================
Verifies which groups should receive notifications and checks recent activity.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import TelegramGroup, Agency, MonitorTask, CheckResult
from django.utils import timezone
from datetime import timedelta

print('='*80)
print('TELEGRAM NOTIFICATION STATUS CHECK')
print('='*80)

# Get all agencies
agencies = Agency.objects.all().order_by('id')

total_enabled_groups = 0
total_active_tasks = 0
agencies_ready = []
agencies_no_groups = []
agencies_no_tasks = []
agencies_disabled_notif = []

for agency in agencies:
    print(f'\n🏢 Agency: {agency.name} (ID: {agency.id})')
    
    # Get approved groups with notifications enabled
    approved_groups = TelegramGroup.objects.filter(
        agency=agency,
        status='approved',
        notification_enabled=True
    )
    
    # Get all groups (including disabled)
    all_groups = TelegramGroup.objects.filter(
        agency=agency,
        status='approved'
    )
    
    disabled_groups = all_groups.filter(notification_enabled=False)
    
    # Get active tasks
    active_tasks = MonitorTask.objects.filter(
        agency=agency,
        is_active=True,
        site='vatican'
    )
    
    print(f'   📱 Telegram Groups:')
    print(f'      Total approved: {all_groups.count()}')
    print(f'      Notifications enabled: {approved_groups.count()} ✅')
    print(f'      Notifications disabled: {disabled_groups.count()} ❌')
    
    if approved_groups.exists():
        print(f'   📋 Groups receiving notifications:')
        for group in approved_groups:
            name = getattr(group, 'group_name', None) or getattr(group, 'name', 'Unknown')
            print(f'      ✅ {name} ({group.chat_id})')
        total_enabled_groups += approved_groups.count()
    
    if disabled_groups.exists():
        print(f'   ⚠️  Groups NOT receiving notifications:')
        for group in disabled_groups:
            name = getattr(group, 'group_name', None) or getattr(group, 'name', 'Unknown')
            print(f'      ❌ {name} ({group.chat_id})')
    
    print(f'   🎯 Active Vatican Tasks: {active_tasks.count()}')
    
    if active_tasks.exists():
        total_active_tasks += active_tasks.count()
        # Show task details
        for task in active_tasks[:3]:  # Show first 3
            notif_mode = task.notification_mode or 'normal'
            print(f'      - Task #{task.id}: {task.ticket_name} ({notif_mode})')
        if active_tasks.count() > 3:
            print(f'      ... and {active_tasks.count() - 3} more')
    
    # Determine status
    if approved_groups.exists() and active_tasks.exists():
        print(f'   ✅ STATUS: Ready to send notifications')
        agencies_ready.append(agency.name)
    elif not approved_groups.exists() and all_groups.exists():
        print(f'   ⚠️  STATUS: Has groups but notifications disabled')
        agencies_disabled_notif.append(agency.name)
    elif not all_groups.exists():
        print(f'   ⚠️  STATUS: No Telegram groups configured')
        agencies_no_groups.append(agency.name)
    elif not active_tasks.exists():
        print(f'   ⚠️  STATUS: No active monitoring tasks')
        agencies_no_tasks.append(agency.name)

print('\n' + '='*80)
print('SUMMARY')
print('='*80)

print(f'\n📊 Overall Statistics:')
print(f'   Total Agencies: {agencies.count()}')
print(f'   Groups with notifications enabled: {total_enabled_groups}')
print(f'   Active Vatican monitoring tasks: {total_active_tasks}')

print(f'\n✅ Agencies ready to receive notifications ({len(agencies_ready)}):')
for name in agencies_ready:
    print(f'   - {name}')

if agencies_disabled_notif:
    print(f'\n⚠️  Agencies with disabled notifications ({len(agencies_disabled_notif)}):')
    for name in agencies_disabled_notif:
        print(f'   - {name}')

if agencies_no_groups:
    print(f'\n⚠️  Agencies without Telegram groups ({len(agencies_no_groups)}):')
    for name in agencies_no_groups:
        print(f'   - {name}')

if agencies_no_tasks:
    print(f'\n⚠️  Agencies without active tasks ({len(agencies_no_tasks)}):')
    for name in agencies_no_tasks:
        print(f'   - {name}')

# Check recent notification activity
print('\n' + '='*80)
print('RECENT ACTIVITY (Last 24 hours)')
print('='*80)

cutoff = timezone.now() - timedelta(hours=24)

# Check for available slots found
recent_available = CheckResult.objects.filter(
    check_time__gte=cutoff,
    status='available'
).select_related('task', 'task__agency')

print(f'\n🎫 Availability Events: {recent_available.count()}')

if recent_available.exists():
    print('\nRecent availability found:')
    for result in recent_available[:10]:  # Show first 10
        details = result.details or {}
        date = details.get('date', 'Unknown')
        ticket_name = details.get('ticket_name', 'Unknown')
        slots = details.get('slots', [])
        state_changed = details.get('state_changed', False)
        
        icon = '🔔' if state_changed else 'ℹ️'
        print(f'   {icon} {result.task.agency.name}: {ticket_name} on {date} ({len(slots)} slots)')
        if state_changed:
            print(f'      → Should have sent notification')
        else:
            print(f'      → No notification (no state change)')
else:
    print('   No availability found in last 24 hours')
    print('   This is normal if all monitored dates are sold out')

# Check Redis state
print('\n' + '='*80)
print('REDIS STATE CHECK')
print('='*80)

from django.core.cache import cache

# Sample a few tasks to check Redis state
sample_tasks = MonitorTask.objects.filter(is_active=True, site='vatican')[:5]

print('\nSample Redis state keys (first 5 tasks):')
for task in sample_tasks:
    if task.dates:
        date = task.dates[0] if isinstance(task.dates, list) else task.dates
        state_key = f"ticket_state:{task.id}:{date}"
        state = cache.get(state_key)
        
        if isinstance(state, bytes):
            state = state.decode('utf-8')
        
        state_display = state if state else 'NOT SET'
        print(f'   Task #{task.id} ({task.agency.name}): {date} → {state_display}')

print('\n' + '='*80)
print('NOTIFICATION LOGIC SUMMARY')
print('='*80)

print('''
📋 How Notifications Work:

1. MONITORING:
   - Bot checks Vatican API every 5 seconds
   - Checks all active tasks for all agencies

2. STATE TRACKING:
   - Redis stores state for each task+date combination
   - States: 'available' or 'closed'

3. NOTIFICATION TRIGGER:
   - Notification sent ONLY when state changes from 'closed' → 'available'
   - NOT sent on first check (baseline)
   - NOT sent if already available (no change)

4. TARGET GROUPS:
   - Gets all approved groups for the agency
   - Filters for notification_enabled=True
   - Sends to all matching groups

5. DEDUPLICATION:
   - Each group gets max 1 notification per date
   - Cooldown key: notified:{chat_id}:{date}
   - Prevents spam if multiple tasks monitor same date

✅ EXPECTED BEHAVIOR:
   - If tickets are already open: No notification (baseline)
   - If tickets open later: Notification sent to all enabled groups
   - If tickets stay open: No repeated notifications
   - If tickets close then reopen: New notification sent
''')

print('='*80)
print('RECOMMENDATIONS')
print('='*80)

if agencies_disabled_notif:
    print('\n⚠️  Enable notifications for these groups:')
    for agency_name in agencies_disabled_notif:
        agency = Agency.objects.get(name=agency_name)
        disabled = TelegramGroup.objects.filter(
            agency=agency,
            status='approved',
            notification_enabled=False
        )
        for group in disabled:
            name = getattr(group, 'group_name', None) or getattr(group, 'name', 'Unknown')
            print(f'   UPDATE telegram_groups SET notification_enabled = true WHERE id = {group.id}; -- {name}')

if agencies_no_groups:
    print('\n⚠️  Add Telegram groups for these agencies:')
    for name in agencies_no_groups:
        print(f'   - {name}: Add bot to Telegram group and approve via /pending')

if agencies_no_tasks:
    print('\n⚠️  Create monitoring tasks for these agencies:')
    for name in agencies_no_tasks:
        print(f'   - {name}: Create tasks via web interface or API')

if not (agencies_disabled_notif or agencies_no_groups or agencies_no_tasks):
    print('\n✅ All agencies are properly configured!')
    print('   Notifications will be sent when tickets become available.')

print('\n' + '='*80)
