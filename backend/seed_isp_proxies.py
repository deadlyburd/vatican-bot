"""
Seed Oxylabs ISP proxies into the DB.
These are static Italian IPs — perfect for Vatican (no geo-blocking).
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import Proxy

# Oxylabs ISP proxy credentials from .env
USERNAME = os.getenv('OXYLABS_USERNAME', '')
PASSWORD = os.getenv('OXYLABS_PASSWORD', '')

# All 13 ISP proxies from the list
PROXIES = [
    {"ip": "104.252.197.22", "port": 8001},
    {"ip": "104.252.197.23", "port": 8002},
    {"ip": "104.252.198.14", "port": 8003},
    {"ip": "104.252.198.17", "port": 8004},
    {"ip": "104.252.200.13", "port": 8005},
    {"ip": "104.252.200.9",  "port": 8006},
    {"ip": "104.252.201.11", "port": 8007},
    {"ip": "104.252.201.12", "port": 8008},
    {"ip": "82.22.163.26",   "port": 8009},
    {"ip": "82.22.163.28",   "port": 8010},
    {"ip": "82.22.168.19",   "port": 8011},
    {"ip": "82.22.168.20",   "port": 8012},
    {"ip": "82.22.163.29",   "port": 8013},
]

added = 0
updated = 0

for p in PROXIES:
    ip_port = f"isp.oxylabs.io:{p['port']}"
    obj, created = Proxy.objects.update_or_create(
        ip_port=ip_port,
        defaults={
            'username': USERNAME,
            'password': PASSWORD,
            'is_active': True,
            'fail_count': 0,
            'consecutive_failures': 0,
            'cooldown_until': None,
        }
    )
    if created:
        added += 1
        print(f"  + Added: {ip_port} ({p['ip']})")
    else:
        updated += 1
        print(f"  ~ Updated: {ip_port} ({p['ip']})")

total = Proxy.objects.filter(is_active=True).count()
print(f"\n✅ Done: {added} added, {updated} updated | Total active proxies: {total}")

# Quick test — verify one proxy works
print("\nTesting proxy connectivity...")
import requests
test_proxy = f"http://{USERNAME}:{PASSWORD}@isp.oxylabs.io:8001"
try:
    r = requests.get('https://ip.oxylabs.io', proxies={'https': test_proxy}, timeout=10)
    print(f"  Proxy IP: {r.text.strip()}")
    print(f"  ✅ Proxy working!")
except Exception as e:
    print(f"  ❌ Proxy test failed: {e}")
    print(f"  (This is OK if running inside Docker without proxy access)")
