#!/usr/bin/env python3
"""
Comprehensive Bot Health Check
===============================
Verifies all components are working correctly.
"""

import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import Agency, TelegramGroup, MonitorTask, CheckResult
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
import redis
from django.conf import settings

print('='*80)
print('BOT HEALTH CHECK')
print('='*80)

all_checks_passed = True

# CHECK 1: Database Connection
print('\n1️⃣  DATABASE CONNECTION')
print('-'*80)
try:
    agency_count = Agency.objects.count()
    print(f'✅ Database connected')
    print(f'   Agencies: {agency_count}')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    all_checks_passed = False

# CHECK 2: Redis Connection
print('\n2️⃣  REDIS CONNECTION')
print('-'*80)
try:
    broker_url = settings.CELERY_BROKER_URL
    r = redis.from_url(broker_url)
    r.ping()
    
    key_count = r.dbsize()
    memory_info = r.info('memory')
    memory_used = memory_info['used_memory_human']
    
    print(f'✅ Redis connected')
    print(f'   Keys: {key_count:,}')
    print(f'   Memory: {memory_used}')
    
    if key_count > 50000:
        print(f'   ⚠️  WARNING: High key count ({key_count:,})')
        print(f'   Run: run_redis_fix.bat')
        all_checks_passed = False
    elif key_count > 20000:
        print(f'   ⚠️  Key count getting high ({key_count:,})')
    else:
        print(f'   ✅ Key count healthy')
        
except Exception as e:
    print(f'❌ Redis connection failed: {e}')
    all_checks_passed = False

# CHECK 3: Agency Configuration
print('\n3️⃣  AGENCY CONFIGURATION')
print('-'*80)
agencies = Agency.objects.all()
configured_count = 0
total_tasks = 0
total_groups = 0

for agency in agencies:
    tasks = MonitorTask.objects.filter(agency=agency, is_active=True)
    groups = TelegramGroup.objects.filter(agency=agency, status='approved', notification_enabled=True)
    
    total_tasks += tasks.count()
    total_groups += groups.count()
    
    if tasks.exists() and groups.exists():
        configured_count += 1
        print(f'✅ {agency.name}: {tasks.count()} tasks, {groups.count()} groups')
    else:
        print(f'⚠️  {agency.name}: {tasks.count()} tasks, {groups.count()} groups')
        all_checks_passed = False

print(f'\nSummary:')
print(f'   Total Agencies: {agencies.count()}')
print(f'   Configured: {configured_count}/{agencies.count()}')
print(f'   Total Active Tasks: {total_tasks}')
print(f'   Total Enabled Groups: {total_groups}')

if configured_count == agencies.count():
    print(f'   ✅ All agencies configured')
else:
    print(f'   ⚠️  {agencies.count() - configured_count} agencies need configuration')

# CHECK 4: Recent Activity
print('\n4️⃣  RECENT ACTIVITY (Last 5 minutes)')
print('-'*80)
cutoff = timezone.now() - timedelta(minutes=5)

recent_checks = CheckResult.objects.filter(check_time__gte=cutoff)
recent_count = recent_checks.count()

if recent_count > 0:
    print(f'✅ Bot is active')
    print(f'   Checks in last 5 min: {recent_count}')
    
    # Show latest check
    latest = recent_checks.order_by('-check_time').first()
    if latest:
        time_ago = (timezone.now() - latest.check_time).total_seconds()
        print(f'   Latest check: {int(time_ago)}s ago')
        print(f'   Task: {latest.task.ticket_name}')
        print(f'   Status: {latest.status}')
else:
    print(f'⚠️  No recent activity')
    print(f'   No checks in last 5 minutes')
    print(f'   Bot may not be running')
    all_checks_passed = False

# CHECK 5: Task Distribution
print('\n5️⃣  TASK DISTRIBUTION')
print('-'*80)
active_tasks = MonitorTask.objects.filter(is_active=True, site='vatican')

if active_tasks.exists():
    print(f'✅ Active tasks found: {active_tasks.count()}')
    
    # Group by agency
    from django.db.models import Count
    by_agency = active_tasks.values('agency__name').annotate(count=Count('id')).order_by('-count')
    
    print(f'\nTasks by agency:')
    for item in by_agency:
        print(f'   {item["agency__name"]}: {item["count"]} tasks')
else:
    print(f'❌ No active tasks found')
    all_checks_passed = False

# CHECK 6: Celery Settings
print('\n6️⃣  CELERY CONFIGURATION')
print('-'*80)
try:
    result_expires = getattr(settings, 'CELERY_RESULT_EXPIRES', None)
    ignore_result = getattr(settings, 'CELERY_TASK_IGNORE_RESULT', None)
    
    if result_expires:
        print(f'✅ CELERY_RESULT_EXPIRES: {result_expires}s ({result_expires//3600}h)')
    else:
        print(f'⚠️  CELERY_RESULT_EXPIRES not set')
        all_checks_passed = False
    
    if ignore_result is not None:
        print(f'✅ CELERY_TASK_IGNORE_RESULT: {ignore_result}')
    else:
        print(f'⚠️  CELERY_TASK_IGNORE_RESULT not set')
        all_checks_passed = False
        
    # Check beat schedule
    beat_schedule = getattr(settings, 'CELERY_BEAT_SCHEDULE', {})
    important_tasks = [
        'vatican-monitor-orchestrator',
        'instant-sniper-scan',
        'cleanup-redis-cache'
    ]
    
    print(f'\nScheduled tasks:')
    for task_name in important_tasks:
        if task_name in beat_schedule:
            schedule = beat_schedule[task_name].get('schedule', 'unknown')
            print(f'   ✅ {task_name}: every {schedule}s')
        else:
            print(f'   ⚠️  {task_name}: NOT SCHEDULED')
            all_checks_passed = False
            
except Exception as e:
    print(f'❌ Error checking Celery config: {e}')
    all_checks_passed = False

# CHECK 7: Redis State Keys
print('\n7️⃣  REDIS STATE KEYS')
print('-'*80)
try:
    # Sample a few tasks
    sample_tasks = MonitorTask.objects.filter(is_active=True, site='vatican')[:3]
    
    if sample_tasks.exists():
        print(f'Checking state keys for {sample_tasks.count()} sample tasks:')
        
        for task in sample_tasks:
            if task.dates:
                date = task.dates[0] if isinstance(task.dates, list) else task.dates
                state_key = f"ticket_state:{task.id}:{date}"
                
                try:
                    state = cache.get(state_key)
                    if isinstance(state, bytes):
                        state = state.decode('utf-8')
                    
                    if state:
                        print(f'   ✅ Task #{task.id} ({date}): {state}')
                    else:
                        print(f'   ⚠️  Task #{task.id} ({date}): NOT SET')
                except Exception as e:
                    print(f'   ⚠️  Task #{task.id} ({date}): Error - {e}')
    else:
        print(f'⚠️  No active tasks to check')
        
except Exception as e:
    print(f'⚠️  Error checking state keys: {e}')

# CHECK 8: Notification Settings
print('\n8️⃣  NOTIFICATION SETTINGS')
print('-'*80)
enabled_groups = TelegramGroup.objects.filter(status='approved', notification_enabled=True)
disabled_groups = TelegramGroup.objects.filter(status='approved', notification_enabled=False)

print(f'Enabled groups: {enabled_groups.count()}')
print(f'Disabled groups: {disabled_groups.count()}')

if enabled_groups.exists():
    print(f'\n✅ Notifications enabled for:')
    for group in enabled_groups:
        print(f'   - {group.agency.name} ({group.chat_id})')
else:
    print(f'\n❌ No groups have notifications enabled')
    all_checks_passed = False

if disabled_groups.exists():
    print(f'\n⚠️  Notifications disabled for:')
    for group in disabled_groups:
        print(f'   - {group.agency.name} ({group.chat_id})')

# FINAL SUMMARY
print('\n' + '='*80)
print('HEALTH CHECK SUMMARY')
print('='*80)

if all_checks_passed:
    print('\n✅ ALL CHECKS PASSED')
    print('\nBot is working correctly:')
    print('   ✅ Database connected')
    print('   ✅ Redis connected and healthy')
    print('   ✅ All agencies configured')
    print('   ✅ Bot is actively checking')
    print('   ✅ Tasks are running')
    print('   ✅ Celery configured correctly')
    print('   ✅ Notifications enabled')
    print('\n🎉 Bot is ready to send notifications!')
else:
    print('\n⚠️  SOME CHECKS FAILED')
    print('\nPlease review the issues above and fix them.')
    print('\nCommon fixes:')
    print('   - Redis bloat: run_redis_fix.bat')
    print('   - No activity: docker-compose restart worker_vatican beat')
    print('   - Missing config: Check backend/core/settings.py')

print('\n' + '='*80)
print('MONITORING COMMANDS')
print('='*80)
print('\nWatch for activity:')
print('   docker-compose logs -f worker_vatican | grep ORCHESTRATOR')
print('\nWatch for notifications:')
print('   docker-compose logs -f worker_vatican | grep "TELEGRAM ALERT"')
print('\nCheck Redis health:')
print('   docker-compose exec redis redis-cli DBSIZE')
print('\nRestart services:')
print('   docker-compose restart worker_vatican beat')
print()

sys.exit(0 if all_checks_passed else 1)
