cd backend && python manage.py shell << 'EOF'
from core.celery import app

# Check queue depth
with app.connection() as conn:
    q = conn.default_channel.queue_declare('vatican', passive=True)
    print(f"Vatican queue depth: {q.message_count} tasks waiting")

# Check active workers
i = app.control.inspect(timeout=3)
stats = i.stats() or {}
print(f"Workers online: {len(stats)}")
for w, s in stats.items():
    pool = s.get('pool', {})
    print(f"  {w}: {pool.get('implementation','?')} pool, {pool.get('max-concurrency','?')} workers")

active = i.active() or {}
total_active = sum(len(v) for v in active.values())
print(f"Active tasks: {total_active}")

reserved = i.reserved() or {}
total_reserved = sum(len(v) for v in reserved.values())
print(f"Reserved (queued) tasks: {total_reserved}")
EOF
