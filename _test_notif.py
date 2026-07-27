"""
End-to-end notification test:
1. Clears the Redis state for task 260 (15/06, 6v)
2. Simulates slots being found
3. Runs the full notification path
4. Reports what would happen
"""
import os, sys, django
sys.path.insert(0, '/app/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.core.cache import cache
from monitors.models import MonitorTask, TelegramGroup
from monitors.notification_utils import send_telegram_signal, format_vatican_notification

TASK_ID = 260
DATE = '15/06/2026'

task = MonitorTask.objects.get(id=TASK_ID)
print(f"Task {TASK_ID}: {task.area_name} | v={task.visitors} | mode={task.notification_mode} | agency={task.agency.name}")

# Check groups
groups = TelegramGroup.objects.filter(agency=task.agency, status='approved', notification_enabled=True)
print(f"Approved+enabled groups: {list(groups.values_list('chat_id', flat=True))}")

# Check current state
state_key = f"ticket_state:{TASK_ID}:{DATE}"
cooldown_key = f"alert_cooldown:{TASK_ID}:{DATE}"
current_state = cache.get(state_key)
cooldown = cache.get(cooldown_key)
print(f"Redis state: {current_state} | cooldown: {cooldown}")

# Simulate: clear state so next check treats it as first_check=False, previous=closed
cache.set(state_key, 'closed', timeout=86400)
cache.delete(cooldown_key)
print(f"Set state=closed, cleared cooldown")

# Now simulate what happens when slots are found
fake_slots = [{'time': '08:00', 'id': '999', 'availability': 'AVAILABLE'},
              {'time': '09:00', 'id': '998', 'availability': 'AVAILABLE'}]

previous_state = cache.get(state_key)  # 'closed'
is_first_check = previous_state is None
is_now_available = True
was_previously_available = previous_state == 'available'
status_changed_to_open = is_now_available and not was_previously_available

print(f"\nSimulation:")
print(f"  previous_state={previous_state} is_first_check={is_first_check}")
print(f"  status_changed_to_open={status_changed_to_open}")

should_alert = status_changed_to_open and not is_first_check
print(f"  should_alert={should_alert}")
print(f"  notification_mode={task.notification_mode} (not silent = {task.notification_mode != 'silent'})")

if should_alert and task.notification_mode != 'silent':
    print("\n✅ WOULD SEND notification - testing actual send...")
    msg = format_vatican_notification(
        date=DATE, ticket_name=task.ticket_name or task.area_name,
        ticket_id='test', slots=fake_slots,
        preferred_times=task.preferred_times, visitors=task.visitors
    )
    for g in groups:
        result = send_telegram_signal(g.chat_id, msg)
        print(f"  Sent to {g.chat_id}: {result}")
else:
    print(f"\n❌ Would NOT send - diagnosing:")
    if is_first_check:
        print("  REASON: is_first_check=True (previous_state was None)")
        print("  FIX: State was just set to 'closed' above, re-run to simulate second check")
    if not status_changed_to_open:
        print(f"  REASON: status_changed_to_open=False (previous={previous_state})")
    if task.notification_mode == 'silent':
        print("  REASON: notification_mode=silent")
