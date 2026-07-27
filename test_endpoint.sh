cd backend && python manage.py shell << 'EOF'
# Simulate exactly what the view does
from django.core.cache import cache
import time

agent_id = 'windows-main'

# Check agent-specific queue
key = f'browser_pending_{agent_id}'
targeted = cache.get(key, [])
print(f"Targeted queue ({key}): {len(targeted)} items")
if targeted:
    print(f"  First item: {targeted[0]['data'][:60]}")

# Check shared queue
pending = cache.get('browser_pending', [])
print(f"Shared queue: {len(pending)} items")

# Simulate what the view returns
if targeted:
    cache.delete(key)
    print(f"Would return: {len(targeted)} requests")
elif pending:
    cache.delete('browser_pending')
    print(f"Would return from shared: {len(pending)} requests")
else:
    print("Would return: empty")
EOF
