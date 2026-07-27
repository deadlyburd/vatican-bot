#!/usr/bin/env python3
"""
Enable Notifications for All Approved Groups
=============================================
Enables notification_enabled=True for all approved Telegram groups.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import TelegramGroup

print('='*80)
print('ENABLE NOTIFICATIONS FOR ALL APPROVED GROUPS')
print('='*80)

# Get all approved groups with notifications disabled
disabled_groups = TelegramGroup.objects.filter(
    status='approved',
    notification_enabled=False
).select_related('agency')

if not disabled_groups.exists():
    print('\n✅ All approved groups already have notifications enabled!')
    print('   Nothing to do.')
else:
    print(f'\nFound {disabled_groups.count()} approved groups with notifications disabled:')
    print()
    
    for group in disabled_groups:
        name = getattr(group, 'group_name', None) or getattr(group, 'name', 'Unknown')
        print(f'   - {name} ({group.chat_id}) - Agency: {group.agency.name}')
    
    print('\n' + '='*80)
    response = input('Enable notifications for all these groups? (yes/no): ')
    
    if response.lower() in ['yes', 'y']:
        count = disabled_groups.update(notification_enabled=True)
        print(f'\n✅ Enabled notifications for {count} groups!')
        print('\nGroups updated:')
        
        # Show updated groups
        for group in disabled_groups:
            name = getattr(group, 'group_name', None) or getattr(group, 'name', 'Unknown')
            print(f'   ✅ {name} ({group.chat_id})')
        
        print('\n' + '='*80)
        print('NEXT STEPS')
        print('='*80)
        print('\n1. Verify notifications are enabled:')
        print('   docker-compose exec backend python backend/check_notification_status.py')
        print('\n2. Monitor for notifications:')
        print('   docker-compose logs -f worker_vatican | grep "TELEGRAM ALERT"')
        print('\n3. Wait for tickets to become available')
        print('   Notifications will be sent automatically when state changes')
        print()
    else:
        print('\n❌ Cancelled - no changes made')

print('='*80)
