import os

"""
Fast Recap Scanner — Standard + Guided Tours
=============================================
Scans all dates in the next 2 months.
Recaps BOTH standard (MV-Biglietti) AND guided (MV-Visite-Guidate) tickets.
Live dashboard shows what's being recapped in real time.
Press Ctrl+C to pause — type slot IDs to skip/stop specific ones.

Run:
    python fast_recap_scanner.py                     # scan once + recap all
    python fast_recap_scanner.py --continuous        # keep scanning forever
    python fast_recap_scanner.py --status            # show all recapped slots
    python fast_recap_scanner.py --stop 42 55 60     # stop/release specific hold IDs
    python fast_recap_scanner.py --dry-run           # scan only, no recap
"""
import sys, os, time, json, requests, argparse, threading
from datetime import datetime, date, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()

from monitors.models import HeldSlot, MonitorTask, Agency
from django.utils import timezone

BASE = 'https://tickets.museivaticani.va'

# ── Telegram notifications ────────────────────────────────────────────────────
_BOT_TOKEN  = os.getenv('TELEGRAM_BOT_TOKEN', '')
_ADMIN_CHAT = os.getenv('ADMIN_TELEGRAM_IDS', '').split(',')[0].strip()

def tg_send(text):
    """Fire-and-forget Telegram message to admin. Never raises."""
    if not _BOT_TOKEN or not _ADMIN_CHAT:
        return
    try:
        requests.post(
            f'https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage',
            json={'chat_id': _ADMIN_CHAT, 'text': text, 'parse_mode': 'HTML'},
            timeout=8,
        )
    except Exception:
        pass

H = {
    'Accept': 'application/json, text/plain, */*',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE}/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Content-Type': 'application/json',
    'Origin': BASE,
}

AGENCY_NAME    = 'WOR'
SCAN_INTERVAL  = 30    # seconds between scans in continuous mode
GUIDED_LANGS   = ['ENG', 'ITA']   # guided tour languages to try
MAX_GUIDED_PER_DATE = 3  # max guided slots to recap per date
PRIORITY_DATES = ['15/06/2026']   # always scan these dates first

# ── June 15 09:30 / 20-pax watcher ───────────────────────────────────────────
_WATCH_DATE     = '15/06/2026'
_WATCH_TIME     = '09:30'
_WATCH_VISITORS = 20
_WATCH_INTERVAL = 15   # seconds between checks
_watch_notified = False  # flip to True once we alert so we don't spam


def _check_june15_0930():
    """
    Check timeavail for June 15 09:30 with 20 visitors.
    Returns list of available slot dicts if found, else empty list.
    """
    s = requests.Session()
    try:
        # Step 1: search API to get fresh ticket IDs + JSESSIONID
        r = s.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(_WATCH_VISITORS),
            'visitDate': _WATCH_DATE, 'area': '1', 'who': '', 'page': '0',
            'tag': 'MV-Visite-Guidate'
        }, headers=H, timeout=8)
        if r.status_code != 200:
            return []
        visits = r.json().get('visits', [])
        jsessionid = s.cookies.get('JSESSIONID', '')

        available = []
        for v in visits:
            if v.get('availability') in ('SOLD_OUT', 'NOT_ALLOWED'):
                continue
            tid = str(v['id'])
            tname = v.get('name', '')
            # Check each guided language
            for lang in ['ENG', 'ITA']:
                r2 = s.get(f'{BASE}/api/visit/timeavail', params={
                    'lang': 'it', 'visitLang': lang, 'visitTypeId': tid,
                    'visitorNum': str(_WATCH_VISITORS), 'visitDate': _WATCH_DATE,
                }, headers={**H, 'Cookie': f'JSESSIONID={jsessionid}'}, timeout=8)
                if r2.status_code != 200:
                    continue
                for sl in r2.json().get('timetable', []):
                    if sl.get('time') == _WATCH_TIME and sl.get('availability') == 'AVAILABLE':
                        available.append({
                            'slot_id': sl['id'], 'time': sl['time'],
                            'ticket_id': tid, 'ticket_name': tname, 'lang': lang
                        })
        return available
    except Exception:
        return []


_watch_already_recapped = False  # flips True after first recap — subsequent hits are notify-only


def _june15_watcher_loop():
    """
    Background thread: pings June 15 09:30 every 15s.
    First hit: recap + notify. After that: notify-only when slot becomes available again.
    """
    global _watch_notified, _watch_already_recapped
    log(f"👁️  Watcher started: {_WATCH_DATE} {_WATCH_TIME} | {_WATCH_VISITORS} pax | every {_WATCH_INTERVAL}s")
    tg_send(
        f"👁️ <b>Watcher active</b>\n"
        f"📅 {_WATCH_DATE}  🕐 {_WATCH_TIME}  👥 {_WATCH_VISITORS} pax\n"
        f"Pinging every {_WATCH_INTERVAL}s — recap on first hit, notify-only after."
    )
    while True:
        if not _watch_notified:
            slots = _check_june15_0930()
            if slots:
                recapped = []
                if not _watch_already_recapped:
                    for sl in slots:
                        try:
                            proxy = next_proxy()
                            rs = make_session_with_proxy(proxy)
                            try: rs.get(f'{BASE}/home', headers=H, timeout=8)
                            except Exception: pass
                            recap_id, total, jsessionid, ticketmv, serverid = do_recap(
                                rs, sl['slot_id'], sl['ticket_id'], _WATCH_VISITORS, sl['lang']
                            )
                            if recap_id and jsessionid:
                                from monitors.models import Agency, MonitorTask, HeldSlot
                                agency, _ = Agency.objects.get_or_create(
                                    name=AGENCY_NAME, defaults={'plan': 'agency', 'is_active': True}
                                )
                                task, _ = MonitorTask.objects.get_or_create(
                                    agency=agency,
                                    area_name="Musei Vaticani - Biglietti d'ingresso",
                                    defaults={
                                        'site': 'vatican', 'dates': [], 'preferred_times': [],
                                        'visitors': _WATCH_VISITORS, 'adult_count': _WATCH_VISITORS,
                                        'child_count': 0, 'tier': 'hold',
                                        'is_active': False, 'notification_mode': 'silent',
                                    }
                                )
                                held = HeldSlot.objects.create(
                                    task=task, date=_WATCH_DATE,
                                    slot_id=str(sl['slot_id']), slot_time=_WATCH_TIME,
                                    ticket_id=sl['ticket_id'], ticket_name=sl['ticket_name'],
                                    visitors=_WATCH_VISITORS, adult_count=_WATCH_VISITORS, child_count=0,
                                    total_price=total, jsessionid=jsessionid, ticketmv=ticketmv or '',
                                    recap_id=recap_id, status='held',
                                    notes=json.dumps({'visit_lang': sl['lang']}) if sl['lang'] else None,
                                )
                                recapped.append(f"#{held.id} {sl['ticket_name'][:40]} [{sl['lang']}] €{total}")
                                log(f"🔒 WATCHER RECAP: {_WATCH_DATE} {_WATCH_TIME} | #{held.id}", 'OK')
                        except Exception as e:
                            log(f"Watcher recap error: {e}", 'ERR')
                    _watch_already_recapped = True

                # Notify admin
                if recapped:
                    msg = (
                        f"🚨 <b>JUNE 15 09:30 — {_WATCH_VISITORS} PAX AVAILABLE!</b>\n\n"
                        f"📅 {_WATCH_DATE}  🕐 {_WATCH_TIME}  👥 {_WATCH_VISITORS} visitors\n\n"
                        f"✅ RECAPPED:\n" + '\n'.join(f"  🔒 {r}" for r in recapped) +
                        f"\n\n⚡ Slot locked!"
                    )
                else:
                    ticket_names = ', '.join(set(s['ticket_name'][:40] for s in slots))
                    msg = (
                        f"🔔 <b>JUNE 15 09:30 RELEASED — {_WATCH_VISITORS} PAX AVAILABLE!</b>\n\n"
                        f"📅 {_WATCH_DATE}  🕐 {_WATCH_TIME}  👥 {_WATCH_VISITORS} visitors\n"
                        f"🎟 {ticket_names}\n\n"
                        f"⚡ Book NOW on Vatican site — slot is open!"
                    )
                tg_send(msg)
                log(f"🚨 JUNE 15 09:30 {_WATCH_VISITORS}pax — notified admin.", 'OK')

                _watch_notified = True
                def _reset():
                    global _watch_notified
                    time.sleep(600)
                    _watch_notified = False
                    log(f"👁️  Watcher reset — checking {_WATCH_DATE} {_WATCH_TIME} again")
                threading.Thread(target=_reset, daemon=True).start()
            else:
                log(f"👁️  {_WATCH_DATE} {_WATCH_TIME} {_WATCH_VISITORS}pax — not available yet")
        time.sleep(_WATCH_INTERVAL)

# ── Rate limiting + Proxy rotation ───────────────────────────────────────────
# With proxy rotation each recap uses a different IP → no rate limit per IP
RECAP_DELAY        = 0.5   # seconds between recaps (fast with proxies)
SEARCH_DELAY       = 0.3   # seconds between search API calls
MAX_RECAPS_PER_RUN = 500   # high limit since proxies spread the load
USE_PROXIES        = True  # rotate through DB proxies for recap calls

# Proxy pool — loaded from DB at startup
_proxy_pool = []
_proxy_idx  = 0
_proxy_lock = threading.Lock()


def load_proxies():
    """Load active proxies from DB into rotation pool."""
    global _proxy_pool
    try:
        from monitors.models import Proxy
        proxies = list(Proxy.objects.filter(is_active=True).order_by('?'))
        _proxy_pool = []
        for p in proxies:
            if p.username and p.password:
                url = f"http://{p.username}:{p.password}@{p.ip_port}"
            else:
                url = f"http://{p.ip_port}"
            _proxy_pool.append(url)
        log(f"Loaded {len(_proxy_pool)} proxies for rotation")
    except Exception as e:
        log(f"Could not load proxies: {e} — using direct connection", 'ERR')
        _proxy_pool = []


def next_proxy():
    """Get next proxy in round-robin rotation. Returns None if no proxies."""
    global _proxy_idx
    if not USE_PROXIES or not _proxy_pool:
        return None
    with _proxy_lock:
        proxy = _proxy_pool[_proxy_idx % len(_proxy_pool)]
        _proxy_idx += 1
    return proxy


def make_session_with_proxy(proxy_url=None):
    """Create a requests session, optionally with a proxy."""
    s = requests.Session()
    if proxy_url:
        s.proxies = {'http': proxy_url, 'https': proxy_url}
    return s

# Ticket types to scan
TICKET_TYPES = [
    {'tag': 'MV-Biglietti',      'type': 'standard', 'label': 'Standard Entry'},
    {'tag': 'MV-Visite-Guidate', 'type': 'guided',   'label': 'Guided Tour'},
]

# ── Stats tracking ────────────────────────────────────────────────────────────
stats = {
    'scanned': 0, 'found': 0, 'recapped': 0, 'failed': 0,
    'skipped': 0, 'standard': 0, 'guided': 0,
    'current_date': '', 'current_type': '', 'start_time': time.time()
}
stats_lock = threading.Lock()
# Set of slot keys to skip: "date|time|type"
SKIP_KEYS = set()
# Timestamp of last summary notification sent [mutable list so inner functions can update]
_last_summary_sent = [0.0]


def log(msg, level='INFO'):
    prefix = {'INFO': '  ', 'OK': '✅', 'ERR': '❌', 'SKIP': '⏭️ ', 'NEW': '🔒'}
    p = prefix.get(level, '  ')
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {p} {msg}")


def print_dashboard():
    """Print live stats header."""
    elapsed = int(time.time() - stats['start_time'])
    m, s = divmod(elapsed, 60)
    print(f"\n{'━'*70}")
    print(f"  Vatican Recap Scanner  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'━'*70}")
    print(f"  Scanned: {stats['scanned']} dates  |  Found: {stats['found']} slots  |  "
          f"Recapped: {stats['recapped']} (std:{stats['standard']} guided:{stats['guided']})")
    print(f"  Failed: {stats['failed']}  |  Skipped: {stats['skipped']}  |  "
          f"Elapsed: {m}m{s:02d}s")
    if stats['current_date']:
        print(f"  Now scanning: {stats['current_date']} [{stats['current_type']}]")
    print(f"{'━'*70}\n")


def get_dates(months=3):
    today = date.today()
    end   = today + timedelta(days=months * 31)
    dates = []
    d = today + timedelta(days=1)
    while d <= end:
        if d.weekday() != 6:  # skip Sundays
            dates.append(d.strftime('%d/%m/%Y'))
        d += timedelta(days=1)
    # Put priority dates first so they're always recapped
    for pd in PRIORITY_DATES:
        if pd in dates:
            dates.remove(pd)
            dates.insert(0, pd)
    return dates


def already_recapped(agency, date_str, slot_time, visitors, ticket_type):
    return HeldSlot.objects.filter(
        task__agency=agency,
        date=date_str,
        slot_time=slot_time,
        visitors=visitors,
        status__in=['held', 'paying', 'paid'],
        ticket_name__icontains='guidat' if ticket_type == 'guided' else 'ingresso',
    ).exists()


def do_recap(session, slot_id, ticket_id, visitors, visit_lang=''):
    """Call /api/visit/recap once. Returns (recap_id, total, jsessionid, ticketmv, serverid)."""
    # Fetch services
    services = []
    try:
        r = session.get(f'{BASE}/api/visit/services', params={
            'lang': 'it', 'visitId': slot_id,
            'visitTypeId': ticket_id, 'visitorNum': str(visitors)
        }, headers=H, timeout=10)
        if r.status_code == 200:
            services = r.json().get('services', []) or []
    except Exception:
        pass

    body = {
        "visitId": str(slot_id),
        "visitTypeId": int(ticket_id),
        "visitorNum": int(visitors),
        "lang": "it",
        "tickets": [
            {"id": 60, "name": "Biglietto Intero",  "price": 20, "quantity": str(visitors)},
            {"id": 61, "name": "Biglietto Ridotto",  "price": 10, "quantity": "0"},
        ],
        "additionalCosts": {},
        "services": []
    }
    for svc in services[:1]:
        body["additionalCosts"]["service-0"] = {
            "id": svc.get('id', 58), "name": svc.get('name', 'Diritti di Prevendita'),
            "price": svc.get('price', 5), "quantity": int(visitors)
        }
        body["services"].append({
            "id": svc.get('id', 58), "name": svc.get('name', 'Diritti di Prevendita'),
            "price": svc.get('price', 5), "quantity": int(visitors)
        })

    try:
        r2 = session.post(f'{BASE}/api/visit/recap', json=body, headers=H, timeout=12)
        if r2.status_code != 200:
            return None, None, None, None, None
        data = r2.json()
        return (
            data.get('recapId') or data.get('id') or '',
            data.get('total', 0),
            session.cookies.get('JSESSIONID', ''),
            session.cookies.get('ticketmv', ''),
            session.cookies.get('SERVERID', ''),
        )
    except Exception as e:
        return None, None, None, None, None


def check_slot_blocked(session, slot_id, ticket_id, visitors, visit_lang, date_str):
    """
    Verify the recap actually blocked the slot.
    Re-calls timeavail and checks if our slot_id is now SOLD_OUT or gone.
    Returns True if blocked, False if still AVAILABLE (recap didn't hold it).
    """
    try:
        r = session.get(f'{BASE}/api/visit/timeavail', params={
            'lang': 'it', 'visitLang': visit_lang, 'visitTypeId': ticket_id,
            'visitorNum': str(visitors), 'visitDate': date_str,
        }, headers=H, timeout=8)
        if r.status_code != 200:
            return None  # Can't verify
        timetable = r.json().get('timetable', [])
        for sl in timetable:
            if str(sl.get('id')) == str(slot_id):
                avail = sl.get('availability', '')
                return avail != 'AVAILABLE'  # True = blocked
        # Slot not in response at all → treated as blocked
        return True
    except Exception:
        return None  # Can't verify


def scan_ticket_type(s, date_str, ticket_cfg, visitors, agency, task, dry_run):
    """Scan one ticket type (standard or guided) for a date. Returns new recap count."""
    tag         = ticket_cfg['tag']
    ttype       = ticket_cfg['type']
    label       = ticket_cfg['label']
    new_recaps  = 0
    guided_count = 0

    with stats_lock:
        stats['current_type'] = label

    # Search API
    try:
        r = s.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date_str,
            'area': '1', 'who': '', 'page': '0', 'tag': tag
        }, headers=H, timeout=8)
        if r.status_code != 200:
            return 0
        visits = r.json().get('visits', [])
    except Exception:
        return 0

    # Filter relevant tickets
    if ttype == 'standard':
        tickets = [v for v in visits
                   if 'musei vaticani' in v.get('name', '').lower()
                   and 'ingresso' in v.get('name', '').lower()
                   and v.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')]
    else:
        tickets = [v for v in visits
                   if v.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')]

    if not tickets:
        return 0

    for ticket in tickets:
        tid = str(ticket['id'])
        tname = ticket.get('name', label)
        visit_lang = ''

        # For guided tours, try each language
        langs_to_try = GUIDED_LANGS if ttype == 'guided' else ['']

        for lang in langs_to_try:
            if ttype == 'guided' and guided_count >= MAX_GUIDED_PER_DATE:
                break

            try:
                r2 = s.get(f'{BASE}/api/visit/timeavail', params={
                    'lang': 'it', 'visitLang': lang, 'visitTypeId': tid,
                    'visitorNum': str(visitors), 'visitDate': date_str,
                }, headers=H, timeout=8)
                if r2.status_code != 200:
                    continue
                available = [sl for sl in r2.json().get('timetable', [])
                             if sl.get('availability') == 'AVAILABLE']
            except Exception:
                continue

            if not available:
                continue

            with stats_lock:
                stats['found'] += len(available)

            for sl in available:
                slot_id   = str(sl['id'])
                slot_time = sl['time']
                skip_key  = f"{date_str}|{slot_time}|{ttype}"

                if skip_key in SKIP_KEYS:
                    with stats_lock: stats['skipped'] += 1
                    log(f"{date_str} {slot_time} [{label}] — SKIPPED by user", 'SKIP')
                    continue

                if already_recapped(agency, date_str, slot_time, visitors, ttype):
                    with stats_lock: stats['skipped'] += 1
                    continue

                if dry_run:
                    log(f"{date_str} {slot_time} [{label}] lang={lang} — would recap", 'NEW')
                    continue

                # Fresh session with next proxy for clean JSESSIONID + different IP
                proxy = next_proxy()
                rs = make_session_with_proxy(proxy)
                try: rs.get(f'{BASE}/home', headers=H, timeout=8)
                except Exception: pass

                recap_id, total, jsessionid, ticketmv, serverid = do_recap(
                    rs, slot_id, tid, visitors, lang)

                if not recap_id or not jsessionid:
                    with stats_lock: stats['failed'] += 1
                    log(f"{date_str} {slot_time} [{label}] — recap FAILED", 'ERR')
                    continue

                notes = json.dumps({'serverid': serverid, 'visit_lang': lang}) if serverid else \
                        json.dumps({'visit_lang': lang}) if lang else None

                held = HeldSlot.objects.create(
                    task=task,
                    date=date_str,
                    slot_id=slot_id,
                    slot_time=slot_time,
                    ticket_id=tid,
                    ticket_name=tname,
                    visitors=visitors,
                    adult_count=visitors,
                    child_count=0,
                    total_price=total,
                    jsessionid=jsessionid,
                    ticketmv=ticketmv or '',
                    recap_id=recap_id,
                    status='held',
                    notes=notes,
                )

                with stats_lock:
                    stats['recapped'] += 1
                    if ttype == 'guided': stats['guided'] += 1
                    else: stats['standard'] += 1

                log(f"{date_str} {slot_time} [{label}] lang={lang} | "
                    f"#{held.id} recapId={recap_id} €{total} proxy={'yes' if proxy else 'direct'}", 'NEW')

                # ── Blocking check ────────────────────────────────────────
                time.sleep(1.2)  # brief pause so Vatican registers the hold
                blocked = check_slot_blocked(rs, slot_id, tid, visitors, lang, date_str)
                if blocked is False:
                    log(f"{date_str} {slot_time} [{label}] — slot still AVAILABLE after recap!", 'ERR')

                # No per-recap notification — summary sent at end of scan cycle
                new_recaps += 1
                guided_count += 1

                # With proxies: minimal delay. Without: 3s to avoid rate limit
                delay = RECAP_DELAY if USE_PROXIES and _proxy_pool else 3.0
                time.sleep(delay)

    return new_recaps


def scan_and_recap(visitors=2, dry_run=False, dates=None):
    # Get or auto-create the scanner agency so it never fails on missing agency
    agency, created = Agency.objects.get_or_create(
        name=AGENCY_NAME,
        defaults={'plan': 'agency', 'is_active': True}
    )
    if created:
        log(f"Auto-created agency '{AGENCY_NAME}' for recap scanner", 'OK')

    task, _ = MonitorTask.objects.get_or_create(
        agency=agency,
        area_name="Musei Vaticani - Biglietti d'ingresso",
        defaults={
            'site': 'vatican', 'dates': [], 'preferred_times': [],
            'visitors': visitors, 'adult_count': visitors, 'child_count': 0,
            'tier': 'hold',
            'is_active': False,          # ← MUST be False: orchestrator must NOT pick this up
            'notification_mode': 'silent', # ← no notifications ever
        }
    )
    # Ensure existing task is also silenced (in case it was created before this fix)
    if task.is_active or task.notification_mode != 'silent':
        task.is_active = False
        task.notification_mode = 'silent'
        task.save(update_fields=['is_active', 'notification_mode'])

    if dates is None:
        dates = get_dates(months=2)

    total_new = 0
    s = requests.Session()

    for date_str in dates:
        with stats_lock:
            stats['scanned'] += 1
            stats['current_date'] = date_str

        sys.stdout.write(f"\r  Scanning {date_str}...                    ")
        sys.stdout.flush()

        for ticket_cfg in TICKET_TYPES:
            n = scan_ticket_type(s, date_str, ticket_cfg, visitors, agency, task, dry_run)
            total_new += n

        time.sleep(0.15)

    sys.stdout.write('\r' + ' '*60 + '\r')

    # Send scan summary — at most once every 10 minutes, only when new recaps found
    if total_new > 0:
        now_ts = time.time()
        if now_ts - _last_summary_sent[0] >= 600:   # 10 min cooldown
            _last_summary_sent[0] = now_ts
            with stats_lock:
                tg_send(
                    f"📊 <b>Recap Scan Summary</b>\n"
                    f"🔒 New recaps: {total_new} "
                    f"(std: {stats['standard']} | guided: {stats['guided']})\n"
                    f"📅 Dates scanned: {stats['scanned']}  |  Found: {stats['found']} slots\n"
                    f"❌ Failed: {stats['failed']}"
                )

    return total_new


def stop_holds(hold_ids):
    """Release specific holds by ID."""
    for hid in hold_ids:
        try:
            hs = HeldSlot.objects.get(id=hid)
            hs.status = 'released'
            hs.released_at = timezone.now()
            hs.save(update_fields=['status', 'released_at'])
            log(f"Released Hold #{hid} | {hs.date} {hs.slot_time}", 'OK')
        except HeldSlot.DoesNotExist:
            log(f"Hold #{hid} not found", 'ERR')


def skip_slot(date_str, slot_time, ttype='standard'):
    """Add a slot to the skip list so it won't be recapped."""
    key = f"{date_str}|{slot_time}|{ttype}"
    SKIP_KEYS.add(key)
    log(f"Added to skip list: {key}", 'SKIP')


def show_status():
    agency, _ = Agency.objects.get_or_create(
        name=AGENCY_NAME,
        defaults={'plan': 'agency', 'is_active': True}
    )

    slots = HeldSlot.objects.filter(
        task__agency=agency,
        status__in=['held', 'paying', 'paid']
    ).order_by('date', 'slot_time')

    std     = slots.filter(ticket_name__icontains='ingresso').count()
    guided  = slots.exclude(ticket_name__icontains='ingresso').count()

    print(f"\n{'━'*75}")
    print(f"  RECAPPED SLOTS — {AGENCY_NAME}  "
          f"({slots.count()} total | {std} standard | {guided} guided)")
    print(f"{'━'*75}")
    for hs in slots:
        age  = int((timezone.now() - hs.hold_started_at).total_seconds() / 3600)
        kind = 'GUIDED' if 'guidat' in hs.ticket_name.lower() else 'STD   '
        print(f"  #{hs.id:4d} | {hs.date} {hs.slot_time} | {kind} | "
              f"{hs.visitors}v | €{hs.total_price} | age={age}h | "
              f"recapId={hs.recap_id} | {hs.status}")
    print(f"{'━'*75}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Vatican Recap Scanner')
    parser.add_argument('--visitors',   type=int, default=2)
    parser.add_argument('--dry-run',    action='store_true')
    parser.add_argument('--status',     action='store_true')
    parser.add_argument('--continuous', action='store_true',
                        help=f'Keep scanning every {SCAN_INTERVAL}s')
    parser.add_argument('--stop',       nargs='+', type=int, metavar='ID',
                        help='Release specific hold IDs')
    parser.add_argument('--skip',       nargs='+', metavar='DATE|TIME|TYPE',
                        help='Skip specific slots e.g. 15/06/2026|08:00|standard')
    args = parser.parse_args()

    if args.status:
        show_status()

    elif args.stop:
        stop_holds(args.stop)

    elif args.skip:
        for s in args.skip:
            parts = s.split('|')
            if len(parts) == 3:
                skip_slot(parts[0], parts[1], parts[2])
            else:
                log(f"Invalid skip format: {s} (use DATE|TIME|TYPE)", 'ERR')

    elif args.continuous:
        print_dashboard()
        log(f"🔄 Continuous scan — {args.visitors}v | interval={SCAN_INTERVAL}s")
        log(f"   Scanning standard + guided tickets for next 2 months")
        log(f"   Press Ctrl+C to stop\n")
        tg_send(f"🚀 <b>Recap Scanner started</b>\n👥 {args.visitors}v | interval={SCAN_INTERVAL}s | continuous mode")

        # Start June 15 09:30 watcher in background
        watcher = threading.Thread(target=_june15_watcher_loop, daemon=True)
        watcher.start()

        scan_num = 0
        while True:
            scan_num += 1
            log(f"=== Scan #{scan_num} ===")
            n = scan_and_recap(args.visitors, dry_run=args.dry_run)
            print_dashboard()
            log(f"Scan #{scan_num} done: {n} new recaps. Next in {SCAN_INTERVAL}s...")
            time.sleep(SCAN_INTERVAL)

    else:
        print_dashboard()
        log(f"Scanning next 2 months | {args.visitors}v | standard + guided")
        n = scan_and_recap(args.visitors, dry_run=args.dry_run)
        print_dashboard()
        log(f"Done. {n} new recaps.")
        show_status()
