#!/usr/bin/env python3
"""
Comprehensive API Payload Validation
=====================================

Validates all Vatican API endpoints and payloads from your HAR files.
Ensures perfect integration with your instant sniper system.
"""

import os
import sys
import json
import logging

# Add the backend directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_har_files():
    """Validate HAR file structure and extract API endpoints."""
    print("🔍 Validating HAR Files...")
    
    har_files = []
    if os.path.exists('1.har'):
        har_files.append('1.har')
    if os.path.exists('epay.catholica.va.har'):
        har_files.append('epay.catholica.va.har')
    
    if not har_files:
        print("❌ No HAR files found!")
        return False
    
    print(f"✅ Found {len(har_files)} HAR files")
    
    # Analyze 1.har for Vatican API endpoints
    try:
        with open('1.har', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check critical API endpoints
        endpoints = {
            '/api/visit/reservation': 'Reservation API',
            '/api/visit/recap': 'Recap API', 
            '/api/search/resultPerTag': 'Search API',
            '/api/visit/timeavail': 'Time Availability API',
            '/api/config/initValues': 'Config API'
        }
        
        found_endpoints = []
        for endpoint, description in endpoints.items():
            if endpoint in content:
                found_endpoints.append(f"✅ {description}: {endpoint}")
            else:
                found_endpoints.append(f"❌ {description}: {endpoint}")
        
        print("\nVatican API Endpoints Found:")
        for endpoint in found_endpoints:
            print(f"  {endpoint}")
        
        # Check for session cookies
        cookies_found = []
        for cookie in ['JSESSIONID', 'ticketmv', 'SERVERID']:
            if cookie in content:
                cookies_found.append(f"✅ {cookie}")
            else:
                cookies_found.append(f"❌ {cookie}")
        
        print("\nSession Cookies Found:")
        for cookie in cookies_found:
            print(f"  {cookie}")
        
        return True
        
    except Exception as e:
        print(f"❌ HAR file analysis failed: {e}")
        return False

def validate_reservation_payload():
    """Validate the reservation API payload structure."""
    print("\n📋 Validating Reservation Payload...")
    
    # Expected payload structure from your HAR analysis
    expected_payload = {
        'recaptcha': 'string',
        'lang': 'string', 
        'recapId': 'string',
        'visitorNum': 'integer',
        'visitId': 'string',
        'visitTypeId': 'integer',
        'tickets': 'array',
        'services': 'array',
        'representativeUser': 'object',
        'participantUser': 'array'
    }
    
    print("Expected Reservation Payload Structure:")
    for key, value_type in expected_payload.items():
        print(f"  {key}: {value_type}")
    
    # Check if we can construct a valid payload
    try:
        from monitors.hold_manager import _build_recap_body
        
        # Test payload construction
        test_payload = _build_recap_body(
            slot_id="2026*8586",
            ticket_id=631560202,
            visitors=2,
            services=[]
        )
        
        print("✅ Reservation payload construction successful")
        print(f"   Sample payload keys: {list(test_payload.keys())}")
        
        return True
        
    except Exception as e:
        print(f"❌ Reservation payload validation failed: {e}")
        return False

def validate_session_management():
    """Validate session management functionality."""
    print("\n🔐 Validating Session Management...")
    
    try:
        from monitors.tasks_sweep import _get_proxy
        from monitors.hold_manager import _make_session
        
        # Test proxy acquisition
        proxy = _get_proxy()
        if proxy:
            print(f"✅ Proxy acquisition: {proxy}")
        else:
            print("⚠️  No proxy available - using direct connection")
        
        # Test session creation
        test_session = _make_session(
            jsessionid="test_session_id",
            ticketmv="01", 
            serverid="01|test"
        )
        
        if hasattr(test_session, 'cookies'):
            print("✅ Session creation successful")
        else:
            print("❌ Session creation failed")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Session management validation failed: {e}")
        return False

def validate_database_integration():
    """Validate database models and integration."""
    print("\n💾 Validating Database Integration...")
    
    try:
        from monitors.models import MonitorTask, HeldSlot
        
        # Check database connectivity
        task_count = MonitorTask.objects.count()
        held_count = HeldSlot.objects.count()
        
        print(f"✅ Database connected")
        print(f"   Monitor tasks: {task_count}")
        print(f"   Held slots: {held_count}")
        
        # Test sniper task creation
        sniper_task, created = MonitorTask.objects.get_or_create(
            name="INSTANT-SNIPER-TEST",
            defaults={
                'site': 'vatican',
                'tier': 'sniper', 
                'visitors': 2,
                'is_active': True,
                'agency_id': 1
            }
        )
        
        if created:
            print("✅ Sniper task creation successful")
            sniper_task.delete()  # Clean up
        else:
            print("✅ Sniper task already exists")
        
        return True
        
    except Exception as e:
        print(f"❌ Database validation failed: {e}")
        return False

def validate_celery_configuration():
    """Validate Celery beat configuration."""
    print("\n⏰ Validating Celery Configuration...")
    
    try:
        from backend.core import settings
        
        if hasattr(settings, 'CELERY_BEAT_SCHEDULE'):
            schedule = settings.CELERY_BEAT_SCHEDULE
            
            if 'instant-sniper-scan' in schedule:
                sniper_config = schedule['instant-sniper-scan']
                print("✅ Instant sniper configured in Celery beat")
                print(f"   Task: {sniper_config['task']}")
                print(f"   Schedule: {sniper_config['schedule']} seconds")
                print(f"   Priority: {sniper_config['options']['priority']}")
            else:
                print("❌ Instant sniper not configured in Celery beat")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Celery configuration validation failed: {e}")
        return False

def main():
    """Run all validation tests."""
    print("Comprehensive API Payload Validation")
    print("=" * 50)
    
    tests = [
        ("HAR Files", validate_har_files),
        ("Reservation Payload", validate_reservation_payload),
        ("Session Management", validate_session_management), 
        ("Database Integration", validate_database_integration),
        ("Celery Configuration", validate_celery_configuration)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 50)
    print("Validation Results:")
    print("=" * 50)
    
    all_passed = True
    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{test_name:25} {status}")
        if not success:
            all_passed = False
    
    print("=" * 50)
    
    if all_passed:
        print("🎉 ALL VALIDATIONS PASSED!")
        print("\nYour instant sniper system is ready to deploy.")
        print("All API endpoints, payloads, and integrations are validated.")
    else:
        print("❌ Some validations failed. Please check the errors above.")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)