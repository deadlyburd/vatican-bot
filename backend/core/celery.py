import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('core')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Explicitly import tasks_search_api to ensure registration
app.autodiscover_tasks(['monitors'], related_name='tasks_search_api')

# Explicitly import main tasks module to ensure registration
app.autodiscover_tasks(['monitors'], related_name='tasks')

# Hold manager tasks
app.autodiscover_tasks(['monitors'], related_name='tasks_hold')

# Sweep tasks (mass hold)
app.autodiscover_tasks(['monitors'], related_name='tasks_sweep')

# Bulk hold manager
app.autodiscover_tasks(['monitors'], related_name='tasks_bulk_hold')

# Turnstile token pool
app.autodiscover_tasks(['monitors'], related_name='turnstile_pool')

# Lightning snipe engine
app.autodiscover_tasks(['monitors'], related_name='lightning_snipe')

# Cleanup and memory health tasks
app.autodiscover_tasks(['monitors'], related_name='tasks_cleanup')

# Google Sheets auto-sync
app.autodiscover_tasks(['monitors'], related_name='tasks_google_sheets')

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


# Start token pool when the snipe worker boots
from celery.signals import worker_ready

@worker_ready.connect
def start_token_pool(sender=None, **kwargs):
    try:
        from monitors.turnstile_pool import start_pool
        start_pool()
    except Exception as e:
        print(f"Token pool start failed: {e}")
