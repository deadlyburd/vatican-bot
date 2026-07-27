"""
Send a browser button to WOR Bot WITHOUT recapping the slot.
The Playwright browser will do the full flow (search → recap → checkout).
"""
import os, sys, django, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.epay_ssl import make_vatican_session
from monitors.models import Agency, MonitorTask
from datetime import datetime, timedelta
import json, requests, base64

BASE = 'https://tickets.museivaticani.va'
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TRIGGER_CHAT_ID = ''  # WOR Bot

H_XHR = {
    'Accept': 'application/json, text/plain, */*',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE}/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}

VISITORS = 1
TARGET_TIME = '15:30'

# ── Find available May slot ───────────────────────────────────────────────────
print("Finding available May slot...")
s = make_vatican_session(use_proxy=True)
found = None

for days in range(1, 120):
    d = (datetime.now() + timedelta(days=days)).strftime('%d/%m/%Y')
    if '/05/' not in d:
        continue
    r = s.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': d,
        'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
    }, headers=H_XHR, timeout=10)
    if r.status_code != 200: continue
    ticket = next((v for v in r.json().get('visits', [])
                   if 'musei vaticani' in v.get('name','').lower()
                   and 'ingresso' in v.get('name','').lower()
                   and v.get('availability') in ('AVAILABLE','LOW_AVAILABILITY')), None)
    if not ticket: continue
    tid = ticket['id']
    r2 = s.get(f'{BASE}/api/visit/timeavail', params={
        'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
        'visitorNum': str(VISITORS), 'visitDate': d,
    }, headers=H_XHR, timeout=10)
    if r2.status_code != 200: continue
    slots = [sl for sl in r2.json().get('timetable', [])
             if sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')]
    if not slots: continue

    # Prefer afternoon slots near TARGET_TIME
    target_mins = int(TARGET_TIME.split(':')[0]) * 60 + int(TARGET_TIME.split(':')[1])
    afternoon = [sl for sl in slots if int(sl.get('time','00:00').split(':')[0]) >= 14]
    pool = afternoon if afternoon else slots
    exact = next((sl for sl in pool if sl.get('time') == TARGET_TIME), None)
    best = exact or min(pool, key=lambda sl: abs(
        int(sl['time'].split(':')[0])*60 + int(sl['time'].split(':')[1]) - target_mins
    ))
    found = {'date': d, 'tid': tid, 'slot': best}
    break
    time.sleep(0.05)

if not found:
    print("No available May slots"); sys.exit(1)

date, tid, slot = found['date'], found['tid'], found['slot']
slot_id, slot_time = str(slot['id']), slot['time']
print(f"Found: {date} {slot_time} (id={slot_id}) — NOT recapping, Playwright will do it")

# ── Send button WITHOUT recapping ─────────────────────────────────────────────
# Embed slot info so agent knows what to open
slot_info_b64 = base64.b64encode(
    f"{date}|{slot_time}|{slot_id}|{VISITORS}|25.0".encode()
).decode()
# Use open_browser_slot: format (no hold_id, agent does full flow)
button_data = f"open_browser_slot:{slot_info_b64}"

msg = (
    f"🎫 *TEST — Slot Available!*\n\n"
    f"📅 {date} {slot_time}\n"
    f"👥 {VISITORS} visitor\n\n"
    f"Click to open Chrome — browser will book it:"
)

print(f"\nSending button to WOR Bot ({TRIGGER_CHAT_ID})...")
r_tg = requests.post(
    f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
    json={
        'chat_id': TRIGGER_CHAT_ID,
        'text': msg,
        'parse_mode': 'Markdown',
        'reply_markup': json.dumps({'inline_keyboard': [[
            {'text': '🌐 Open Browser', 'callback_data': button_data}
        ]]})
    },
    timeout=10
)
print(f"Telegram: {r_tg.status_code}")
if r_tg.status_code == 200:
    print(f"✅ Button sent!")
    print(f"\nSlot: {date} {slot_time} — still AVAILABLE (not recapped)")
    print(f"Click [🌐 Open Browser] in WOR Bot → Chrome opens → browser recaps + books")
else:
    print(f"❌ {r_tg.text[:200]}")
