cd backend && python manage.py shell << 'EOF'
from monitors.models import MonitorTask
for t in MonitorTask.objects.filter(tier='snipe'):
    print(f"Task #{t.id}: dates={t.dates} agent={t.agent_target} times={t.preferred_times}")
EOF
