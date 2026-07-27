import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()

from monitors.models import Agency, TelegramGroup, MonitorTask
from django.contrib.auth import get_user_model

print('\n' + '='*80)
print('  FULL AGENCY / USER / GROUP AUDIT')
print('='*80)

# ── All agencies ──────────────────────────────────────────────────────────────
print(f'\n[AGENCIES] Total: {Agency.objects.count()}\n')
for a in Agency.objects.all().order_by('id'):
    print(f'  [{a.id}] {a.name}  plan={a.plan}  active={a.is_active}  api_key={a.api_key}  tg_chat_id={a.telegram_chat_id}')

# ── All telegram groups ───────────────────────────────────────────────────────
print(f'\n[TELEGRAM GROUPS] Total: {TelegramGroup.objects.count()}\n')
for g in TelegramGroup.objects.all().order_by('id'):
    agency_name = g.agency.name if g.agency else '(no agency)'
    agency_id   = g.agency.id   if g.agency else 'N/A'
    print(f'  [{g.id}] "{g.chat_title}"  chat_id={g.chat_id}  status={g.status}  notif={g.notification_enabled}  agency=[{agency_id}]{agency_name}')

# ── All users ─────────────────────────────────────────────────────────────────
try:
    from monitors.models import User as BotUser
    print(f'\n[BOT USERS] Total: {BotUser.objects.count()}\n')
    for u in BotUser.objects.all().order_by('id'):
        agency_name = u.agency.name if u.agency else '(no agency)'
        print(f'  [{u.id}] username={u.username}  email={u.email}  agency={agency_name}  active={u.is_active}  admin={u.is_admin}')
except Exception as e:
    print(f'  (could not load BotUser: {e})')

# ── Groups with no agency ─────────────────────────────────────────────────────
orphan_groups = TelegramGroup.objects.filter(agency__isnull=True)
print(f'\n[ORPHAN GROUPS — no agency linked] Count: {orphan_groups.count()}\n')
for g in orphan_groups:
    print(f'  [{g.id}] "{g.chat_title}"  chat_id={g.chat_id}  status={g.status}  notif={g.notification_enabled}')

# ── Pending groups ────────────────────────────────────────────────────────────
pending = TelegramGroup.objects.filter(status='pending')
print(f'\n[PENDING GROUPS — waiting approval] Count: {pending.count()}\n')
for g in pending:
    agency_name = g.agency.name if g.agency else '(no agency)'
    print(f'  [{g.id}] "{g.chat_title}"  chat_id={g.chat_id}  agency={agency_name}')

# ── Summary: who will actually get notified ───────────────────────────────────
print('\n' + '='*80)
print('  NOTIFICATION READINESS')
print('='*80 + '\n')
for a in Agency.objects.filter(is_active=True).exclude(plan='system').order_by('name'):
    approved_groups = TelegramGroup.objects.filter(agency=a, status='approved', notification_enabled=True)
    active_tasks    = MonitorTask.objects.filter(agency=a, is_active=True)
    ready = approved_groups.exists() and active_tasks.exists()
    print(f'  {"✅" if ready else "❌"} {a.name} (id={a.id}) — approved_groups={approved_groups.count()}  active_tasks={active_tasks.count()}')
    if not approved_groups.exists():
        all_groups = TelegramGroup.objects.filter(agency=a)
        if all_groups.exists():
            for g in all_groups:
                print(f'       group "{g.chat_title}" status={g.status} notif={g.notification_enabled}')
        else:
            print(f'       (no groups at all)')

print()
