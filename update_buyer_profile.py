#!/usr/bin/env python3
"""Update buyer profile with correct phone format"""
import os, sys, django
sys.path.insert(0, '/app/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import BuyerProfile
import json

# Update all buyer profiles
profiles = BuyerProfile.objects.filter(first_name='John', last_name='Doe')
for profile in profiles:
    profile.phone = '+393331234567'  # Italian format
    profile.participants_json = json.dumps([
        {"first_name": "John", "last_name": "Doe"},
        {"first_name": "Jane", "last_name": "Doe"}
    ])
    profile.save()
    print(f'Updated profile {profile.id}: phone={profile.phone}')

print(f'Updated {profiles.count()} profiles')
