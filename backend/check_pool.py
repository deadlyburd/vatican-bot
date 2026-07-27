import os, sys, django, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()
from django.core.cache import cache
from monitors.turnstile_pool import POOL_KEY, RESERVED_KEY
pool = cache.get(POOL_KEY, [])
reserved = cache.get(RESERVED_KEY)
now = time.time()
print(f"Pool size: {len(pool)}")
for i, t in enumerate(pool):
    age = now - t.get('solved_at', 0)
    tok = t['token']
    print(f"  [{i}] age={age:.0f}s prefix={tok[:4]} len={len(tok)}")
if reserved:
    age = now - reserved.get('solved_at', 0)
    tok = reserved['token']
    print(f"Reserved: age={age:.0f}s prefix={tok[:4]} len={len(tok)}")
    print(f"  Full token: {tok}")
else:
    print("No reserved token")
