import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

from monitors.models import Agency, MonitorTask, TelegramGroup
from monitors.notification_utils import send_telegram_signal

# Get Italy pass agency
agency = Agency.objects.get(name='Italy pass')
print(f'Agency: {agency.name} (id={agency.id})')

# Get approved groups
groups = TelegramGroup.objects.filter(agency=agency, status='approved', notification_enabled=True)
print(f'Approved groups: {groups.count()}')
for g in groups:
    print(f'  - {g.chat_title} | chat_id={g.chat_id} | notifications={g.notification_enabled}')

# Get tasks
tasks = MonitorTask.objects.filter(agency=agency, is_active=True)
print(f'\nActive tasks: {tasks.count()}')
for t in tasks:
    print(f'  [{t.id}] {t.dates} | {t.visitors}v | status={t.last_status}')

# Send a test notification
print('\n--- Sending test notification ---')
test_msg = (
    "🧪 TEST NOTIFICATION\n\n"
    "Italy pass group is correctly linked and receiving notifications.\n"
    "Bot is monitoring your Vatican ticket tasks."
)
for g in groups:
    result = send_telegram_signal(g.chat_id, test_msg)
    print(f'  Sent to {g.chat_title} ({g.chat_id}): {"✅ OK" if result else "❌ FAILED"}')
