#!/usr/bin/env python3
"""
Delete Unused Agencies
======================
Safely deletes agencies that don't have proper Telegram group configuration.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import Agency, TelegramGroup, MonitorTask, User
from django.db import transaction

print('='*80)
print('DELETE UNUSED AGENCIES')
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

for agency_name in agencies_to_delete:
    try:
        agency = Agency.objects.get(name=agency_name)
        
        tasks = MonitorTask.objects.filter(agency=agency)
        users = User.objects.filter(agency=agency)
        groups = TelegramGroup.objects.filter(agency=agency)
        
        print(f'\n📋 {agency_name} (ID: {agency.id}):')
        print(f'   Tasks: {tasks.count()}')
        print(f'   Users: {users.count()}')
        print(f'   Groups: {groups.count()}')
        
        total_tasks += tasks.count()
        total_users += users.count()
        total_groups += groups.count()
        
        if tasks.exists():
            print(f'   Task IDs: {list(tasks.values_list("id", flat=True))}')
        if users.exists():
            print(f'   Users: {list(users.values_list("username", flat=True))}')
        if groups.exists():
            print(f'   Groups: {list(groups.values_list("chat_id", flat=True))}')
            
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

print('\n⚠️  WARNING: This will permanently delete:')
print('   - All monitoring tasks for these agencies')
print('   - All users belonging to these agencies')
print('   - All Telegram groups for these agencies')
print('   - All check results and history')
print('   - The agencies themselves')

print('\n' + '='*80)
response = input('Are you sure you want to delete these agencies? (type "DELETE" to confirm): ')

if response == 'DELETE':
    print('\n🗑️  Deleting agencies...')
    
    deleted_count = 0
    
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
                
            except Agency.DoesNotExist:
                print(f'   ⚠️  {agency_name}: Not found (skipped)')
            except Exception as e:
                print(f'   ❌ Error deleting {agency_name}: {e}')
    
    print('\n' + '='*80)
    print('DELETION COMPLETE')
    print('='*80)
    print(f'\n✅ Successfully deleted {deleted_count} agencies')
    print(f'   Total tasks deleted: {total_tasks}')
    print(f'   Total users deleted: {total_users}')
    print(f'   Total groups deleted: {total_groups}')
    
    print('\n📊 Remaining agencies:')
    remaining = Agency.objects.exclude(plan='system').order_by('name')
    for agency in remaining:
        task_count = MonitorTask.objects.filter(agency=agency, is_active=True).count()
        group_count = TelegramGroup.objects.filter(agency=agency, status='approved', notification_enabled=True).count()
        print(f'   - {agency.name}: {task_count} tasks, {group_count} enabled groups')
    
else:
    print('\n❌ Cancelled - no changes made')

print('\n' + '='*80)
