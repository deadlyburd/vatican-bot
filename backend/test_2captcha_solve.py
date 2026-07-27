"""
Test 2captcha reCAPTCHA v3 solve for Vatican.
Vatican uses reCAPTCHA Enterprise — site key extracted from their API config endpoint.
"""
import os, sys, requests, re, json
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

BASE = 'https://tickets.museivaticani.va'

# Step 1: Try to get site key from Vatican's config API
print("Fetching Vatican config...")
r = requests.get(f'{BASE}/api/config/isAgency',
    headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'},
    timeout=10)
print(f"isAgency: {r.status_code} | {r.text[:200]}")

# Try the recaptcha config endpoint
r2 = requests.get(f'{BASE}/api/config/recaptcha',
    headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'},
    timeout=10)
print(f"recaptcha config: {r2.status_code} | {r2.text[:200]}")

# Try general config
r3 = requests.get(f'{BASE}/api/config',
    headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'},
    timeout=10)
print(f"config: {r3.status_code} | {r3.text[:500]}")

# Step 2: Check if 2captcha API key is set
api_key = os.getenv('TWOCAPTCHA_API_KEY', '')
if not api_key:
    print("\n⚠️  TWOCAPTCHA_API_KEY not set in environment")
    print("Add it to .env: TWOCAPTCHA_API_KEY=your_key_here")
    print("Get a key at: https://2captcha.com")
else:
    print(f"\n✅ 2captcha key found: {api_key[:8]}...")

    # Step 3: Try to solve with known Vatican site key
    # Vatican uses reCAPTCHA Enterprise — site key from their JS
    # Based on token format "0.xxx" this is Enterprise v3
    SITE_KEY = '6LcI6-0UAAAAAJ8sMjEBBFHMFJFJFJFJFJFJFJFJ'  # placeholder
    PAGE_URL = f'{BASE}/home/checkout'

    from twocaptcha import TwoCaptcha
    solver = TwoCaptcha(api_key)

    print(f"\nAttempting reCAPTCHA v3 solve...")
    print(f"Site key: {SITE_KEY}")
    print(f"Page: {PAGE_URL}")

    try:
        result = solver.recaptcha(
            sitekey=SITE_KEY,
            url=PAGE_URL,
            version='v3',
            action='submit',
            score=0.3,
        )
        print(f"✅ Solved! Token: {result['code'][:50]}...")
    except Exception as e:
        print(f"❌ Error: {e}")
