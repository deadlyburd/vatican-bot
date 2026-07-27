"""
Test Error-Free Reservation Implementation
==========================================
Tests the comprehensive reservation handler with all fixes applied:
1. Cloudflare headers (cf-chl, cf-chl-ra)
2. Proper Turnstile token format (~500+ characters)
3. Realistic participant names (no blanks)
4. Proper session chain flow
"""
import os
import sys
import django
import time
import json
from datetime import datetime, timedelta

# Setup Django
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import HeldSlot, MonitorTask, Agency, BuyerProfile
from monitors.error_free_reservation import error_free_reservation
from monitors.epay_ssl import make_vatican_session
from monitors.turnstile_pool import get_token_sync, pool_size

def test_error_free_reservation():
    """Test the error-free reservation implementation."""
    print("🧪 Testing Error-Free Reservation Implementation")
    print("=" * 60)
    
    # Get test agency and create buyer profile if needed
    agency = Agency.objects.filter(is_active=True).first()
    if not agency:
        print("❌ No active agency found")
        return False
    
    print(f"Using agency: {agency.name}")
    
    # Create buyer profile if needed
    buyer_profile, created = BuyerProfile.objects.get_or_create(
        agency=agency,
        defaults={
            'first_name': 'Mario',
            'last_name': 'Rossi',
            'email': 'mario.rossi@example.com',
            'phone': '+39 123 456 7890',
            'country': 'Italy',
            'city': 'Roma',
            'language': 'it'
        }
    )
    
    if created:
        print("✅ Created buyer profile")
    else:
        print("✅ Using existing buyer profile")
    
    # Set participant names to avoid blank names
    participant_names = [
        {"first_name": "Marco", "last_name": "Rossi"},
        {"first_name": "Luca", "last_name": "Bianchi"}
    ]
    buyer_profile.participants_json = json.dumps(participant_names)
    buyer_profile.save()
    print("✅ Set realistic participant names")
    
    # Check Turnstile pool
    pool_count = pool_size()
    print(f"📊 Turnstile pool size: {pool_count}")
    
    if pool_count == 0:
        print("⚠️  Turnstile pool empty, solving token...")
        # This will trigger a solve in the background
        get_token_sync()
        time.sleep(2)  # Wait for solve
    
    # Create a test held slot (or use existing one)
    test_slot = HeldSlot.objects.filter(
        status='held',
        task__agency=agency
    ).first()
    
    if not test_slot:
        print("❌ No held slots found for testing")
        print("💡 Create a held slot first using the hold manager")
        return False
    
    print(f"🎯 Testing with held slot: {test_slot.slot_id}")
    print(f"   Date: {test_slot.date} {test_slot.slot_time}")
    print(f"   Visitors: {test_slot.visitors}")
    print(f"   Recap ID: {test_slot.recap_id}")
    
    # Test the error-free reservation
    print("\n🚀 Testing error-free reservation...")
    
    success, result = error_free_reservation.complete_reservation(test_slot)
    
    if success:
        print("✅ RESERVATION SUCCESS!")
        print(f"   Reference: {result['reference']}")
        print(f"   Epay URL: {result['epay_url'][:50]}...")
        print(f"   Total: €{result['total']}")
        
        # Verify epay URL works
        if result['epay_url']:
            print("\n🔗 Testing epay URL accessibility...")
            try:
                session = make_vatican_session()
                epay_response = session.get(result['epay_url'], timeout=10)
                print(f"   Epay URL status: {epay_response.status_code}")
                if epay_response.status_code == 200:
                    print("   ✅ Epay URL accessible")
                else:
                    print(f"   ⚠️  Epay URL returned {epay_response.status_code}")
            except Exception as e:
                print(f"   ⚠️  Epay URL test failed: {e}")
        
        return True
    else:
        print("❌ RESERVATION FAILED")
        print(f"   Status: {result.get('status_code', 'Unknown')}")
        print(f"   Error: {result.get('error', 'Unknown error')}")
        
        # Analyze the failure
        if result.get('status_code') == 500:
            print("\n🔍 Analyzing 500 error...")
            print("   Possible causes:")
            print("   - Session expired (need re-hold)")
            print("   - Slot sold out between hold and reservation")
            print("   - Turnstile token invalid")
            print("   - Missing Cloudflare headers")
            
            # Check session freshness
            if not test_slot.is_session_fresh():
                print("   ⚠️  Session appears stale, consider re-holding")
        
        return False

def test_turnstile_token_validation():
    """Test Turnstile token validation."""
    print("\n🔍 Testing Turnstile token validation...")
    
    # Test valid token format
    valid_token = "1." + "A" * 500  # Simulate valid token
    result = error_free_reservation.validate_turnstile_token(valid_token)
    print(f"Valid token (500+ chars, starts with '1.'): {result}")
    
    # Test invalid tokens
    short_token = "1." + "A" * 100
    result = error_free_reservation.validate_turnstile_token(short_token)
    print(f"Short token (100 chars): {result}")
    
    wrong_prefix = "0." + "A" * 500
    result = error_free_reservation.validate_turnstile_token(wrong_prefix)
    print(f"Wrong prefix token: {result}")
    
    empty_token = ""
    result = error_free_reservation.validate_turnstile_token(empty_token)
    print(f"Empty token: {result}")

def test_cloudflare_headers():
    """Test Cloudflare header generation."""
    print("\n🔍 Testing Cloudflare header generation...")
    
    # Create a mock session
    session = make_vatican_session()
    session.cookies.set('JSESSIONID', 'TEST123456789ABCDEF')
    error_free_reservation.session = session
    
    headers = error_free_reservation.get_cloudflare_headers()
    print(f"Generated cf-chl header: {headers.get('cf-chl', 'None')[:50]}...")
    print(f"Generated cf-chl-ra header: {headers.get('cf-chl-ra', 'None')}")
    
    # Validate format
    cf_chl = headers.get('cf-chl', '')
    if cf_chl and len(cf_chl) > 20:
        print("✅ cf-chl header format looks valid")
    else:
        print("⚠️  cf-chl header format may be invalid")

def main():
    """Run all tests."""
    print("🚀 Starting Error-Free Reservation Tests")
    print("=" * 60)
    
    # Test components
    test_turnstile_token_validation()
    test_cloudflare_headers()
    
    # Test full reservation flow
    success = test_error_free_reservation()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed - check logs above")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)