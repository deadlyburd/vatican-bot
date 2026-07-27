import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import TelegramGroup, Agency

CHAT_ID = '-520664897'

print("=== ALL GROUPS IN DB ===")
for g in TelegramGroup.objects.all().order_by('-created_at'):
    print(f"  chat_id={g.chat_id} | title={g.chat_title} | status={g.status} | agency={g.agency_id}")

print("\n=== ALL AGENCIES ===")
for a in Agency.objects.filter(is_active=True).exclude(plan='system'):
    print(f"  id={a.id} | name={a.name} | plan={a.plan}")

print(f"\n=== FIXING GROUP {CHAT_ID} ===")
g = TelegramGroup.objects.filter(chat_id=CHAT_ID).first()
if not g:
    print(f"Group {CHAT_ID} not found — creating it")
    agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
    g = TelegramGroup.objects.create(
        chat_id=CHAT_ID,
        chat_type='group',
        chat_title='Admin Group',
        status='approved',
        notification_enabled=True,
        agency=agency,
    )
    print(f"  Created and approved → agency: {agency.name}")
else:
    print(f"  Found: status={g.status} agency={g.agency_id} title={g.chat_title}")
    agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
    g.status = 'approved'
    g.notification_enabled = True
    g.agency = agency
    g.save()
    print(f"  Fixed: status=approved → agency: {agency.name} (id={agency.id})")

print("\nDone.")
