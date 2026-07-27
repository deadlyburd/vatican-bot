import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import MonitorTask, HeldSlot
from django.utils import timezone

print("=== LATEST 5 TASKS ===")
tasks = MonitorTask.objects.filter(is_active=True).order_by('-created_at')[:5]
for t in tasks:
    age = (timezone.now() - t.created_at).total_seconds()
    print(f"#{t.id} | {t.agency.name} | tier={t.tier} | dates={t.dates} | times={t.preferred_times} | {age:.0f}s ago")

print()
print("=== LATEST HELD SLOTS ===")
held = HeldSlot.objects.order_by('-hold_started_at')[:5]
for h in held:
    print(f"#{h.id} | {h.date} {h.slot_time} | {h.status} | task=#{h.task_id}")
