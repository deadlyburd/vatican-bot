"""
Find a real open slot from Vatican API and send a live notification
to all enabled groups for all active agencies.
"""
import os, sys, django, requests
sys.path.insert(0, '/app/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.core.cache import cache
from monitors.models import MonitorTask, TelegramGroup, Agency
from monitors.notification_utils import send_telegram_signal, format_vatican_notification
from datetime import date, timedelta

BASE = 'https://tickets.museivaticani.va'
H = {
    'Accept': 'application/json, text/plain, */*',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE}/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}

print("=== Scanning Vatican for a real open slot ===\n")

found_date = None
found_slots = []
found_ticket_id = None
found_ticket_name = None

# Scan next 60 days with 2 visitors
s = requests.Session()
today = date.today()
for i in range(1, 60):
    d = today + timedelta(days=i)
    if d.weekday() == 6:  # skip Sunday
        continue
    date_str = d.strftime('%d/%m/%Y')

    try:
        r = s.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': '2', 'visitDate': date_str,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=H, timeout=8)
        if r.status_code != 200:
            continue
        visits = r.json().get('visits', [])
        ticket = next((v for v in visits
                       if 'musei vaticani' in v.get('name', '').lower()
                       and 'ingresso' in v.get('name', '').lower()
                       and v.get('availability') == 'AVAILABLE'), None)
        if not ticket:
            continue

        tid = str(ticket['id'])
        jsessionid = s.cookies.get('JSESSIONID', '')

        r2 = s.get(f'{BASE}/api/visit/timeavail', params={
            'lang': 'it', 'visitLang': '', 'visitTypeId': tid,
            'visitorNum': '2', 'visitDate': date_str,
        }, headers={**H, 'Cookie': f'JSESSIONID={jsessionid}'}, timeout=8)
        if r2.status_code != 200:
            continue

        slots = [{'time': sl['time'], 'id': str(sl['id']), 'availability': sl['availability']}
                 for sl in r2.json().get('timetable', [])
                 if sl.get('availability') == 'AVAILABLE']

        if slots:
            found_date = date_str
            found_slots = slots
            found_ticket_id = tid
            found_ticket_name = ticket['name']
            print(f"✅ Found open date: {date_str} | {len(slots)} slots | ticket_id={tid}")
            print(f"   Ticket: {found_ticket_name}")
            print(f"   Slots: {[s['time'] for s in slots[:6]]}{'...' if len(slots)>6 else ''}")
            break
    except Exception as e:
        continue

if not found_date:
    print("❌ No open slots found in next 60 days")
    sys.exit(1)

print()
print("=== Sending live notifications to all enabled groups ===\n")

# Get all agencies with enabled groups
groups = TelegramGroup.objects.filter(status='approved', notification_enabled=True)
print(f"Enabled groups: {list(groups.values_list('chat_id', flat=True))}")
print()

sent_total = 0
for group in groups:
    # Find a matching task for this agency on this date (or use generic)
    task = MonitorTask.objects.filter(
        agency=group.agency, is_active=True, site='vatican'
    ).first()
    visitors = task.visitors if task else 2
    preferred = task.preferred_times if task else []

    msg = format_vatican_notification(
        date=found_date,
        ticket_name=found_ticket_name,
        ticket_id=found_ticket_id,
        slots=found_slots,
        preferred_times=preferred,
        language=None,
        visitors=visitors,
        check_method="live_test"
    )

    ok = send_telegram_signal(group.chat_id, msg)
    status = "✅ SENT" if ok else "❌ FAILED"
    print(f"{status} → {group.agency.name} | chat_id={group.chat_id}")
    if ok:
        sent_total += 1

print(f"\n=== Done: {sent_total}/{groups.count()} notifications sent ===")
