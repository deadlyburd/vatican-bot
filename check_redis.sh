cd backend && python manage.py shell << 'EOF'
from django.core.cache import cache

# Check what's in the agent queue
key = 'browser_pending_windows-main'
val = cache.get(key)
print(f"Key '{key}': {val}")

shared = cache.get('browser_pending')
print(f"Key 'browser_pending': {shared}")

# List all keys with browser_pending prefix
import django_redis
try:
    client = cache.client.get_client()
    keys = client.keys('browser_pending*')
    print(f"All browser_pending keys: {keys}")
except Exception as e:
    print(f"Redis client error: {e}")
    # Try alternative
    try:
        from django.core.cache import caches
        c = caches['default']
        print(f"Cache backend: {c.__class__.__name__}")
    except Exception as e2:
        print(f"Cache error: {e2}")
EOF
