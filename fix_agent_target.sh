cd backend && python manage.py shell << 'EOF'
from monitors.models import MonitorTask
from django.core.cache import cache

# Fix task #171 agent target
t = MonitorTask.objects.get(id=171)
t.agent_target = 'windows-main'
t.save(update_fields=['agent_target'])
print(f"Task #171 agent_target updated to: windows-main")

# Clear all hold cooldowns so they fire immediately
for task in MonitorTask.objects.filter(tier='snipe'):
    for date_iso in (task.dates or []):
        try:
            parts = date_iso.split('-')
            d_api = f"{parts[2]}/{parts[1]}/{parts[0]}"
        except Exception:
            d_api = date_iso
        for t_slot in ['08:00','09:00','10:00','11:00','12:00','13:00','14:00','15:00','16:00','16:30','17:00','17:30']:
            cache.delete(f"hold_cooldown:{task.id}:{d_api}:{t_slot}")
        cache.delete(f"ticket_state:{task.id}:{d_api}")
        cache.delete(f"ticket_state:{task.id}:{date_iso}")
    print(f"Cleared cooldowns for task #{task.id}")

print("Done.")
EOF
