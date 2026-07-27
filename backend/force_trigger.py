"""Force trigger browser for June 19 17:00 regardless of held slots"""
import os, sys, django, base64
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.core.cache import cache

# June 19 17:00 with 2 visitors
date = '19/06/2026'
slot_time = '17:00'
slot_id = '2026*8866'
visitors = 2

slot_info = base64.b64encode(f"{date}|{slot_time}|{slot_id}|{visitors}|50.0".encode()).decode()
data = f'open_browser_slot:{slot_info}'

pending = cache.get('browser_pending', [])
pending.append({'data': data, 'user': 'Force trigger', 'auto': True})
cache.set('browser_pending', pending, timeout=300)
print(f"Queued: {data[:60]}")
print("Agent will pick this up within 10 seconds and open Chrome")
