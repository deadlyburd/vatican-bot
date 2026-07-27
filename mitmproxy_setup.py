"""
MITM Proxy Setup for Vatican API Analysis
This script sets up mitmproxy to monitor Vatican API traffic and detect anti-bot patterns.
"""
import subprocess
import time
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# MITM Proxy configuration
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8080
PROXY_URL = f"http://{PROXY_HOST}:{PROXY_PORT}"

# Vatican API endpoints to monitor
VATICAN_ENDPOINTS = [
    "https://tickets.museivaticani.va/api/visit/recap",
    "https://tickets.museivaticani.va/api/config/isAgency", 
    "https://tickets.museivaticani.va/api/visit/services",
    "https://tickets.museivaticani.va/api/search/resultPerTag",
    "https://tickets.museivaticani.va/api/visit/timeavail"
]

def test_vatican_with_proxy():
    """Test Vatican API connectivity through mitmproxy"""
    session = requests.Session()
    session.proxies = {
        'http': PROXY_URL,
        'https': PROXY_URL
    }
    session.verify = False  # Disable SSL verification for mitmproxy
    
    # Test basic connectivity
    try:
        print("🧪 Testing Vatican API through mitmproxy...")
        
        # Test homepage first
        response = session.get("https://tickets.museivaticani.va/home", timeout=10)
        print(f"✅ Homepage: {response.status_code}")
        
        # Test search API
        params = {
            'lang': 'it', 
            'visitorNum': '2', 
            'visitDate': '2026-04-15',
            'area': '1', 
            'who': '', 
            'page': '0', 
            'tag': 'MV-Biglietti'
        }
        response = session.get(
            "https://tickets.museivaticani.va/api/search/resultPerTag", 
            params=params, 
            timeout=10
        )
        print(f"✅ Search API: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"📊 Found {len(data.get('visits', []))} ticket types")
        
        return True
        
    except Exception as e:
        print(f"❌ Proxy test failed: {e}")
        return False

def analyze_keepalive_pattern():
    """Analyze the current keepalive pattern and suggest improvements"""
    print("\n🔍 Keepalive Pattern Analysis:")
    print("============================")
    
    # Current issues
    issues = [
        "Fixed 5-minute intervals (easily detectable)",
        "No randomization in timing patterns", 
        "Same API endpoints used repeatedly",
        "No user-agent rotation",
        "Predictable request sequences",
        "No IP rotation between requests"
    ]
    
    for i, issue in enumerate(issues, 1):
        print(f"{i}. {issue}")
    
    print("\n🎯 Recommended Improvements:")
    print("============================")
    improvements = [
        "Randomized keepalive intervals (3-8 minutes)",
        "Rotate between different API endpoints",
        "Vary user-agent strings randomly",
        "Implement IP rotation using proxies",
        "Add jitter to request timing",
        "Use different HTTP methods occasionally (HEAD, OPTIONS)",
        "Simulate human browsing patterns"
    ]
    
    for i, improvement in enumerate(improvements, 1):
        print(f"{i}. {improvement}")

if __name__ == "__main__":
    print("🚀 Vatican API MITM Proxy Analysis")
    print("==================================")
    
    analyze_keepalive_pattern()
    
    print("\n📋 To use mitmproxy:")
    print("1. Install: pip install mitmproxy")
    print("2. Run: mitmproxy --set confdir=~/.mitmproxy --mode regular")
    print("3. Configure proxy: 127.0.0.1:8080")
    print("4. Run this script to test through proxy")
    
    # Uncomment to test when mitmproxy is running
    # test_vatican_with_proxy()