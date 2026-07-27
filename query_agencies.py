#!/usr/bin/env python3
import os, sys, django
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import Agency, User
from django.conf import settings

print("=" * 80)
print("DATABASE LOCATION")
print("=" * 80)
print(f"Database: {settings.DATABASES['default']}")
print()

print("=" * 80)
print("ALL AGENCIES IN DATABASE")
print("=" * 80)

agencies = Agency.objects.all().order_by('id')
print(f"\nTotal: {agencies.count()} agencies\n")

for agency in agencies:
    users = User.objects.filter(agency=agency)
    print(f"ID: {agency.id:2d} | Name: {agency.name:30s} | Plan: {agency.plan:8s} | Users: {users.count()}")
    for user in users:
        print(f"           └─ {user.username}")

print()
print("=" * 80)
print("WHERE DID YOU SEE IDs 3-14?")
print("=" * 80)
print()
print("If you saw agencies with IDs 3-14, they might be from:")
print("1. A different database file")
print("2. A PostgreSQL/MySQL database (not SQLite)")
print("3. A backup/old database")
print("4. The Telegram bot's internal data")
print()
print("Please share:")
print("- Where did you run the query that showed IDs 3-14?")
print("- What command did you use?")
print("- Are you using PostgreSQL or MySQL instead of SQLite?")
print()
