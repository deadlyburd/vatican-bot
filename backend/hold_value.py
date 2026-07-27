import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import HeldSlot
from django.db.models import Sum, Count

held = HeldSlot.objects.filter(status='held')
total_value = held.aggregate(total=Sum('total_price'))['total'] or 0
april = held.filter(date__contains='/04/2026')
may = held.filter(date__contains='/05/2026')
april_val = april.aggregate(total=Sum('total_price'))['total'] or 0
may_val = may.aggregate(total=Sum('total_price'))['total'] or 0

# Unique dates held
dates = held.values_list('date', flat=True).distinct()
print(f"Total held slots:  {held.count()}")
print(f"Total ticket value: €{total_value:,.2f}")
print(f"April: {april.count()} slots | €{april_val:,.2f}")
print(f"May:   {may.count()} slots | €{may_val:,.2f}")
print(f"Unique dates held: {dates.count()}")
print(f"Oldest hold: {held.order_by('hold_started_at').first().hold_duration_minutes() // 60}h {held.order_by('hold_started_at').first().hold_duration_minutes() % 60}min ago")
