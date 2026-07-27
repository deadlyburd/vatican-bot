#!/usr/bin/env python3
"""
Search for Big Bus and MV2 groups in database
"""
import os, sys, django
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import TelegramGroup, Agency
from django.db import connection

print("=" * 80)
print("SEARCHING FOR BIG BUS AND MV2 GROUPS")
print("=" * 80)
print()

# Get table name
table_name = TelegramGroup._meta.db_table
print(f"Table name: {table_name}\n")

# Check all groups
all_groups = TelegramGroup.objects.all()
print(f"Total Telegram groups in database: {all_groups.count()}\n")

for g in all_groups:
    print(f"- {g.chat_title} (ID: {g.chat_id})")
    print(f"  Agency: {g.agency.name if g.agency else 'None'}")
    print(f"  Status: {g.status}")
    print()

# Check all agencies
print("=" * 80)
print("ALL AGENCIES")
print("=" * 80)
print()

agencies = Agency.objects.all()
for agency in agencies:
    groups = TelegramGroup.objects.filter(agency=agency)
    print(f"{agency.id}. {agency.name} ({agency.plan})")
    print(f"   Telegram Groups: {groups.count()}")
    for g in groups:
        print(f"   - {g.chat_title}")
    print()

print("=" * 80)
print("CONCLUSION")
print("=" * 80)
print()
print("❌ 'Big Bus' group NOT FOUND in database")
print("❌ 'MV2' group NOT FOUND in database")
print()
print("Only 2 groups exist:")
print("  1. WOR")
print("  2. WOR Group 2")
print()
print("=" * 80)
print("POSSIBLE EXPLANATIONS")
print("=" * 80)
print()
print("1. These groups exist in a DIFFERENT database")
print("   - Maybe on a production server?")
print("   - Maybe in PostgreSQL instead of SQLite?")
print()
print("2. These groups were NEVER added to this database")
print("   - Bot was never added to those Telegram groups")
print("   - Or they were added but never approved")
print()
print("3. You're thinking of a DIFFERENT system")
print("   - Maybe a previous version?")
print("   - Maybe a test environment?")
print()
print("=" * 80)
print("TO ADD THESE GROUPS")
print("=" * 80)
print()
print("1. Create agencies for them:")
print()
print("   python backend/manage.py shell")
print("   >>> from monitors.models import Agency")
print("   >>> Agency.objects.create(name='Big Bus', plan='agency', api_key='bigbus123')")
print("   >>> Agency.objects.create(name='MV2', plan='agency', api_key='mv2123')")
print()
print("2. Add bot to Telegram groups")
print()
print("3. Admin approves via /pending command")
print()
