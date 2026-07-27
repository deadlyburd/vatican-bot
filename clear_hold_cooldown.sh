cd backend && python manage.py shell << 'EOF'
from django.core.cache import cache
from monitors.models import MonitorTask

# Clear hold cooldowns for all June snipe tasks so they fire immediately
tasks = MonitorTask.objects.filter(is_active=True, tier='snipe')
cleared = 0
for task in tasks:
    for date in (task.dates or []):
        for t in ['08:00','09:00','10:00','11:00','12:00','13:00','14:00','15:00','16:00','16:30','17:00','17:30']:
            for slot_id_prefix in ['2026*']:
                # Clear by pattern - delete all hold cooldown keys for this task+date
                key = f"hold_cooldown:{task.id}:{date}"
                cache.delete(key)
                cleared += 1
        # Also clear state cache so is_first_check triggers
        for date_fmt in [date, date.replace('-', '/')]:
            cache.delete(f"ticket_state:{task.id}:{date_fmt}")
            
print(f"Cleared cooldowns for {tasks.count()} tasks")
print("Tasks will re-trigger on next check cycle (~30s)")
EOF
