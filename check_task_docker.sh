cd backend && python manage.py shell << 'EOF'
from monitors.models import MonitorTask
tasks = MonitorTask.objects.filter(is_active=True, tier='snipe')
print(f"Active snipe tasks: {tasks.count()}")
for t in tasks:
    print(f"\nTask #{t.id}")
    print(f"  dates:    {t.dates}")
    print(f"  visitors: {t.visitors} (a={t.adult_count} c={t.child_count})")
    print(f"  times:    {t.preferred_times}")
    print(f"  method:   {t.checkout_method}")
    print(f"  agent:    {t.agent_target}")
    print(f"  status:   {t.last_status}")
    print(f"  result:   {str(t.last_result_summary)[:120]}")
EOF
