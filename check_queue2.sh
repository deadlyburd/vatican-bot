cd backend && python manage.py shell << 'EOF'
from core.celery import app

# Check active workers and concurrency
i = app.control.inspect(timeout=3)
stats = i.stats() or {}
print(f"Workers online: {len(stats)}")
for w, s in stats.items():
    pool = s.get('pool', {})
    print(f"  {w}")
    print(f"    concurrency: {pool.get('max-concurrency', '?')}")
    print(f"    processes: {pool.get('processes', '?')}")

active = i.active() or {}
total_active = sum(len(v) for v in active.values())
print(f"\nActive tasks right now: {total_active}")
for w, tasks in active.items():
    for t in tasks[:5]:
        print(f"  {t.get('name','?')} — {str(t.get('args',''))[:60]}")

reserved = i.reserved() or {}
total_reserved = sum(len(v) for v in reserved.values())
print(f"\nQueued (waiting) tasks: {total_reserved}")
EOF
