import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import MonitorTask, HeldSlot

print("=== SNIPE TASKS ===")
tasks = MonitorTask.objects.filter(tier='snipe', is_active=True).order_by('-created_at')[:10]
for t in tasks:
    print(f"Task #{t.id} | {t.agency.name}")
    print(f"  dates={t.dates} | times={t.preferred_times} | visitors={t.visitors}")
    print(f"  status={t.last_status} | created={t.created_at.strftime('%H:%M:%S')}")
    print(f"  participants={t.participants_json}")

print()
print("=== HELD SLOTS (May 2026) ===")
held = HeldSlot.objects.filter(date__contains='/05/2026').order_by('-hold_started_at')[:10]
if not held:
    print("No held slots for May 2026")
for h in held:
    print(f"  #{h.id} | {h.date} {h.slot_time} | {h.status} | recapId={h.recap_id} | task=#{h.task_id}")

print()
print("=== BROWSER PENDING ===")
from django.core.cache import cache
pending = cache.get('browser_pending', [])
print(f"Pending browser requests: {len(pending)}")
for p in pending:
    print(f"  {p}")
