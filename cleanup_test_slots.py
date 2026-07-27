#!/usr/bin/env python3
"""Delete old test slots"""
import os, sys, django
sys.path.insert(0, '/app/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import HeldSlot
# Delete all TEST slots (both old format and new format)
count = HeldSlot.objects.filter(slot_id__startswith='TEST').delete()[0]
print(f'Deleted {count} test slots')
