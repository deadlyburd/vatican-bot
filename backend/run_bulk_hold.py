"""
Immediately recap and hold ALL available slots from today to April 20.
Runs continuously — as soon as a slot appears, it gets locked.
"""
import os, sys, django, time, logging
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

from monitors.models import BulkHoldConfig, Agency
from monitors.tasks_bulk_hold import bulk_hold_scan
from datetime import date, timedelta

agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
print(f"Agency: {agency.name}")

# Create bulk hold config for today → April 20, all times
date_from = date.today()
date_to = date(2026, 4, 20)

cfg, created = BulkHoldConfig.objects.get_or_create(
    agency=agency,
    date_from=date_from,
    date_to=date_to,
    defaults={
        'time_from': '08:00',
        'time_to': '17:30',
        'visitors': 1,
        'is_active': True,
    }
)
if not created:
    cfg.is_active = True
    cfg.time_from = '08:00'
    cfg.time_to = '17:30'
    cfg.save()

print(f"BulkHoldConfig #{cfg.id}: {date_from} → {date_to} | 08:00-17:30 | 1 visitor")
print(f"Running scan now...")

# Run the scan directly (not via Celery — immediate)
result = bulk_hold_scan()
print(f"\nScan result: {result}")

# Show what's held
from monitors.models import HeldSlot
held = HeldSlot.objects.filter(status__in=['held','paying']).order_by('date','slot_time')
print(f"\nCurrently held ({held.count()} slots):")
for h in held:
    print(f"  {h.date} {h.slot_time} | {h.visitors}v | recapId={h.recap_id} | status={h.status}")
