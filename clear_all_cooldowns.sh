cd backend && python manage.py shell << 'EOF'
from django.core.cache import cache
from monitors.models import MonitorTask

# Clear ALL hold cooldowns and state caches for snipe tasks
tasks = MonitorTask.objects.filter(is_active=True, tier='snipe')
print(f"Clearing cooldowns for {tasks.count()} snipe tasks...")

for task in tasks:
    for date_iso in (task.dates or []):
        # Convert YYYY-MM-DD to DD/MM/YYYY
        try:
            parts = date_iso.split('-')
            d_api = f"{parts[2]}/{parts[1]}/{parts[0]}"
        except Exception:
            d_api = date_iso

        # Clear hold cooldowns (all possible slot_id patterns)
        for prefix in ['2026*', '']:
            cache.delete(f"hold_cooldown:{task.id}:{d_api}")
            cache.delete(f"hold_cooldown:{task.id}:{date_iso}")

        # Clear state cache so is_first_check triggers again
        cache.delete(f"ticket_state:{task.id}:{d_api}")
        cache.delete(f"ticket_state:{task.id}:{date_iso}")

        # Clear alert cooldown
        cache.delete(f"alert_cooldown:{task.id}:{d_api}")
        cache.delete(f"alert_cooldown:{task.id}:{date_iso}")

        print(f"  Task #{task.id} {d_api} — cleared")

print("Done. Next check cycle will fire immediately.")
EOF
