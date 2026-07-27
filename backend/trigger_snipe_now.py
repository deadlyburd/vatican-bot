"""Manually trigger snipe for tasks that have available slots."""
import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import MonitorTask
from monitors.epay_ssl import make_vatican_session
from monitors.tasks_sweep import sweep_notify_slot

BASE = 'https://tickets.museivaticani.va'
H = {'Accept':'application/json','X-Requested-With':'XMLHttpRequest','Referer':f'{BASE}/'}

# Check all active snipe tasks
tasks = MonitorTask.objects.filter(tier='snipe', is_active=True).order_by('-created_at')[:10]

for task in tasks:
    for iso_date in task.dates:
        year, month, day = iso_date.split('-')
        d_api = f"{day}/{month}/{year}"

        s = make_vatican_session(use_proxy=True)
        r = s.get(f'{BASE}/api/search/resultPerTag', params={
            'lang':'it','visitorNum':str(task.visitors),'visitDate':d_api,
            'area':'1','who':'','page':'0','tag':'MV-Biglietti'
        }, headers=H, timeout=10)
        if r.status_code != 200:
            print(f"Task #{task.id} {d_api}: API error {r.status_code}")
            continue

        ticket = next((v for v in r.json().get('visits',[])
                       if 'musei vaticani' in v.get('name','').lower()
                       and 'ingresso' in v.get('name','').lower()
                       and v.get('availability') in ('AVAILABLE','LOW_AVAILABILITY')), None)
        if not ticket:
            print(f"Task #{task.id} {d_api}: SOLD_OUT — monitoring")
            continue

        tid = ticket['id']
        r2 = s.get(f'{BASE}/api/visit/timeavail', params={
            'lang':'it','visitLang':'','visitTypeId':str(tid),
            'visitorNum':str(task.visitors),'visitDate':d_api,
        }, headers=H, timeout=10)
        if r2.status_code != 200:
            continue

        for sl in r2.json().get('timetable',[]):
            if sl.get('availability') not in ('SOLD_OUT','NOT_ALLOWED'):
                slot_time = sl['time']
                if not task.preferred_times or slot_time in task.preferred_times:
                    print(f"Task #{task.id} {d_api} {slot_time}: AVAILABLE — triggering snipe NOW!")
                    sweep_notify_slot(date=d_api, slot_id=str(sl['id']), slot_time=slot_time)
                    print(f"  ✅ Snipe triggered — check WOR Bot and your screen")
                    break
