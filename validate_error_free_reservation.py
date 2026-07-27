"""
Complete Error-Free Reservation Integration
===========================================
Integrates all components for zero-error Vatican reservations.

This script:
1. Tests the error-free reservation handler
2. Validates Cloudflare headers
3. Ensures proper Turnstile token format
4. Generates realistic participant names
5. Handles the complete session chain
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
from monitors.hold_manager_enhanced import complete_reservation_error_free, generate_epay_url_error_free
from monitors.turnstile_pool import get_token_sync, pool_size, _solve_one_token
from monitors.epay_ssl import make_vatican_session

logging.basicConfig(level=logging.INFO, encoding='utf-8')
logger = logging.getLogger(__name__)

# Set console encoding for Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def validate_implementation():
    """Validate that all components are properly integrated."""
    print("Validating Error-Free Reservation Implementation")
    print("=" * 60)
    
    # Check error-free reservation handler
    if not hasattr(error_free_reservation, 'complete_reservation'):
        print("❌ Error-free reservation handler not properly initialized")
        return False
    
    print("✅ Error-free reservation handler loaded")
    
    # Check enhanced hold manager
    try:
        from monitors.hold_manager_enhanced import complete_reservation_error_free
        print("✅ Enhanced hold manager loaded")
    except ImportError:
        print("❌ Enhanced hold manager not available")
        return False
    
    # Check Turnstile pool
    pool_count = pool_size()
    print(f"📊 Turnstile pool size: {pool_count}")
    
    if pool_count == 0:
        print("⚠️  Turnstile pool empty, will solve on demand")
    
    # Check for active agencies
    agencies = Agency.objects.filter(is_active=True)
    if not agencies.exists():
        print("❌ No active agencies found")
        return False
    
    print(f"✅ Found {agencies.count()} active agencies")
    
    # Check for buyer profiles
    profiles = BuyerProfile.objects.all()
    if not profiles.exists():
        print("⚠️  No buyer profiles found, will create test profile")
    else:
        print(f"✅ Found {profiles.count()} buyer profiles")
    
    return True

def create_test_setup():
    """Create test setup if needed."""
    print("\n[SETUP] Setting up test environment...")
    
    # Get or create test agency
    agency, created = Agency.objects.get_or_create(
        name="Test Agency",
        defaults={
            'api_key': 'test_key_123',
            'plan': 'pro',
            'is_active': True
        }
    )
    
    if created:
        print(f"✅ Created test agency: {agency.name}")
    else:
        print(f"✅ Using existing agency: {agency.name}")
    
    # Create buyer profile with realistic data
    profile, created = BuyerProfile.objects.get_or_create(
        agency=agency,
        defaults={
            'first_name': 'Mario',
            'last_name': 'Rossi',
            'email': 'mario.rossi@example.com',
            'phone': '+39 123 456 7890',
            'country': 'Italy',
            'city': 'Roma',
            'gender': 'M',
            'language': 'it'
        }
    )
    
    if created:
        print(f"✅ Created buyer profile: {profile.first_name} {profile.last_name}")
    else:
        print(f"✅ Using existing buyer profile: {profile.first_name} {profile.last_name}")
    
    # Set realistic participant names
    participant_names = [
        {"first_name": "Marco", "last_name": "Rossi"},
        {"first_name": "Luca", "last_name": "Bianchi"},
        {"first_name": "Giuseppe", "last_name": "Ferrari"}
    ]
    profile.participants_json = json.dumps(participant_names)
    profile.save()
    print(f"✅ Set {len(participant_names)} realistic participant names")
    
    return agency

def test_error_free_components():
    """Test individual components of the error-free system."""
    print("\n🧪 Testing Error-Free Components")
    print("=" * 60)
    
    # Test 1: Turnstile token validation
    print("1️⃣ Testing Turnstile token validation...")
    
    # Valid token format
    valid_token = "1." + "A" * 500
    result = error_free_reservation.validate_turnstile_token(valid_token)
    print(f"   Valid token (500+ chars): {result}")
    
    # Invalid tokens
    short_token = "1." + "A" * 100
    result = error_free_reservation.validate_turnstile_token(short_token)
    print(f"   Short token (100 chars): {result}")
    
    # Test 2: Cloudflare headers
    print("\n2️⃣ Testing Cloudflare header generation...")
    
    session = make_vatican_session()
    session.cookies.set('JSESSIONID', 'TEST123456789ABCDEF')
    error_free_reservation.session = session
    
    headers = error_free_reservation.get_cloudflare_headers()
    cf_chl = headers.get('cf-chl', '')
    cf_chl_ra = headers.get('cf-chl-ra', '')
    
    print(f"   cf-chl header: {cf_chl[:50]}... (length: {len(cf_chl)})")
    print(f"   cf-chl-ra header: {cf_chl_ra}")
    
    # Test 3: Participant name generation
    print("\n3️⃣ Testing participant name generation...")
    
    agency = Agency.objects.first()
    participants = error_free_reservation.generate_participant_names(3, agency)
    print(f"   Generated {len(participants)} participants:")
    for i, p in enumerate(participants):
        print(f"     {i+1}. {p['name']} {p['surname']}")
    
    # Test 4: Representative user generation
    print("\n4️⃣ Testing representative user generation...")
    
    representative = error_free_reservation.generate_representative_user(agency)
    print(f"   Representative: {representative['name']} {representative['surname']}")
    print(f"   Email: {representative['email']}")
    print(f"   Country: {representative['country']}")
    
    print("\n✅ All component tests completed")

def find_test_slot():
    """Find or create a test held slot."""
    print("\n🔍 Looking for test held slot...")
    
    # Look for existing held slots
    held_slots = HeldSlot.objects.filter(status='held').order_by('-created_at')
    
    if held_slots.exists():
        slot = held_slots.first()
        print(f"✅ Found existing held slot: {slot.slot_id}")
        print(f"   Date: {slot.date} {slot.slot_time}")
        print(f"   Visitors: {slot.visitors}")
        print(f"   Recap ID: {slot.recap_id}")
        return slot
    else:
        print("⚠️  No held slots found")
        print("💡 Create a held slot first using the hold manager")
        return None

def test_complete_reservation():
    """Test the complete reservation flow."""
    print("\n🚀 Testing Complete Reservation Flow")
    print("=" * 60)
    
    # Find test slot
    test_slot = find_test_slot()
    if not test_slot:
        return False
    
    print(f"\n🎯 Testing reservation with slot: {test_slot.slot_id}")
    
    # Test the complete reservation
    success, result = complete_reservation_error_free(test_slot)
    
    if success:
        print("✅ RESERVATION SUCCESS!")
        print(f"   Reference: {result['reference']}")
        print(f"   Epay URL: {result['epay_url'][:50]}...")
        print(f"   Total: €{result['total']}")
        
        # Test epay URL accessibility
        if result['epay_url']:
            print("\n🔗 Testing epay URL accessibility...")
            try:
                session = make_vatican_session()
                response = session.get(result['epay_url'], timeout=10)
                print(f"   Epay URL status: {response.status_code}")
                
                if response.status_code == 200:
                    print("   ✅ Epay URL is accessible")
                else:
                    print(f"   ⚠️  Epay URL returned {response.status_code}")
                    
            except Exception as e:
                print(f"   ⚠️  Epay URL test failed: {e}")
        
        return True
    else:
        print("❌ RESERVATION FAILED")
        print(f"   Error: {result.get('error', 'Unknown error')}")
        
        # Analyze failure
        if result.get('status_code') == 500:
            print("\n🔍 Analyzing 500 error...")
            print("   Possible causes:")
            print("   - Session expired (need re-hold)")
            print("   - Slot sold out between hold and reservation")
            print("   - Turnstile token invalid")
            print("   - Missing Cloudflare headers")
            
            # Check session freshness
            if not test_slot.is_session_fresh():
                print("   ⚠️  Session appears stale")
        
        return False

def main():
    """Run complete validation and testing."""
    print("🚀 Starting Complete Error-Free Reservation Test")
    print("=" * 60)
    
    # Step 1: Validate implementation
    if not validate_implementation():
        print("❌ Implementation validation failed")
        return False
    
    # Step 2: Setup test environment
    agency = create_test_setup()
    
    # Step 3: Test components
    test_error_free_components()
    
    # Step 4: Test complete flow
    success = test_complete_reservation()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 ALL TESTS PASSED!")
        print("✅ Error-free reservation implementation is working")
    else:
        print("❌ SOME TESTS FAILED")
        print("🔧 Check the logs above for details")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)