#!/usr/bin/env python3
"""
Direct trigger for August 13, 2026 17:00 booking
Adds the slot directly to the database for extension to pick up
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from backend.models import AvailableSlot
from datetime import datetime

print("=" * 60)
print("🎯 TRIGGERING AUGUST 13, 2026 17:00 BOOKING")
print("=" * 60)
print()

# Slot data for August 13, 2026 at 17:00
slot_data = {
    'date': '13/08/2026',
    'time': '17:00',
    'ticket_id': '2129030053',  # Will be resolved dynamically by extension
    'ticket_name': 'Musei Vaticani - Biglietti d\'ingresso',
    'visitors': 1,
    'adult_count': 1,
    'child_count': 0,
    'language': '',  # Empty for standard ticket
    'profile': {
        'first_name': 'Mario',
        'last_name': 'Rossi',
        'email': 'mario.rossi@example.com',
        'phone': '+39 123 456 7890',
        'country': 'IT'
    },
    'participants': [
        {
            'first_name': 'Mario',
            'last_name': 'Rossi',
            'email': 'mario.rossi@example.com'
        }
    ],
    'card': {
        'number': '4111111111111111',
        'expiry': '12/28',
        'cvv': '123',
        'holder': 'MARIO ROSSI'
    }
}

# Check if slot already exists
existing = AvailableSlot.objects.filter(
    date='13/08/2026',
    time='17:00',
    status='available'
).first()

if existing:
    print(f"✅ Slot already exists in database:")
    print(f"   ID: {existing.id}")
    print(f"   Date: {existing.date} {existing.time}")
    print(f"   Visitors: {existing.visitors}")
    print(f"   Status: {existing.status}")
    print()
    print("🔄 Updating slot to ensure it's fresh...")
    
    # Update the slot
    existing.ticket_id = slot_data['ticket_id']
    existing.ticket_name = slot_data['ticket_name']
    existing.profile = slot_data['profile']
    existing.participants = slot_data['participants']
    existing.card = slot_data['card']
    existing.status = 'available'
    existing.save()
    
    slot = existing
    print("✅ Slot updated!")
else:
    # Create new slot
    print("📝 Creating new slot in database...")
    slot = AvailableSlot.objects.create(
        date=slot_data['date'],
        time=slot_data['time'],
        ticket_id=slot_data['ticket_id'],
        ticket_name=slot_data['ticket_name'],
        visitors=slot_data['visitors'],
        adult_count=slot_data['adult_count'],
        child_count=slot_data['child_count'],
        language=slot_data['language'],
        profile=slot_data['profile'],
        participants=slot_data['participants'],
        card=slot_data['card'],
        status='available'
    )
    print(f"✅ Created new slot: {slot.id}")

print()
print("=" * 60)
print("📋 SLOT DETAILS")
print("=" * 60)
print(f"Slot ID: {slot.id}")
print(f"Date: {slot.date}")
print(f"Time: {slot.time}")
print(f"Ticket: {slot.ticket_name}")
print(f"Visitors: {slot.visitors}")
print(f"Participant: {slot.participants[0]['first_name']} {slot.participants[0]['last_name']}")
print(f"Email: {slot.profile['email']}")
print(f"Status: {slot.status}")
print()
print("=" * 60)
print("🚀 SLOT IS READY!")
print("=" * 60)
print()
print("The extension will pick this up within 10 seconds and:")
print("1. Open a regular Chrome window")
print("2. Navigate to Vatican booking page")
print("3. Auto-fill the form with Mario Rossi's details")
print("4. Proceed through checkout")
print("5. Complete the booking")
print()
print("👀 Watch your Chrome window for the booking to start!")
print()
