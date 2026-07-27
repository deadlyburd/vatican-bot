#!/usr/bin/env python3
"""
Find missing Telegram groups (Big Bus, MV2, etc.)
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import TelegramGroup, Agency
from django.db import connection

print("=" * 80)
print("SEARCHING FOR MISSING TELEGRAM GROUPS")
print("=" * 80)
print()

# Search for groups with "big bus" or "mv2" in name
print("🔍 Searching for 'Big Bus' groups...")
big_bus_groups = TelegramGroup.objects.filter(chat_title__icontains='big bus')
print(f"   Found: {big_bus_groups.count()}")
for g in big_bus_groups:
    print(f"   - {g.chat_title} ({g.chat_id}) - Status: {g.status}")
print()

print("🔍 Searching for 'MV2' groups...")
mv2_groups = TelegramGroup.objects.filter(chat_title__icontains='mv2')
print(f"   Found: {mv2_groups.count()}")
for g in mv2_groups:
    print(f"   - {g.chat_title} ({g.chat_id}) - Status: {g.status}")
print()

print("🔍 Searching for 'MV' groups...")
mv_groups = TelegramGroup.objects.filter(chat_title__icontains='mv')
print(f"   Found: {mv_groups.count()}")
for g in mv_groups:
    print(f"   - {g.chat_title} ({g.chat_id}) - Status: {g.status}")
print()

print("🔍 Searching for 'bus' groups...")
bus_groups = TelegramGroup.objects.filter(chat_title__icontains='bus')
print(f"   Found: {bus_groups.count()}")
for g in bus_groups:
    print(f"   - {g.chat_title} ({g.chat_id}) - Status: {g.status}")
print()

# Check if Big Bus agency exists
print("=" * 80)
print("CHECKING FOR 'BIG BUS' AGENCY")
print("=" * 80)
print()

big_bus_agency = Agency.objects.filter(name__icontains='big bus')
if big_bus_agency.exists():
    for agency in big_bus_agency:
        print(f"✅ Found agency: {agency.name} (ID: {agency.id})")
        groups = TelegramGroup.objects.filter(agency=agency)
        print(f"   Telegram groups: {groups.count()}")
        for g in groups:
            print(f"   - {g.chat_title} ({g.chat_id}) - {g.status}")
else:
    print("❌ No 'Big Bus' agency found")
print()

# Show ALL groups regardless of status
print("=" * 80)
print("ALL TELEGRAM GROUPS (Including Deleted/Rejected)")
print("=" * 80)
print()

all_groups = TelegramGroup.objects.all().order_by('-created_at')
print(f"Total: {all_groups.count()} groups\n")

for g in all_groups:
    status_icon = {
        'approved': '✅',
        'pending': '⏳',
        'rejected': '❌'
    }.get(g.status, '❓')
    
    print(f"{status_icon} {g.chat_title or 'Unknown'}")
    print(f"   Chat ID: {g.chat_id}")
    print(f"   Status: {g.status}")
    print(f"   Agency: {g.agency.name if g.agency else 'None'}")
    print(f"   Created: {g.created_at.strftime('%Y-%m-%d %H:%M')}")
    print()

# Check database directly for any deleted records
print("=" * 80)
print("RAW DATABASE CHECK")
print("=" * 80)
print()

with connection.cursor() as cursor:
    cursor.execute("SELECT COUNT(*) FROM monitors_telegramgroup")
    total = cursor.fetchone()[0]
    print(f"Total records in monitors_telegramgroup table: {total}")
    
    cursor.execute("""
        SELECT id, chat_id, chat_title, status, agency_id, created_at 
        FROM monitors_telegramgroup 
        ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    
    print("\nAll records:")
    for row in rows:
        print(f"  ID: {row[0]}, Chat: {row[1]}, Title: {row[2]}, Status: {row[3]}, Agency: {row[4]}, Created: {row[5]}")

print()
print("=" * 80)
print("POSSIBLE REASONS FOR MISSING GROUPS")
print("=" * 80)
print()
print("1. Groups were never added to the bot")
print("2. Groups were rejected by admin")
print("3. Bot was removed from the groups")
print("4. Groups are in a different database")
print("5. Groups were deleted from database")
print()
print("To add groups:")
print("  1. Add bot to Telegram group")
print("  2. Admin sends /pending to see pending groups")
print("  3. Admin approves the group")
print()
