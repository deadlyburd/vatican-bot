"""
Vatican Slot Sniper — Open Browser on Release
==============================================
Monitors 3 target windows via Search API.
As soon as a slot appears → opens Chrome, navigates to checkout, fills form.
Recaps every 4 minutes to keep the hold alive.

Target windows:
  • 15 May  2026  08:00–10:30  (any slot)
  • 15 June 2026  08:00–10:30  (any slot)
  • 29 April 2026 08:00–12:00  (any slot)

Run:
    python snipe_open_browser.py
    python snipe_open_browser.py --visitors 2
    python snipe_open_browser.py --poll 5   # poll every 5 seconds
"""
import asyncio
import json
import os
import sys
import time
import requests
import subprocess
import logging
import argparse
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────────────────────
CHROME_PATH    = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
BASE_PROFILE   = r'C:\Users\wonde\vatican_snipe_'
BASE_DEBUG_PORT = 9300   # each session gets its own port: 9300, 9301, ...
HEARTBEAT_SECS = 240     # recap every 4 minutes
POLL_INTERVAL  = 8       # seconds between availability checks
VISITORS       = 6       # Vatican max per API call is 6; override with --visitors
BASE           = 'https://tickets.museivaticani.va'
USER_AGENT     = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/146.0.7680.178 Safari/537.36')

# Load profile from agent_config.json if present
def _load_profile():
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent_config.json')
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path) as f:
                c = json.load(f)
            return {
                'first_name':  c.get('first_name',  'Mario'),
                'last_name':   c.get('last_name',   'Rossi'),
                'email':       c.get('email',       'mario.rossi@example.com'),
                'phone':       c.get('phone',       '3401234567'),
                'city':        c.get('city',        'Roma'),
                'country':     c.get('country',     'Italy'),
                'gender':      c.get('gender',      'M'),
                'birth_year':  str(c.get('birth_year',  1990)),
                'birth_month': str(c.get('birth_month', 'GEN')),
                'birth_day':   str(c.get('birth_day',   15)),
            }
        except Exception:
            pass
    return {
        'first_name': 'Mario', 'last_name': 'Rossi',
        'email': 'mario.rossi@example.com', 'phone': '3401234567',
        'city': 'Roma', 'country': 'Italy', 'gender': 'M',
        'birth_year': '1990', 'birth_month': 'GEN', 'birth_day': '15',
    }

PROFILE = _load_profile()

# ── TARGET WINDOWS ────────────────────────────────────────────────────────────
# Each entry: date DD/MM/YYYY, earliest/latest time (inclusive), visitors
TARGETS = [
    {'date': '29/04/2026', 'from': '08:00', 'to': '12:00', 'visitors': VISITORS},
    {'date': '15/05/2026', 'from': '08:00', 'to': '10:30', 'visitors': VISITORS},
    {'date': '15/06/2026', 'from': '08:00', 'to': '10:30', 'visitors': VISITORS},
]

HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE}/',
    'User-Agent': USER_AGENT,
    'Accept-Language': 'it-IT,it;q=0.9,en;q=0.8',
    'Origin': BASE,
}

# ── State ─────────────────────────────────────────────────────────────────────
# Keys already opened in a browser so we don't double-open
_opened: set = set()
_opened_lock = threading.Lock()


def time_in_window(slot_time: str, from_time: str, to_time: str) -> bool:
    """Return True if slot_time (HH:MM) is within [from_time, to_time]."""
    def mins(t):
        h, m = t.split(':')
        return int(h) * 60 + int(m)
    return mins(from_time) <= mins(slot_time) <= mins(to_time)


def rome_ts(date_str: str) -> int:
    """Convert DD/MM/YYYY to Vatican timestamp (ms, Rome midnight)."""
    d, m, y = date_str.split('/')
    rome = ZoneInfo('Europe/Rome')
    dt = datetime(int(y), int(m), int(d), 0, 0, 0, tzinfo=rome)
    return int(dt.timestamp() * 1000)


def search_and_timeavail(target: dict) -> list:
    """
    Step 1: Search API → fresh ticket IDs + JSESSIONID
    Step 2: timeavail → available slots in window
    Returns list of slot dicts.
    """
    date_str = target['date']
    visitors = target['visitors']
    s = requests.Session()

    # Step 1 — Search API
    try:
        r = s.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date_str,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti',
        }, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return []
        visits = r.json().get('visits', [])
    except Exception as e:
        log.debug(f"Search API error {date_str}: {e}")
        return []

    jsessionid = s.cookies.get('JSESSIONID', '')

    # Match standard entry ticket
    ticket = next((
        v for v in visits
        if 'musei vaticani' in v.get('name', '').lower()
        and 'ingresso' in v.get('name', '').lower()
        and v.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')
    ), None)

    if not ticket:
        return []

    tid = str(ticket['id'])
    tname = ticket.get('name', 'Musei Vaticani')

    # Step 2 — timeavail
    try:
        r2 = s.get(f'{BASE}/api/visit/timeavail', params={
            'lang': 'it', 'visitLang': '', 'visitTypeId': tid,
            'visitorNum': str(visitors), 'visitDate': date_str,
        }, headers={**HEADERS, 'Cookie': f'JSESSIONID={jsessionid}'}, timeout=8)
        if r2.status_code != 200:
            return []
        timetable = r2.json().get('timetable', [])
    except Exception as e:
        log.debug(f"Timeavail error {date_str}: {e}")
        return []

    slots = []
    for sl in timetable:
        if sl.get('availability') != 'AVAILABLE':
            continue
        t = sl.get('time', '')
        if not time_in_window(t, target['from'], target['to']):
            continue
        slots.append({
            'date':       date_str,
            'slot_id':    str(sl['id']),
            'slot_time':  t,
            'ticket_id':  tid,
            'ticket_name': tname,
            'visitors':   visitors,
            'jsessionid': jsessionid,
        })
    return slots


# ── Browser session ───────────────────────────────────────────────────────────

async def open_browser_session(session_idx: int, slot: dict):
    """
    Open Chrome, navigate to Vatican checkout, fill form, start heartbeat.
    Keeps the hold alive by recapping every HEARTBEAT_SECS seconds.
    """
    from playwright.async_api import async_playwright

    port    = BASE_DEBUG_PORT + session_idx
    profile = f"{BASE_PROFILE}{session_idx}"
    label   = f"[{slot['date']} {slot['slot_time']}]"

    def llog(msg):
        log.info(f"{label} {msg}")

    llog(f"🚀 Opening Chrome (port={port})...")

    chrome_cmd = [
        CHROME_PATH,
        f'--remote-debugging-port={port}',
        f'--user-data-dir={profile}',
        '--profile-directory=Default',
        '--no-first-run',
        '--no-default-browser-check',
        '--start-maximized',
        '--disable-blink-features=AutomationControlled',
        '--ignore-gpu-blocklist',
        '--enable-webgl',
        '--enable-accelerated-2d-canvas',
        f'--user-agent={USER_AGENT}',
        'about:blank',
    ]
    subprocess.Popen(
        chrome_cmd,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    await asyncio.sleep(3 + session_idx * 1.5)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(f'http://localhost:{port}')
        except Exception as e:
            llog(f"❌ CDP connect failed: {e}")
            return

        ctx = (browser.contexts[0] if browser.contexts
               else await browser.new_context(
                   locale='it-IT', timezone_id='Europe/Rome',
                   user_agent=USER_AGENT, ignore_https_errors=True))
        page = await ctx.new_page()

        date_str  = slot['date']
        slot_time = slot['slot_time']
        slot_id   = slot['slot_id']
        tid       = slot['ticket_id']
        visitors  = slot['visitors']
        ts        = rome_ts(date_str)
        entry_url = f"{BASE}/home/fromtag/{visitors}/{ts}/MV-Biglietti/1"

        # [1] Navigate
        llog(f"[1] {entry_url}")
        await page.goto(entry_url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(4000)

        # [2] Resolve fresh ticket_id from Search API (via page context for cookies)
        llog("[2] Resolving fresh ticket_id...")
        r = await page.request.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date_str,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti',
        }, headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'})
        visits = (await r.json()).get('visits', [])
        fresh = next((v for v in visits
                      if 'musei vaticani' in v.get('name', '').lower()
                      and 'ingresso' in v.get('name', '').lower()), None)
        if fresh:
            tid = str(fresh['id'])
        llog(f"   ticket_id={tid}")

        # [3] Click PRENOTA
        llog(f"[3] bookTicket_{tid}")
        try:
            await page.wait_for_selector(f"[data-cy='bookTicket_{tid}']", timeout=10000)
            await page.click(f"[data-cy='bookTicket_{tid}']")
            await page.wait_for_timeout(2000)
        except Exception as e:
            llog(f"   bookTicket fallback: {e}")
            await page.evaluate(f"document.querySelector(\"[data-cy='bookTicket_{tid}']\")?.click()")
            await page.wait_for_timeout(2000)

        # [4] Quantity
        llog(f"[4] quantity={visitors}")
        try:
            await page.wait_for_selector("[data-cy='ticketQuantity']", timeout=8000)
            await page.click("[data-cy='ticketQuantity']")
            await page.wait_for_timeout(600)
            await page.evaluate(f"""
                () => {{
                    const items = Array.from(document.querySelectorAll("[data-cy='ticketQuantitySection']"));
                    const match = items.find(el => el.innerText.trim() === '{visitors}');
                    if (match) match.click();
                    else if (items.length >= {visitors}) items[{visitors}-1].click();
                    else if (items.length > 0) items[items.length-1].click();
                }}
            """)
            await page.wait_for_timeout(800)
        except Exception as e:
            llog(f"   quantity error: {e}")

        # [5] Select time slot
        llog(f"[5] time={slot_time}")
        try:
            await page.wait_for_timeout(1500)
            clicked = await page.evaluate(f"""
                () => {{
                    for (const cell of document.querySelectorAll("[data-cy='time']")) {{
                        const num = cell.querySelector('div.muvaCalendarNumber');
                        const txt = num ? num.innerText.trim() : cell.innerText.trim().split('\\n')[0];
                        if (txt === '{slot_time}') {{ cell.scrollIntoView(); cell.click(); return txt; }}
                    }}
                    return null;
                }}
            """)
            if not clicked:
                # Try afternoon tab
                await page.evaluate("""() => {
                    const tabs = document.querySelectorAll('div.showGTMobile > div > div');
                    if (tabs.length >= 2) tabs[1].click();
                }""")
                await page.wait_for_timeout(800)
                await page.evaluate(f"""
                    () => {{
                        for (const cell of document.querySelectorAll("[data-cy='time']")) {{
                            const txt = cell.innerText.trim().split('\\n')[0];
                            if (txt === '{slot_time}') {{ cell.scrollIntoView(); cell.click(); return; }}
                        }}
                    }}
                """)
            llog(f"   time clicked: {clicked or slot_time}")
            await page.wait_for_timeout(1500)
        except Exception as e:
            llog(f"   time error: {e}")

        # [6] PROCEDI
        llog("[6] PROCEDI")
        try:
            await page.wait_for_selector("[data-cy='bookVisit']", timeout=15000)
            await page.click("[data-cy='bookVisit']")
            await page.wait_for_timeout(5000)
        except Exception as e:
            llog(f"   PROCEDI fallback: {e}")
            await page.evaluate("document.querySelector(\"[data-cy='bookVisit']\")?.click()")
            await page.wait_for_timeout(5000)

        # [7] Fill checkout form
        llog("[7] Filling form...")
        try:
            await page.wait_for_selector("[data-cy='managerSurname']", timeout=20000)
        except Exception:
            llog("   ⚠️ Form not found — browser stays open for manual action")
            while True:
                await asyncio.sleep(60)

        async def fill(sel, val):
            try:
                safe = str(val).replace('`', '\\`')
                await page.evaluate(f"""
                    () => {{
                        const el = document.querySelector(`{sel}`);
                        if (!el) return;
                        el.focus(); el.value = ''; el.value = `{safe}`;
                        el.dispatchEvent(new Event('input',  {{bubbles: true}}));
                        el.dispatchEvent(new Event('change', {{bubbles: true}}));
                        el.blur();
                    }}
                """)
            except Exception:
                pass

        await fill("[data-cy='managerSurname']",     PROFILE['last_name'])
        await fill("[data-cy='managerName']",         PROFILE['first_name'])
        await fill("[data-cy='managerCity']",         PROFILE['city'])
        await fill("[data-cy='managerEmail']",        PROFILE['email'])
        await fill("[data-cy='managerConfirmEmail']", PROFILE['email'])
        await fill("[data-cy='managerPhone']",        PROFILE['phone'])

        # Gender
        try:
            await page.click("[data-cy='managerSex']"); await page.wait_for_timeout(300)
            await page.click("[data-cy='managerSexSection']"); await page.wait_for_timeout(300)
        except Exception: pass

        # Country
        try:
            await page.click("[data-cy='managerCountry']"); await page.wait_for_timeout(300)
            await page.evaluate("""() => {
                const items = Array.from(document.querySelectorAll("[data-cy='managerCountrySection']"));
                const italy = items.find(el => /ital/i.test(el.innerText));
                if (italy) italy.click(); else if (items[0]) items[0].click();
            }""")
            await page.wait_for_timeout(300)
        except Exception: pass

        # Birth date — try direct input first
        b_display = f"{PROFILE['birth_day'].zfill(2)}/01/{PROFILE['birth_year']}"
        set_ok = await page.evaluate(f"""
            () => {{
                const inp = document.querySelector("[data-cy='dateCalendar']");
                if (!inp) return false;
                inp.removeAttribute('readonly');
                inp.focus(); inp.value = '{b_display}';
                inp.dispatchEvent(new Event('input',  {{bubbles: true}}));
                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                inp.setAttribute('readonly', 'true');
                return !!inp.value;
            }}
        """)
        await page.wait_for_timeout(400)

        # Language
        try:
            await page.click("[data-cy='managerLanguage']"); await page.wait_for_timeout(300)
            await page.click("[data-cy='managerLanguageSection']"); await page.wait_for_timeout(300)
        except Exception: pass

        # Participants
        for i in range(visitors):
            try:
                if i > 0:
                    acc = await page.query_selector(f"#participantElement_{i} div.tw-flex-grow > div")
                    if acc: await acc.click(); await page.wait_for_timeout(400)
                await fill(f"#participantSurname_{i}", PROFILE['last_name'])
                await fill(f"#participantName_{i}",    PROFILE['first_name'])
            except Exception: pass

        # GDPR checkboxes
        try:
            cb1 = await page.query_selector("#mat-mdc-checkbox-1-input")
            if cb1 and not await cb1.is_checked():
                await cb1.click(); await page.wait_for_timeout(1000)
                close = await page.query_selector("[data-cy='purchase-rules-close-btn']")
                if close: await close.click(); await page.wait_for_timeout(600)
        except Exception: pass
        try:
            for sel in ["#mat-mdc-checkbox-3-input", "#mat-mdc-checkbox-4-input"]:
                cb = await page.query_selector(sel)
                if cb and not await cb.is_checked():
                    await cb.click(); await page.wait_for_timeout(300)
        except Exception: pass

        llog(f"✅ FORM FILLED — heartbeat every {HEARTBEAT_SECS}s (recap to keep hold alive)")

        # [8] Heartbeat — recap every 4 minutes to keep hold alive
        await page.evaluate("""
            (args) => {
                const { slot_id, ticket_id, visitors, heartbeat_ms } = args;
                window._hb = setInterval(() => {
                    fetch('/api/visit/recap', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({
                            visitId: slot_id,
                            visitTypeId: parseInt(ticket_id),
                            visitorNum: parseInt(visitors),
                            lang: 'it',
                            tickets: [
                                { id: 60, name: 'Biglietto Intero',  price: 20, quantity: String(visitors) },
                                { id: 61, name: 'Biglietto Ridotto', price: 10, quantity: '0' }
                            ],
                            additionalCosts: {
                                'service-0': { id: 58, name: 'Diritti di Prevendita', price: 5, quantity: parseInt(visitors) }
                            },
                            services: [{ id: 58, name: 'Diritti di Prevendita', price: 5, quantity: parseInt(visitors) }]
                        })
                    })
                    .then(r => console.log('♻️ HB', r.status, new Date().toLocaleTimeString()))
                    .catch(e => console.log('HB err', e));
                }, heartbeat_ms);

                // Keep checkboxes ticked
                window._cbfix = setInterval(() => {
                    const cb1 = document.querySelector('#mat-mdc-checkbox-1-input');
                    if (cb1 && !cb1.checked) {
                        cb1.click();
                        setTimeout(() => {
                            const c = document.querySelector("[data-cy='purchase-rules-close-btn']");
                            if (c) c.click();
                        }, 800);
                    }
                    ['#mat-mdc-checkbox-3-input','#mat-mdc-checkbox-4-input'].forEach(s => {
                        const cb = document.querySelector(s);
                        if (cb && !cb.checked) cb.click();
                    });
                }, 30000);
            }
        """, {
            'slot_id':     slot_id,
            'ticket_id':   tid,
            'visitors':    str(visitors),
            'heartbeat_ms': HEARTBEAT_SECS * 1000,
        })

        # Keep Python alive — Chrome is detached and will survive
        start = time.time()
        while True:
            elapsed = (time.time() - start) / 60
            llog(f"⏱️  ACTIVE {elapsed:.1f} min — solve Turnstile and click ACQUISTA to complete")
            await asyncio.sleep(60)


# ── Monitor loop ──────────────────────────────────────────────────────────────

async def monitor_loop(poll_interval: int):
    """Poll all targets. Open a browser session the moment a slot appears."""
    session_counter = 0
    tasks = []

    log.info("=" * 60)
    log.info("Vatican Slot Sniper — waiting for slots to open")
    log.info("=" * 60)
    for t in TARGETS:
        log.info(f"  🎯 {t['date']}  {t['from']}–{t['to']}  ({t['visitors']}v)")
    log.info(f"  Poll interval: {poll_interval}s | Heartbeat: {HEARTBEAT_SECS}s")
    log.info("=" * 60)

    while True:
        for target in TARGETS:
            slots = search_and_timeavail(target)
            for slot in slots:
                key = f"{slot['date']}|{slot['slot_time']}"
                with _opened_lock:
                    if key in _opened:
                        continue
                    _opened.add(key)

                log.info(f"🔥 SLOT FOUND: {slot['date']} {slot['slot_time']} — opening browser #{session_counter}")
                idx = session_counter
                session_counter += 1
                task = asyncio.create_task(open_browser_session(idx, slot))
                tasks.append(task)

            if not slots:
                log.debug(f"  {target['date']} {target['from']}–{target['to']} — no slots yet")

        await asyncio.sleep(poll_interval)


def main():
    parser = argparse.ArgumentParser(description='Vatican Slot Sniper')
    parser.add_argument('--visitors', type=int, default=VISITORS,
                        help='Number of visitors (default: 2)')
    parser.add_argument('--poll', type=int, default=POLL_INTERVAL,
                        help=f'Poll interval in seconds (default: {POLL_INTERVAL})')
    args = parser.parse_args()

    # Apply visitor count to all targets
    for t in TARGETS:
        t['visitors'] = args.visitors

    asyncio.run(monitor_loop(args.poll))


if __name__ == '__main__':
    main()
