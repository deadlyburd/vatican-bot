cd backend && python manage.py shell << 'EOF'
from django.core.cache import cache
from monitors.models import MonitorTask, HeldSlot, CheckResult

# Delete in correct order (child records first)
cr = CheckResult.objects.count()
CheckResult.objects.all().delete()
print(f"Deleted {cr} check results")

hold_count = HeldSlot.objects.count()
HeldSlot.objects.all().delete()
print(f"Deleted {hold_count} holds")

task_count = MonitorTask.objects.count()
MonitorTask.objects.all().delete()
print(f"Deleted {task_count} tasks")

# Flush Redis cache
cache.clear()
print("Redis cache cleared")

print("\nClean slate. Ready for fresh test.")
EOF
