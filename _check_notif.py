import os, sys, django
sys.path.insert(0, '/app/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import TelegramGroup, MonitorTask, Agency

tasks = MonitorTask.objects.filter(is_active=True, site='vatican').select_related('agency')
agency_seen = set()
for t in tasks:
    if t.agency_id in agency_seen:
        continue
    agency_seen.add(t.agency_id)
    groups = TelegramGroup.objects.filter(agency=t.agency, status='approved', notification_enabled=True)
    legacy = t.agency.telegram_chat_id
    modes = list(MonitorTask.objects.filter(agency=t.agency, is_active=True).values_list('notification_mode', flat=True))
    mode_set = set(modes)
    print(f"Agency: {t.agency.name}")
    print(f"  enabled groups: {list(groups.values_list('chat_id', flat=True))}")
    print(f"  legacy chat_id: {legacy}")
    print(f"  notification_modes: {mode_set}")
    print()
