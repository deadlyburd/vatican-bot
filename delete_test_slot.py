#!/usr/bin/env python3
"""
Delete test held slots created for extension testing.

Usage:
    docker-compose exec backend python /app/delete_test_slot.py
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/app/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import HeldSlot

def delete_test_slots():
    """Delete all test held slots."""
    
    print("🗑️  Deleting test held slots...")
    print("=" * 60)
    
    # Delete test slots (slot_id starts with TEST)
    test_slots = HeldSlot.objects.filter(slot_id__startswith='TEST')
    count = test_slots.count()
    
    if count == 0:
        print("ℹ️  No test slots found")
        return
    
    # Show what will be deleted
    print(f"Found {count} test slot(s):")
    for slot in test_slots:
        print(f"  - ID {slot.id}: {slot.date} {slot.slot_time} ({slot.status})")
    
    # Delete
    deleted = test_slots.delete()[0]
    
    print("=" * 60)
    print(f"✅ Deleted {deleted} test slot(s)")
    print("=" * 60)

def main():
    try:
        delete_test_slots()
        sys.exit(0)
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
