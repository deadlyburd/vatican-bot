"""
Hold Forever Test
=================
1. Finds an available guided tour slot
2. Recaps it (pure API)
3. Re-recaps every 4 minutes using same JSESSIONID
4. Logs hold duration + notifies admin on Telegram
5. Runs until you Ctrl+C or Vatican kills the session

Run: python hold_forever_test.py
     python hold_forever_test.py --date 15/06/2026 --visitors 2
"""
import sys, os, time, requests, json, argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()

BASE        = 'https://tickets.museivaticani.va'
BOT_TOKEN   = os.getenv('TELEGRAM_BOT_TOKEN', '')
ADMIN_CHAT  = os.getenv('ADMIN_TELEGRAM_IDS', '').split(',')[0].strip()
RE_RECAP_INTERVAL = 4 * 60   # 4 minutes

H = {
    'Accept': 'application/json, text/plain, */*',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE}/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Content-Type': 'application/json',
    'Origin': BASE,
}


def tg(text):
    if not BOT_TOKEN or not ADMIN_CHAT:
        return
    try:
        requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json={'chat_id': ADMIN_CHAT, 'text': text, 'parse_mode': 'HTML'},
            timeout=8
        )
    except Exception:
        pass


def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f'[{ts}] {msg}')


def find_slot(session, date, visitors, tag='MV-Visite-Guidate', lang='ENG'):
    """Find first available slot for given date/visitors."""
    r = session.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date,
        'area': '1', 'who': '', 'page': '0', 'tag': tag
    }, headers=H, timeout=10)
    if r.status_code != 200:
        return None
    for v in r.json().get('visits', []):
        if v.get('availability') in ('SOLD_OUT', 'NOT_ALLOWED'):
            continue
        tid = str(v['id'])
        tname = v.get('name', '')
        r2 = session.get(f'{BASE}/api/visit/timeavail', params={
            'lang': 'it', 'visitLang': lang, 'visitTypeId': tid,
            'visitorNum': str(visitors), 'visitDate': date,
        }, headers=H, timeout=8)
        for sl in r2.json().get('timetable', []):
            if sl.get('availability') == 'AVAILABLE':
                return {
                    'slot_id': sl['id'], 'time': sl['time'],
                    'ticket_id': tid, 'ticket_name': tname, 'lang': lang
                }
    return None


def do_recap(session, slot_id, ticket_id, visitors, lang=''):
    """Call /api/visit/recap. Returns (recap_id, total, jsessionid)."""
    # Get services
    services = []
    try:
        r = session.get(f'{BASE}/api/visit/services', params={
            'lang': 'it', 'visitId': slot_id, 'visitTypeId': ticket_id, 'visitorNum': str(visitors)
        }, headers=H, timeout=10)
        if r.status_code == 200:
            services = r.json().get('services', []) or []
    except Exception:
        pass

    body = {
        'visitId': str(slot_id),
        'visitTypeId': int(ticket_id),
        'visitorNum': int(visitors),
        'lang': 'it',
        'tickets': [
            {'id': 60, 'name': 'Biglietto Intero',  'price': 20, 'quantity': str(visitors)},
            {'id': 61, 'name': 'Biglietto Ridotto',  'price': 10, 'quantity': '0'},
        ],
        'additionalCosts': {},
        'services': []
    }
    for svc in services[:1]:
        body['additionalCosts']['service-0'] = {
            'id': svc.get('id', 58), 'name': svc.get('name', 'Diritti di Prevendita'),
            'price': svc.get('price', 5), 'quantity': int(visitors)
        }
        body['services'].append({
            'id': svc.get('id', 58), 'name': svc.get('name', 'Diritti di Prevendita'),
            'price': svc.get('price', 5), 'quantity': int(visitors)
        })

    r2 = session.post(f'{BASE}/api/visit/recap', json=body, headers=H, timeout=12)
    if r2.status_code != 200:
        return None, None, None
    data = r2.json()
    return (
        data.get('recapId') or data.get('id') or '',
        data.get('total', 0),
        session.cookies.get('JSESSIONID', '')
    )


def re_recap(session, slot_id, ticket_id, visitors, lang=''):
    """Re-recap using existing session to refresh hold."""
    # Refresh ticket_id via search first
    try:
        r = session.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(visitors), 'visitDate': TARGET_DATE,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Visite-Guidate'
        }, headers=H, timeout=10)
        if r.status_code == 200:
            fresh = next((v for v in r.json().get('visits', [])
                         if str(v['id']) == str(ticket_id) or
                         v.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')), None)
            if fresh:
                ticket_id = str(fresh['id'])
    except Exception:
        pass

    recap_id, total, jsid = do_recap(session, slot_id, ticket_id, visitors, lang)
    return recap_id, total, jsid


# ── Main ──────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument('--date',     default='15/06/2026')
parser.add_argument('--visitors', type=int, default=2)
parser.add_argument('--lang',     default='ENG')
args = parser.parse_args()

TARGET_DATE = args.date
VISITORS    = args.visitors
LANG        = args.lang

log(f'Hold Forever Test | {TARGET_DATE} | {VISITORS}v | lang={LANG}')
log(f'Re-recap interval: {RE_RECAP_INTERVAL//60} minutes')
log('Finding available slot...')

session = requests.Session()
slot = find_slot(session, TARGET_DATE, VISITORS, lang=LANG)

if not slot:
    log('❌ No available slot found. Try a different date or visitor count.')
    sys.exit(1)

log(f'✅ Found: {slot["time"]} | {slot["ticket_name"][:50]}')
log(f'   slot_id={slot["slot_id"]} ticket_id={slot["ticket_id"]}')
log('Recapping...')

recap_id, total, jsid = do_recap(session, slot['slot_id'], slot['ticket_id'], VISITORS, LANG)

if not recap_id or not jsid:
    log('❌ Initial recap failed.')
    sys.exit(1)

hold_start = time.time()
recap_count = 1
log(f'🔒 HELD! recapId={recap_id} €{total} JSESSIONID={jsid[:16]}...')

tg(
    f'🔒 <b>Hold Forever Test Started</b>\n'
    f'📅 {TARGET_DATE}  🕐 {slot["time"]}  👥 {VISITORS}v\n'
    f'🎟 {slot["ticket_name"][:50]}\n'
    f'💶 €{total}  recapId={recap_id}\n\n'
    f'Re-recapping every {RE_RECAP_INTERVAL//60} min. Will notify on each re-recap and on failure.'
)

print()
log('─' * 60)
log(f'Hold started. Re-recapping every {RE_RECAP_INTERVAL//60} min. Ctrl+C to stop.')
log('─' * 60)

try:
    while True:
        time.sleep(RE_RECAP_INTERVAL)

        elapsed_min = int((time.time() - hold_start) / 60)
        log(f'⏰ {elapsed_min} min elapsed — re-recapping #{recap_count + 1}...')

        new_recap_id, new_total, new_jsid = re_recap(
            session, slot['slot_id'], slot['ticket_id'], VISITORS, LANG
        )

        if new_recap_id:
            recap_count += 1
            if new_jsid:
                jsid = new_jsid
            log(f'✅ Re-recap #{recap_count} OK | recapId={new_recap_id} | held {elapsed_min} min total')
            tg(
                f'✅ <b>Re-recap #{recap_count}</b> — still holding!\n'
                f'📅 {TARGET_DATE}  🕐 {slot["time"]}  👥 {VISITORS}v\n'
                f'⏱ Held for <b>{elapsed_min} minutes</b>\n'
                f'🔑 recapId={new_recap_id}'
            )
        else:
            elapsed_min = int((time.time() - hold_start) / 60)
            log(f'❌ Re-recap FAILED after {elapsed_min} min | {recap_count} successful re-recaps')
            tg(
                f'❌ <b>Hold LOST after {elapsed_min} minutes</b>\n'
                f'📅 {TARGET_DATE}  🕐 {slot["time"]}  👥 {VISITORS}v\n'
                f'📊 Successful re-recaps: {recap_count}\n'
                f'Vatican killed the session at {elapsed_min} min mark.'
            )
            break

except KeyboardInterrupt:
    elapsed_min = int((time.time() - hold_start) / 60)
    log(f'\n⏹ Stopped manually after {elapsed_min} min | {recap_count} re-recaps')
    tg(
        f'⏹ <b>Hold test stopped manually</b>\n'
        f'📅 {TARGET_DATE}  🕐 {slot["time"]}  👥 {VISITORS}v\n'
        f'⏱ Held for <b>{elapsed_min} minutes</b>\n'
        f'📊 Re-recaps: {recap_count}'
    )
