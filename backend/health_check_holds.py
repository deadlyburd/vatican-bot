import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import HeldSlot
held = HeldSlot.objects.filter(status='held')
april = held.filter(date__contains='/04/2026')
may = held.filter(date__contains='/05/2026')
oldest = held.order_by('hold_started_at').first()
print(f'Total held: {held.count()}')
print(f'April: {april.count()} slots')
print(f'May: {may.count()} slots')
if oldest:
    print(f'Oldest hold: #{oldest.id} | {oldest.date} {oldest.slot_time} | {oldest.hold_duration_minutes()} min ago')
