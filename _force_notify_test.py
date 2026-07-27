"""
Force-test the full notification pipeline end-to-end.
Clears Redis state for task 260, then calls the actual worker task
with fake slots to prove the notification fires.
"""
import os, sys, django
sys.path.insert(0, '/app/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.core.cache import cache
from monitors.tasks_search_api import run_search_api_vatican_monitor
from monitors.models import MonitorTask

TASK_ID = 260
DATE = '15/06/2026'

task = MonitorTask.objects.get(id=TASK_ID)
print(f"Testing task {TASK_ID}: {task.area_name} | agency={task.agency.name} | v={task.visitors}")

# Step 1: clear state so it's treated as a real closed→open transition
state_key = f"ticket_state:{TASK_ID}:{DATE}"
cooldown_key = f"alert_cooldown:{TASK_ID}:{DATE}"
cache.set(state_key, 'closed', timeout=86400)
cache.delete(cooldown_key)
print(f"Set state=closed, cleared cooldown for task {TASK_ID}")

# Step 2: monkey-patch the monitor to return fake slots
import worker_vatican.search_api_monitor as sam
original_check = sam.VaticanSearchAPIMonitor.check_ticket

def fake_check(self, target_date, ticket_name, visitors, ticket_type=0, language=None):
    print(f"  [MOCK] check_ticket called for {target_date}")
    return True, [
        {'time': '08:00', 'id': '99901', 'availability': 'AVAILABLE'},
        {'time': '09:00', 'id': '99902', 'availability': 'AVAILABLE'},
    ], '1277573256'

sam.VaticanSearchAPIMonitor.check_ticket = fake_check

# Step 3: run the actual task synchronously
print(f"\nRunning task synchronously with fake slots...")
result = run_search_api_vatican_monitor(
    date=DATE,
    ticket_id=None,
    ticket_name="Musei Vaticani - Biglietti d'ingresso",
    language=None,
    task_ids=[TASK_ID],
    visitors=task.visitors,
)
print(f"\nTask result: {result}")

# Restore
sam.VaticanSearchAPIMonitor.check_ticket = original_check
