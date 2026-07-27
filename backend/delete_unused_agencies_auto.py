#!/usr/bin/env python3
"""
Delete Unused Agencies - Automatic
===================================
Automatically deletes agencies without proper Telegram configuration.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import Agency, TelegramGroup, MonitorTask, User, CheckResult, HeldSlot
from django.db import transaction

print('='*80)
print('DELETE UNUSED AGENCIES - AUTOMATIC')
print('='*80)

# Agencies to delete
agencies_to_delete = [
    'Italy pass',
    'Vatican Bot Agency 2',
    'System Admin',
    'Agency-admin',
    'Wondersofrome'
]

print('\nAgencies marked for deletion:')
for name in agencies_to_delete:
    print(f'   - {name}')

print('\n' + '='*80)
print('CHECKING WHAT WILL BE DELETED')
print('='*80)

total_tasks = 0
total_users = 0
total_groups = 0
total_check_results = 0
total_held_slots = 0

for agency_name in agencies_to_delete:
    try:
        agency = Agency.objects.get(name=agency_name)
        
        tasks = MonitorTask.objects.filter(agency=agency)
        users = User.objects.filter(agency=agency)
        groups = TelegramGroup.objects.filter(agency=agency)
        check_results = CheckResult.objects.filter(task__agency=agency)
        held_slots = HeldSlot.objects.filter(task__agency=agency)
        
        print(f'\n📋 {agency_name} (ID: {agency.id}):')
        print(f'   Tasks: {tasks.count()}')
        print(f'   Users: {users.count()}')
        print(f'   Groups: {groups.count()}')
        print(f'   Check Results: {check_results.count()}')
        print(f'   Held Slots: {held_slots.count()}')
        
        total_tasks += tasks.count()
        total_users += users.count()
        total_groups += groups.count()
        total_check_results += check_results.count()
        total_held_slots += held_slots.count()
            
    except Agency.DoesNotExist:
        print(f'\n⚠️  {agency_name}: Not found (already deleted?)')

print('\n' + '='*80)
print('SUMMARY')
print('='*80)
print(f'\nTotal to delete:')
print(f'   Agencies: {len(agencies_to_delete)}')
print(f'   Tasks: {total_tasks}')
print(f'   Users: {total_users}')
print(f'   Groups: {total_groups}')
print(f'   Check Results: {total_check_results}')
print(f'   Held Slots: {total_held_slots}')

print('\n🗑️  Starting deletion...')

deleted_count = 0
deleted_tasks = 0
deleted_users = 0
deleted_groups = 0

with transaction.atomic():
    for agency_name in agencies_to_delete:
        try:
            agency = Agency.objects.get(name=agency_name)
            
            # Get counts before deletion
            task_count = MonitorTask.objects.filter(agency=agency).count()
            user_count = User.objects.filter(agency=agency).count()
            group_count = TelegramGroup.objects.filter(agency=agency).count()
            
            # Delete the agency (cascade will delete related objects)
            agency.delete()
            
            print(f'   ✅ Deleted {agency_name}:')
            print(f'      - {task_count} tasks')
            print(f'      - {user_count} users')
            print(f'      - {group_count} groups')
            
            deleted_count += 1
            deleted_tasks += task_count
            deleted_users += user_count
            deleted_groups += group_count
            
        except Agency.DoesNotExist:
            print(f'   ⚠️  {agency_name}: Not found (skipped)')
        except Exception as e:
            print(f'   ❌ Error deleting {agency_name}: {e}')
            import traceback
            traceback.print_exc()

print('\n' + '='*80)
print('DELETION COMPLETE')
print('='*80)
print(f'\n✅ Successfully deleted {deleted_count} agencies')
print(f'   Tasks deleted: {deleted_tasks}')
print(f'   Users deleted: {deleted_users}')
print(f'   Groups deleted: {deleted_groups}')

print('\n📊 Remaining agencies:')
remaining = Agency.objects.all().order_by('name')
for agency in remaining:
    task_count = MonitorTask.objects.filter(agency=agency, is_active=True).count()
    group_count = TelegramGroup.objects.filter(agency=agency, status='approved', notification_enabled=True).count()
    print(f'   - {agency.name}: {task_count} tasks, {group_count} enabled groups')

print('\n' + '='*80)
print('✅ CLEANUP COMPLETE')
print('='*80)
print('\nNext steps:')
print('1. Verify remaining agencies:')
print('   docker-compose exec backend python backend/check_notification_status.py')
print('\n2. All remaining agencies should now have proper Telegram configuration')
print()
