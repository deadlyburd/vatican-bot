#!/usr/bin/env python3
"""
Fetch all bookings from Bokun API and create monitoring tasks

This script:
1. Fetches all confirmed bookings from Bokun
2. Writes them to Google Sheets
3. Creates monitoring tasks for Vatican
"""

import sys
import os
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta
import json

# Bokun API credentials
BOKUN_ACCESS_KEY = os.getenv('BOKUN_ACCESS_KEY', '')
BOKUN_SECRET_KEY = os.getenv('BOKUN_SECRET_KEY', '')

# Bokun API base URL
BOKUN_API_BASE = 'https://api.bokun.io'

def test_bokun_endpoints():
    """Test different Bokun API endpoints to find the correct one"""
    
    print("=" * 80)
    print("🧪 Testing Bokun API Endpoints")
    print("=" * 80)
    
    auth = HTTPBasicAuth(BOKUN_ACCESS_KEY, BOKUN_SECRET_KEY)
    
    # Date range: today to 90 days from now
    from_date = datetime.now().strftime('%Y-%m-%d')
    to_date = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')
    
    endpoints = [
        # Try different endpoint formats
        f'/booking.json/confirmed-bookings?from={from_date}&to={to_date}',
        f'/booking.json/bookings?from={from_date}&to={to_date}',
        f'/booking.json/bookings?status=CONFIRMED&from={from_date}&to={to_date}',
        '/booking.json/bookings',
        '/booking.json/confirmed-bookings',
        '/v1/booking/confirmed-bookings',
        '/v1/bookings',
    ]
    
    for endpoint in endpoints:
        url = f"{BOKUN_API_BASE}{endpoint}"
        print(f"\n📡 Testing: {endpoint}")
        
        try:
            response = requests.get(
                url,
                auth=auth,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                timeout=10
            )
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   ✅ SUCCESS! Found data")
                    print(f"   Response type: {type(data)}")
                    
                    if isinstance(data, list):
                        print(f"   Number of bookings: {len(data)}")
                        if data:
                            print(f"\n   First booking sample:")
                            print(json.dumps(data[0], indent=2)[:500])
                    elif isinstance(data, dict):
                        print(f"   Keys: {list(data.keys())}")
                        if 'bookings' in data:
                            print(f"   Number of bookings: {len(data['bookings'])}")
                    
                    return endpoint, data
                    
                except Exception as e:
                    print(f"   Response: {response.text[:200]}")
                    
            elif response.status_code == 404:
                print(f"   ❌ Not Found")
            elif response.status_code == 401:
                print(f"   ❌ Unauthorized - Check credentials")
            else:
                print(f"   Response: {response.text[:200]}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n" + "=" * 80)
    print("❌ No working endpoint found")
    print("=" * 80)
    return None, None

def get_bokun_products():
    """Try to get available products/activities"""
    
    print("\n" + "=" * 80)
    print("🔍 Checking Bokun Products/Activities")
    print("=" * 80)
    
    auth = HTTPBasicAuth(BOKUN_ACCESS_KEY, BOKUN_SECRET_KEY)
    
    endpoints = [
        '/activity.json/activities',
        '/product.json/products',
        '/v1/products',
        '/v1/activities',
    ]
    
    for endpoint in endpoints:
        url = f"{BOKUN_API_BASE}{endpoint}"
        print(f"\n📡 Testing: {endpoint}")
        
        try:
            response = requests.get(
                url,
                auth=auth,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                timeout=10
            )
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   ✅ SUCCESS!")
                    print(f"   Response type: {type(data)}")
                    
                    if isinstance(data, list):
                        print(f"   Number of products: {len(data)}")
                        if data:
                            print(f"\n   First product:")
                            print(json.dumps(data[0], indent=2)[:500])
                    elif isinstance(data, dict):
                        print(f"   Keys: {list(data.keys())}")
                    
                except Exception as e:
                    print(f"   Response: {response.text[:200]}")
                    
        except Exception as e:
            print(f"   ❌ Error: {e}")

def check_bokun_api_docs():
    """Check Bokun API documentation endpoint"""
    
    print("\n" + "=" * 80)
    print("📚 Checking Bokun API Info")
    print("=" * 80)
    
    auth = HTTPBasicAuth(BOKUN_ACCESS_KEY, BOKUN_SECRET_KEY)
    
    # Try to get API info
    endpoints = [
        '/',
        '/api',
        '/v1',
        '/booking.json',
    ]
    
    for endpoint in endpoints:
        url = f"{BOKUN_API_BASE}{endpoint}"
        print(f"\n📡 Testing: {endpoint}")
        
        try:
            response = requests.get(
                url,
                auth=auth,
                timeout=10
            )
            
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                print(f"   Response: {response.text[:300]}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")

if __name__ == '__main__':
    print("\n🚀 Bokun API Explorer")
    print("=" * 80)
    print(f"Access Key: {BOKUN_ACCESS_KEY}")
    print(f"Secret Key: {BOKUN_SECRET_KEY[:8]}...")
    print(f"Base URL: {BOKUN_API_BASE}")
    print("=" * 80)
    
    # Test authentication
    print("\n🔐 Testing Authentication...")
    auth = HTTPBasicAuth(BOKUN_ACCESS_KEY, BOKUN_SECRET_KEY)
    try:
        response = requests.get(
            f"{BOKUN_API_BASE}/",
            auth=auth,
            timeout=5
        )
        print(f"Base URL Status: {response.status_code}")
    except Exception as e:
        print(f"❌ Connection error: {e}")
    
    # Test different endpoints
    endpoint, data = test_bokun_endpoints()
    
    if endpoint:
        print(f"\n✅ Working endpoint found: {endpoint}")
        print(f"\nYou can use this endpoint to fetch bookings!")
    else:
        print("\n⚠️ No bookings endpoint found. Trying other endpoints...")
        get_bokun_products()
        check_bokun_api_docs()
        
        print("\n" + "=" * 80)
        print("📝 Recommendations:")
        print("=" * 80)
        print("1. Check Bokun API documentation: https://docs.bokun.io/")
        print("2. Verify your API credentials are correct")
        print("3. Check if your Bokun account has any bookings")
        print("4. Contact Bokun support for API endpoint information")
        print("\n💡 Alternative: Use Bokun webhooks instead of API polling")
