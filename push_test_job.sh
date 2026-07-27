cd backend && python manage.py shell << 'EOF'
from django.core.cache import cache
import base64

# Push a test job directly to windows-main queue
date = '13/05/2026'
slot_time = '15:00'
slot_id = '2026*8222'
visitors = 1

slot_info = base64.b64encode(
    f"{date}|{slot_time}|{slot_id}|{visitors}|28.0|{visitors}|0".encode()
).decode()

job = {
    'data': f'open_browser_slot:{slot_info}',
    'user': 'Test',
    'auto': True,
}

# Push to agent-specific queue
key = 'browser_pending_windows-main'
q = cache.get(key, [])
q.insert(0, job)
cache.set(key, q, timeout=1800)
print(f"Pushed test job to {key}")
print(f"Queue size: {len(q)}")

# Also check shared queue
shared = cache.get('browser_pending', [])
print(f"Shared queue size: {len(shared)}")
EOF
