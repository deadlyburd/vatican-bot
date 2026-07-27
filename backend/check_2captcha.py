"""Check 2captcha account balance and usage stats"""
import os, sys, requests
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()

API_KEY = os.getenv('TWOCAPTCHA_API_KEY', '')

# Check balance
r = requests.get('https://2captcha.com/res.php', params={
    'key': API_KEY, 'action': 'getbalance', 'json': 1
}, timeout=10)
print(f"Balance: {r.text}")

# Try the correct stats endpoint
from datetime import datetime, timedelta
yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
today = datetime.now().strftime('%Y-%m-%d')

for date_str in [today, yesterday]:
    r2 = requests.get('https://2captcha.com/res.php', params={
        'key': API_KEY, 'action': 'getTaskResultList',
        'date': date_str, 'json': 1
    }, timeout=10)
    print(f"Tasks {date_str}: {r2.text[:300]}")

# Also try reportbad to see if API is working
r3 = requests.get('https://2captcha.com/res.php', params={
    'key': API_KEY, 'action': 'get', 'id': '1', 'json': 1
}, timeout=10)
print(f"API test: {r3.text}")
