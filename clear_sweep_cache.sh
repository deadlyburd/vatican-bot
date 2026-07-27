cd backend && python manage.py shell << 'EOF'
from django.core.cache import cache
import re

# Clear all sweep_notified keys for June dates
keys_to_clear = [
    'sweep_notified:17/06/2026',
    'sweep_notified:16/06/2026',
    'sweep_notified:18/06/2026',
    'sweep_notified:19/06/2026',
]
for k in keys_to_clear:
    cache.delete(k)
    print(f"Cleared: {k}")

# Also clear with time suffixes
for date in ['17/06/2026', '16/06/2026', '18/06/2026', '19/06/2026']:
    for t in ['08:00','09:00','10:00','11:00','12:00','13:00','14:00','15:00','16:00','16:30','17:00','17:30']:
        cache.delete(f'sweep_notified:{date}:{t}')
print("Done clearing sweep cache for June dates")
EOF
