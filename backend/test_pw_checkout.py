"""
Test the full Playwright UI checkout — no 2captcha needed.
"""
import os, sys, django, logging
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

logging.basicConfig(level=logging.INFO, format='%(message)s')

from monitors.models import BuyerProfile, Agency
from monitors.playwright_checkout import checkout_ui_sync
from datetime import datetime, timedelta

# Find first available date
import requests
BASE = 'https://tickets.museivaticani.va'
VISITORS = 1

agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
profile = BuyerProfile.objects.filter(agency=agency).first()
print(f"Profile: {profile.first_name} {profile.last_name} | {profile.email}\n")

# Use a known available slot to skip the scan (Vatican is rate limiting)
found = {'date': '05/05/2026', 'slot_time': '16:30'}
print(f"Using hardcoded slot: {found['date']} {found['slot_time']}")

print(f"\nRunning Playwright checkout...")
print(f"Date: {found['date']} | Time: {found['slot_time']} | Visitors: {VISITORS}")
print(f"This will take 2-3 minutes (Turnstile solve time)\n")

result = checkout_ui_sync(
    date=found['date'],
    slot_time=found['slot_time'],
    visitors=VISITORS,
    profile=profile,
    timeout_s=180,
)

print(f"\n{'='*60}")
if result['success']:
    print(f"✅ SUCCESS!")
    print(f"Reference: {result['reference']}")
    print(f"Total: €{result['total']}")
    print(f"\nEpay URL: {result['epay_url']}")
    if result['epay_params'] and result['epay_params'].get('mac_avvio'):
        print(f"mac_avvio: {result['epay_params']['mac_avvio'][:20]}...")
        print(f"\nTo pay: open {result['epay_url']} in browser")
        print(f"(POST form with mac_avvio will auto-submit)")
else:
    print(f"❌ Failed: {result['error']}")
    print(f"Screenshot: /tmp/pw_checkout_final.png")
print(f"{'='*60}")
