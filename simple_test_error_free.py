"""
Simple Error-Free Reservation Test
================================
Tests the error-free reservation implementation without Unicode issues.
"""
import os
import sys
import django
import time
import json
import logging
from datetime import datetime, timedelta

# Setup Django
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import HeldSlot, MonitorTask, Agency, BuyerProfile
from monitors.error_free_reservation import error_free_reservation
from monitors.turnstile_pool import get_token_sync, pool_size

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def simple_test():
    """Simple test of error-free reservation components."""
    print("Testing Error-Free Reservation Implementation")
    print("=" * 60)
    
    # Check error-free reservation handler
    if not hasattr(error_free_reservation, 'complete_reservation'):
        print("ERROR: Error-free reservation handler not properly initialized")
        return False
    
    print("OK: Error-free reservation handler loaded")
    
    # Check Turnstile pool
    pool_count = pool_size()
    print(f"Turnstile pool size: {pool_count}")
    
    # Check for active agencies
    agencies = Agency.objects.filter(is_active=True)
    if not agencies.exists():
        print("ERROR: No active agencies found")
        return False
    
    print(f"OK: Found {agencies.count()} active agencies")
    
    # Test Turnstile token validation
    print("\nTesting Turnstile token validation...")
    
    # Valid token format
    valid_token = "1." + "A" * 500
    result = error_free_reservation.validate_turnstile_token(valid_token)
    print(f"Valid token (500+ chars): {result}")
    
    # Invalid tokens
    short_token = "1." + "A" * 100
    result = error_free_reservation.validate_turnstile_token(short_token)
    print(f"Short token (100 chars): {result}")
    
    # Test participant name generation
    print("\nTesting participant name generation...")
    
    agency = agencies.first()
    participants = error_free_reservation.generate_participant_names(3, agency)
    print(f"Generated {len(participants)} participants:")
    for i, p in enumerate(participants):
        print(f"  {i+1}. {p['name']} {p['surname']}")
    
    # Test representative user generation
    print("\nTesting representative user generation...")
    
    representative = error_free_reservation.generate_representative_user(agency)
    print(f"Representative: {representative['name']} {representative['surname']}")
    print(f"Email: {representative['email']}")
    print(f"Country: {representative['country']}")
    
    # Find test slot
    print("\nLooking for test held slot...")
    
    held_slots = HeldSlot.objects.filter(status='held').order_by('-created_at')
    
    if held_slots.exists():
        slot = held_slots.first()
        print(f"OK: Found existing held slot: {slot.slot_id}")
        print(f"  Date: {slot.date} {slot.slot_time}")
        print(f"  Visitors: {slot.visitors}")
        print(f"  Recap ID: {slot.recap_id}")
        
        print("\nTesting complete reservation...")
        success, result = error_free_reservation.complete_reservation(slot)
        
        if success:
            print("SUCCESS: Reservation completed!")
            print(f"  Reference: {result['reference']}")
            print(f"  Epay URL: {result['epay_url'][:50]}...")
            print(f"  Total: €{result['total']}")
            return True
        else:
            print("FAILED: Reservation failed")
            print(f"  Error: {result.get('error', 'Unknown error')}")
            return False
    else:
        print("WARNING: No held slots found")
        print("Create a held slot first using the hold manager")
        return False

if __name__ == "__main__":
    print("Starting Simple Error-Free Reservation Test")
    print("=" * 60)
    
    success = simple_test()
    
    print("\n" + "=" * 60)
    if success:
        print("SUCCESS: All tests passed!")
    else:
        print("FAILED: Some tests failed - check logs above")
    
    sys.exit(0 if success else 1)