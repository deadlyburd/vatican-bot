"""
Local Browser Agent — runs on YOUR Windows machine (not Docker)
================================================================
Polls for new snipe tasks from the server, opens Chrome when a slot is found,
navigates to Vatican checkout with form pre-filled, waits for you to solve
Turnstile and click BUY, captures the epay URL, sends it to Telegram.

Browser auto-closes after 20 minutes to save RAM.

Setup (run once in PowerShell):
  python -m pip install playwright requests
  python -m playwright install chromium

Run:
  python local_browser_agent.py
  (or double-click run_agent.bat)

The script polls the server every 10 seconds for new held slots.
When one appears, it opens Chrome automatically.
"""
import asyncio
import json
import os
import sys
import time
import requests
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse
import subprocess
import shutil

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

import platform as _platform

# ── Load config from agent_config.json if it exists next to the exe ──────────
def _load_config():
    """Load config from agent_config.json in same dir as the exe/script."""
    import json as _json
    # When frozen as exe, use exe directory; otherwise script directory
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(base, 'agent_config.json')
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, 'r') as f:
                return _json.load(f)
        except Exception:
            pass
    return {}

_cfg = _load_config()

# ── CONFIG — overridable via agent_config.json or CLI args ───────────────────
SERVER_URL            = _cfg.get('server_url',   'https://hydrabot.it')
BOT_TOKEN             = _cfg.get('bot_token',    '')
ADMIN_CHAT_ID         = _cfg.get('admin_chat_id','')
TRIGGER_GROUP_CHAT_ID = _cfg.get('trigger_group','')
POLL_INTERVAL         = int(_cfg.get('poll_interval', 2))
BROWSER_TIMEOUT       = int(_cfg.get('browser_timeout', 20 * 60))
AGENT_ID              = _cfg.get('agent_id', os.getenv('AGENT_ID', _platform.node()))
CHROME_PATH           = _cfg.get('chrome_path', r'C:\Program Files\Google\Chrome\Application\chrome.exe')
CHROME_PROFILE        = _cfg.get('chrome_profile', os.path.join(os.path.expanduser('~'), 'vatican_chrome_profile'))

BASE = 'https://tickets.museivaticani.va'

# Profile fallback (overridden by server's /api/v1/buyer-profile/ at runtime)
PROFILE = {
    'first_name': _cfg.get('first_name', 'Mario'),
    'last_name':  _cfg.get('last_name',  'Rossi'),
    'email':      _cfg.get('email',      'mario.rossi@example.com'),
    'phone':      _cfg.get('phone',      '3401234567'),
    'city':       _cfg.get('city',       'Roma'),
    'country':    _cfg.get('country',    'Italy'),
    'gender':     _cfg.get('gender',     'M'),
    'birth_date': _cfg.get('birth_date', {'year': 1990, 'month': 'JAN', 'day': 1}),
    'language':   _cfg.get('language',   'en'),
}
# ─────────────────────────────────────────────────────────────────────────────

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.7680.178 Safari/537.36"
last_update_id = 0
processed_slots = set()


def _kill_vatican_chrome():
    """
    Kill only Chrome processes using the Vatican profile directory.
    Does NOT kill other Chrome windows the user has open.
    Uses WMIC to find Chrome processes with our profile path in their command line.
    """
    try:
        profile_path = CHROME_PROFILE.replace('\\', '\\\\')
        # Find Chrome PIDs using our specific profile
        result = subprocess.run(
            ['wmic', 'process', 'where',
             f'name="chrome.exe" and commandline like "%{CHROME_PROFILE}%"',
             'get', 'processid', '/format:value'],
            capture_output=True, text=True, timeout=5
        )
        pids = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith('ProcessId=') and line[10:].strip().isdigit():
                pids.append(line[10:].strip())
        if pids:
            for pid in pids:
                subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True, timeout=3)
            logger.info(f"Killed Vatican Chrome PIDs: {pids}")
        else:
            # Fallback: just delete the lockfile so next launch works
            lockfile = os.path.join(CHROME_PROFILE, 'lockfile')
            if os.path.exists(lockfile):
                try: os.remove(lockfile)
                except: pass
    except Exception as e:
        logger.debug(f"_kill_vatican_chrome: {e}")


def send_telegram(chat_id: str, msg: str, reply_markup=None):
    """Send message to a Telegram chat."""
    payload = {'chat_id': chat_id, 'text': msg, 'parse_mode': 'Markdown'}
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    try:
        requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json=payload, timeout=5, proxies={'http': None, 'https': None}
        )
    except Exception:
        pass


def answer_callback(callback_query_id: str, text: str = ''):
    """Answer a Telegram callback query (removes loading spinner)."""
    try:
        requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery',
            json={'callback_query_id': callback_query_id, 'text': text},
            timeout=5, proxies={'http': None, 'https': None}
        )
    except Exception:
        pass


def get_telegram_updates():
    """Poll server for pending browser open requests — short poll, returns immediately."""
    try:
        r = requests.get(
            f'{SERVER_URL}/api/v1/browser-pending/?agent_id={AGENT_ID}',
            timeout=5, proxies={'http': None, 'https': None}
        )
        if r.status_code == 200:
            return r.json().get('requests', [])
    except Exception:
        pass
    return []


def get_trigger_group():
    """Get the configured browser trigger group from server."""
    try:
        r = requests.get(f'{SERVER_URL}/api/v1/browser-trigger-group/', timeout=5, proxies={'http': None, 'https': None})
        if r.status_code == 200:
            data = r.json()
            return data.get('chat_id', TRIGGER_GROUP_CHAT_ID)
    except Exception:
        pass
    return TRIGGER_GROUP_CHAT_ID


def get_pending_slots():
    """Poll the server for held slots that need browser checkout."""
    try:
        r = requests.get(f'{SERVER_URL}/api/v1/holds/?status=held', timeout=8, proxies={'http': None, 'https': None})
        if r.status_code == 200:
            return r.json().get('results', [])
    except Exception:
        pass
    return []


def notify_slot_with_button(slot: dict):
    """Send slot notification to the trigger group with Open Browser button."""
    date = slot.get('date', '')
    slot_time = slot.get('slot_time', '')
    visitors = slot.get('visitors', 1)
    total = slot.get('total_price', '?')
    hold_id = slot.get('id')

    msg = (
        f"🎫 *Slot Available — Open Browser to Book*\n\n"
        f"📅 {date} {slot_time}\n"
        f"👥 {visitors} visitors | €{total}\n\n"
        f"Click the button to open Chrome on your machine.\n"
        f"Form will be pre-filled — just solve Turnstile and click BUY."
    )
    reply_markup = {
        'inline_keyboard': [[
            {'text': '🌐 Open Browser', 'callback_data': f'open_browser:{hold_id}'}
        ]]
    }
    send_telegram(TRIGGER_GROUP_CHAT_ID, msg, reply_markup)
    logger.info(f"📢 Sent browser button to group {TRIGGER_GROUP_CHAT_ID}")


async def open_checkout(slot: dict):
    """
    Open Chrome via nodriver (bypasses Cloudflare Turnstile natively),
    navigate to Vatican checkout, pre-fill form, auto-solve Turnstile, click BUY.
    Captures epay URL and reports back to server + Telegram.
    """
    import nodriver as uc

    is_setup = slot is None or slot.get('id') == 'setup'
    if is_setup:
        slot = {'id': 'setup', 'date': '?', 'slot_time': '?', 'visitors': 1}

    date = slot.get('date', '')
    slot_time = slot.get('slot_time', '')
    visitors = int(slot.get('visitors', 1))
    adult_count = int(slot.get('adult_count', visitors))
    child_count = int(slot.get('child_count', 0))
    hold_id = slot.get('id')
    total = slot.get('total_price', '?')

    participants = []
    try:
        import json as _j
        notes = _j.loads(slot.get('notes') or '{}')
        participants = notes.get('participants', [])
    except Exception:
        pass

    logger.info(f"\n{'='*60}")
    logger.info(f"🎫 SLOT: {date} {slot_time} | {visitors}v | €{total} | Hold #{hold_id}")
    logger.info(f"🚀 Launching nodriver Chrome (Turnstile auto-solve)...")
    logger.info(f"{'='*60}")

    # Fetch profile from server
    profile_data = PROFILE.copy()
    try:
        r = await asyncio.to_thread(lambda: requests.get(
            f'{SERVER_URL}/api/v1/buyer-profile/', timeout=5, proxies={'http': None, 'https': None}
        ))
        if r.status_code == 200:
            srv = r.json()
            if srv.get('first_name'):
                profile_data.update({k: srv[k] for k in ('first_name','last_name','email','phone','city','country') if srv.get(k)})
    except Exception:
        pass

    send_telegram(TRIGGER_GROUP_CHAT_ID,
        f"🌐 *Browser opening (nodriver)*\n📅 {date} {slot_time} | 👥 {visitors}v | €{total}\n"
        f"Turnstile will auto-solve. Watch your screen.")

    # Pause server-side recap so it doesn't interfere with checkout
    try:
        await asyncio.to_thread(lambda: requests.post(
            f'{SERVER_URL}/api/v1/holds/{hold_id}/pause-recap/', timeout=5, proxies={'http': None, 'https': None}
        ))
        logger.info(f"  ⏸️ Server recap paused for Hold #{hold_id}")
    except Exception:
        pass

    from zoneinfo import ZoneInfo
    rome = ZoneInfo('Europe/Rome')
    day, month, year = date.split('/')
    dt = datetime(int(year), int(month), int(day), 0, 0, 0, tzinfo=rome)
    ts = int(dt.timestamp() * 1000)
    # Use /home/visit/ URL (same as working test_headful_hold_challenge.py)
    entry_url = f'{BASE}/home/visit/{visitors}/{ts}/1'

    epay_result = {}
    start_time = time.time()

    # Kill only Chrome using the Vatican profile (not all Chrome windows)
    _kill_vatican_chrome()
    await asyncio.sleep(0.5)

    # Clean stale lockfile
    lockfile = os.path.join(CHROME_PROFILE, 'lockfile')
    if os.path.exists(lockfile):
        try: os.remove(lockfile)
        except: pass

    browser = await uc.start(
        user_data_dir=CHROME_PROFILE,
        browser_executable_path=CHROME_PATH,
        headless=False,
        lang='it-IT',
        sandbox=True,          # Chrome is a child process — dies when Python dies
    )
    tab = browser.main_tab
    logger.info("  ✅ nodriver Chrome launched — Turnstile-invisible")

    try:
        if is_setup:
            logger.info("SETUP MODE — navigate manually, then Ctrl+C")
            await tab.get('https://tickets.museivaticani.va/home')
            try:
                while True: await asyncio.sleep(60)
            except KeyboardInterrupt:
                pass
            return

        # [0] Skip warm-up — go straight to ticket page
        logger.info(f"[1] {entry_url}")
        await tab.get(entry_url)
        await tab.sleep(2)

        # [2] Resolve fresh ticket_id via Search API
        logger.info("[2] Resolving ticket_id via Search API...")
        import requests as _req

        def _search_api():
            cookies = {}  # will be populated below
            return _req.get(f'{BASE}/api/search/resultPerTag', params={
                'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date,
                'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
            }, headers={
                'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest', 'User-Agent': USER_AGENT
            }, timeout=10, proxies={'http': None, 'https': None})

        r = await asyncio.to_thread(_search_api)
        visits = r.json().get('visits', []) if r.status_code == 200 else []
        ticket = next((v for v in visits
                       if 'musei vaticani' in v.get('name', '').lower()
                       and 'ingresso' in v.get('name', '').lower()), None)
        if not ticket:
            logger.error(f"No standard entry ticket found for {date}")
            send_telegram(TRIGGER_GROUP_CHAT_ID, f"❌ No ticket found for {date} — hold #{hold_id} still active")
            # Resume recap since we're not proceeding
            try: _req.post(f'{SERVER_URL}/api/v1/holds/{hold_id}/resume-recap/', timeout=5, proxies={'http': None, 'https': None})
            except: pass
            return
        tid = str(ticket['id'])
        logger.info(f"  ticket_id={tid}")

        # [3] Click PRENOTA — find by ticket name in the card, not by API ticket_id
        # (Vatican DOM IDs differ from Search API IDs)
        logger.info(f"[3] Finding PRENOTA button for 'Musei Vaticani - Biglietti d'ingresso'...")
        dom_tid = await tab.evaluate("""
            (() => {
                // Find the ticket card containing "Musei Vaticani" + "ingresso" text
                const cards = Array.from(document.querySelectorAll('[id^="ticket_"]'));
                for (const card of cards) {
                    const text = card.innerText.toLowerCase();
                    if (text.includes('musei vaticani') && (text.includes('ingresso') || text.includes('biglietti'))) {
                        // Get the data-cy of the PRENOTA button inside this card
                        const btn = card.querySelector("[data-cy^='bookTicket_']");
                        if (btn) return btn.getAttribute('data-cy').replace('bookTicket_', '');
                    }
                }
                // Fallback: first PRENOTA button (not NON PRENOTABILE)
                const allBtns = Array.from(document.querySelectorAll("[data-cy^='bookTicket_']"));
                for (const btn of allBtns) {
                    if (btn.innerText.trim() === 'PRENOTA') {
                        return btn.getAttribute('data-cy').replace('bookTicket_', '');
                    }
                }
                return null;
            })()
        """)
        if not dom_tid:
            logger.error("Could not find PRENOTA button in DOM")
            return
        logger.info(f"  DOM ticket_id={dom_tid} (API had {tid})")
        tid = dom_tid  # use DOM id for all subsequent steps

        await tab.evaluate(f"document.querySelector(\"[data-cy='bookTicket_{tid}']\")?.click()")
        await tab.sleep(1)

        # [4] Set quantity — exact logic from working test_headful_hold_challenge.py
        logger.info(f"[4] quantity: {adult_count} adults, {child_count} children")
        await tab.evaluate("""
            const qty = document.querySelector("[data-cy='ticketQuantity']");
            if (qty) qty.click();
        """)
        await tab.sleep(0.3)
        await tab.evaluate("""
            const sec = document.querySelector("div.ng-touched section > div:nth-of-type(1)");
            if (sec) sec.click();
        """)
        await tab.sleep(0.2)
        await tab.evaluate("""
            const qty2 = document.querySelector("[data-cy='ticketQuantity']");
            if (qty2) qty2.click();
        """)
        await tab.sleep(0.3)
        clicked_qty = await tab.evaluate(f"""
            (() => {{
                // Try to find the exact quantity number
                const all = Array.from(document.querySelectorAll("[data-cy='ticketQuantitySection']"))
                    .filter(el => el.offsetParent !== null);
                const match = all.find(el => el.innerText.trim() === '{adult_count}');
                if (match) {{ match.click(); return match.innerText.trim(); }}
                // Fallback: click span inside first visible section
                const span = document.querySelector("[data-cy='ticketQuantitySection'] > span");
                if (span) {{ span.click(); return span.innerText.trim(); }}
                const sec = document.querySelector("[data-cy='ticketQuantitySection']");
                if (sec) {{ sec.click(); return sec.innerText.trim(); }}
                return null;
            }})()
        """)
        logger.info(f"  quantity selected: {clicked_qty}")
        await tab.sleep(0.2)

        # [5] Select time slot — wait for slots to render first
        logger.info(f"[5] time={slot_time}")
        target_mins = int(slot_time.split(':')[0]) * 60 + int(slot_time.split(':')[1])

        # Wait up to 5s for time slots to appear
        for _ in range(10):
            count = await tab.evaluate("""
                document.querySelectorAll("[data-cy='time'] div.muvaCalendarNumber").length
            """)
            if count and count > 0:
                break
            await tab.sleep(0.5)

        if target_mins >= 14 * 60:
            await tab.evaluate("""
                (() => {
                    const tabs = Array.from(document.querySelectorAll('.tab')).filter(el => el.offsetParent !== null);
                    if (tabs.length >= 2) tabs[1].click();
                })()
            """)
            await tab.sleep(0.5)

        # Exact selector from working file
        await tab.evaluate(f"""
            (() => {{
                const els = Array.from(document.querySelectorAll("[data-cy='time'] div.muvaCalendarNumber"))
                    .filter(el => el.innerText.trim() === '{slot_time}');
                if (els.length > 0) {{ els[0].scrollIntoView(); els[0].click(); return; }}
                // fallback: pick closest available time
                const all = Array.from(document.querySelectorAll("[data-cy='time'] div.muvaCalendarNumber"));
                if (!all.length) return;
                const target = {target_mins};
                let best = null, bestDiff = 9999;
                for (const el of all) {{
                    const t = el.innerText.trim();
                    const parts = t.split(':');
                    if (parts.length !== 2) continue;
                    const mins = parseInt(parts[0]) * 60 + parseInt(parts[1]);
                    const diff = Math.abs(mins - target);
                    if (diff < bestDiff) {{ bestDiff = diff; best = el; }}
                }}
                if (best) {{ best.scrollIntoView(); best.click(); }}
            }})()
        """)
        await tab.sleep(0.8)

        # [6] Click PROCEDI — exact from working file
        logger.info("[6] PROCEDI")
        await tab.evaluate("""
            (() => {
                const btn = document.querySelector("[data-cy='bookVisit']") ||
                    Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes("PROCEDI"));
                if (btn) btn.click();
            })()
        """)
        await tab.sleep(3)

        # [7] Fill checkout form
        logger.info("[7] Filling form...")

        async def fill_field(selector, value):
            await tab.evaluate(f"""
                (() => {{
                    const el = document.querySelector("{selector}");
                    if (el) {{
                        el.focus();
                        el.value = '';
                        el.value = `{value}`;
                        el.dispatchEvent(new Event('input', {{bubbles: true}}));
                        el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    }}
                }})()
            """)

        # Wait for form
        for _ in range(15):
            el = await tab.evaluate("document.querySelector(\"[data-cy='managerSurname']\")?.tagName")
            if el: break
            await tab.sleep(1)

        await fill_field("[data-cy='managerSurname']", profile_data['last_name'])
        await fill_field("[data-cy='managerName']", profile_data['first_name'])
        await fill_field("[data-cy='managerCity']", profile_data['city'])
        await fill_field("[data-cy='managerEmail']", profile_data['email'])
        await fill_field("[data-cy='managerConfirmEmail']", profile_data['email'])
        await fill_field("[data-cy='managerPhone']", profile_data['phone'])

        # Gender
        await tab.evaluate("""
            (() => {
                const s = document.querySelector("[data-cy='managerSex']");
                if (s) s.click();
            })()
        """)
        await tab.sleep(0.2)
        await tab.evaluate("""
            (() => {
                const opt = document.querySelector("[data-cy='managerSexSection']");
                if (opt) opt.click();
            })()
        """)
        await tab.sleep(0.2)

        # Country
        await tab.evaluate("""
            (() => {
                const s = document.querySelector("[data-cy='managerCountry']");
                if (s) s.click();
            })()
        """)
        await tab.sleep(0.2)
        await tab.evaluate(f"""
            (() => {{
                const search = document.querySelector('#searchInput_country');
                if (search) {{
                    search.value = '{profile_data["country"][:4]}';
                    search.dispatchEvent(new Event('input', {{bubbles: true}}));
                }}
            }})()
        """)
        await tab.sleep(0.3)
        await tab.evaluate("""
            (() => {
                const opt = document.querySelector("[data-cy='managerCountrySection']");
                if (opt) opt.click();
            })()
        """)
        await tab.sleep(0.2)

        # Language
        await tab.evaluate("""
            (() => {
                const s = document.querySelector("[data-cy='managerLanguage']");
                if (s) s.click();
            })()
        """)
        await tab.sleep(0.2)
        await tab.evaluate("""
            (() => {
                const opt = document.querySelector("[data-cy='managerLanguageSection']");
                if (opt) opt.click();
            })()
        """)
        await tab.sleep(0.2)

        # Participants
        for i in range(visitors):
            if i > 0:
                await tab.evaluate(f"""
                    (() => {{
                        const el = document.querySelector('#participantElement_{i} div.tw-flex-grow > div');
                        if (el) el.click();
                    }})()
                """)
                await tab.sleep(0.5)
            p_first = participants[i].get('first_name', profile_data['first_name']) if i < len(participants) else profile_data['first_name']
            p_last = participants[i].get('last_name', profile_data['last_name']) if i < len(participants) else profile_data['last_name']
            await fill_field(f"#participantSurname_{i}", p_last)
            await fill_field(f"#participantName_{i}", p_first)

        # GDPR checkboxes
        await tab.evaluate("""
            (() => {
                const cb1 = document.querySelector("#mat-mdc-checkbox-1-input");
                if (cb1 && !cb1.checked) {
                    cb1.click();
                    setTimeout(() => {
                        const close = document.querySelector("[data-cy='purchase-rules-close-btn'] mat-icon");
                        if (close) close.click();
                    }, 1000);
                }
                setTimeout(() => {
                    const cb4 = document.querySelector("#mat-mdc-checkbox-4-input");
                    if (cb4 && !cb4.checked) cb4.click();
                }, 1500);
            })()
        """)
        await tab.sleep(1.5)

        # Inject browser-side heartbeat (backup — server recap is paused)
        await tab.evaluate(f"""
            ((slot_id, ticket_id, visitors, adult_count, child_count) => {{
                window._vatican_heartbeat = setInterval(() => {{
                    fetch('/api/visit/recap', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        credentials: 'include',
                        body: JSON.stringify({{
                            visitId: slot_id,
                            visitTypeId: parseInt(ticket_id),
                            visitorNum: parseInt(visitors),
                            lang: 'it',
                            tickets: [
                                {{id: 60, name: 'Biglietto Intero', price: 20, quantity: adult_count.toString()}},
                                {{id: 61, name: 'Biglietto Ridotto', price: 10, quantity: child_count.toString()}}
                            ],
                            additionalCosts: {{'service-0': {{id: 58, name: 'Diritti di Prevendita', price: 5, quantity: parseInt(visitors)}}}},
                            services: [{{id: 58, name: 'Diritti di Prevendita', price: 5, quantity: parseInt(visitors)}}]
                        }})
                    }}).then(r => console.log('HB', r.status, new Date().toLocaleTimeString()))
                      .catch(e => console.log('HB err', e));
                }}, 240000);
                // Keep checkboxes ticked
                window._box_maintainer = setInterval(() => {{
                    const cb1 = document.querySelector("#mat-mdc-checkbox-1-input");
                    const cb4 = document.querySelector("#mat-mdc-checkbox-4-input");
                    if (cb1 && !cb1.checked) {{
                        cb1.click();
                        setTimeout(() => {{
                            const c = document.querySelector("[data-cy='purchase-rules-close-btn'] mat-icon");
                            if (c) c.click();
                        }}, 1000);
                    }}
                    if (cb4 && !cb4.checked) cb4.click();
                }}, 30000);
            }})("{slot.get('slot_id', '')}", "{tid}", "{visitors}", "{adult_count}", "{child_count}")
        """)

        logger.info(f"\n{'='*60}")
        logger.info(f"✅ FORM FILLED — nodriver will auto-solve Turnstile")
        logger.info(f"   Watch the browser — it should click BUY automatically")
        logger.info(f"{'='*60}\n")
        send_telegram(TRIGGER_GROUP_CHAT_ID,
            f"✅ *Form filled for {date} {slot_time}*\n"
            f"nodriver is solving Turnstile... BUY will be clicked automatically.")

        # Wait for reservation or epay redirect
        deadline = time.time() + BROWSER_TIMEOUT
        reservation_done = False
        while time.time() < deadline and not reservation_done:
            await asyncio.sleep(3)

            # Check current URL for epay redirect
            try:
                current_url = await tab.evaluate("window.location.href")
            except Exception:
                current_url = ''

            if 'epay.catholica.va' in (current_url or ''):
                logger.info(f"✅ Redirected to epay: {current_url[:80]}")
                reservation_done = True

                # Auto-fill card details
                try:
                    card_r = await asyncio.to_thread(lambda: requests.get(
                        f'{SERVER_URL}/api/v1/buyer-card/', timeout=5, proxies={'http': None, 'https': None}
                    ))
                    if card_r.status_code == 200:
                        card = card_r.json()
                        await tab.sleep(2)
                        await tab.evaluate(f"""
                            (() => {{
                                const setVal = (sel, val) => {{
                                    const el = document.querySelector(sel);
                                    if (el) {{
                                        el.focus(); el.value = val;
                                        el.dispatchEvent(new Event('input', {{bubbles:true}}));
                                        el.dispatchEvent(new Event('change', {{bubbles:true}}));
                                    }}
                                }};
                                setVal("input[id*='cardNumber'], input[ng-model*='cardNumber']", "{card.get('card_number','')}");
                                setVal("input[id*='expiryDate'], input[ng-model*='expiry']", "{card.get('card_expiry','').replace('//','')}");
                                setVal("input[id*='cvv'], input[ng-model*='cvv']", "{card.get('card_cvv','')}");
                                setVal("input[id*='cardHolder'], input[ng-model*='holder']", "{card.get('card_holder','')}");
                                const terms = document.querySelector("input[type='checkbox']");
                                if (terms && !terms.checked) terms.click();
                            }})()
                        """)
                        logger.info("  💳 Card details auto-filled on epay page")
                        send_telegram(TRIGGER_GROUP_CHAT_ID,
                            f"💳 *Card auto-filled on epay!*\n{date} {slot_time}\nClick PAY to complete.")
                except Exception as e:
                    logger.warning(f"  Card fill error: {e}")

                # Mark paid on server
                try:
                    requests.post(f'{SERVER_URL}/api/v1/mark-paid/', json={
                        'hold_id': hold_id, 'reference': '', 'epay_url': current_url
                    }, timeout=5, proxies={'http': None, 'https': None})
                except Exception:
                    pass

                send_telegram(TRIGGER_GROUP_CHAT_ID,
                    f"✅ *Vatican ticket booked!*\n📅 {date} {slot_time} | 👥 {visitors}v | €{total}\n"
                    f"💳 Complete payment on epay page.")
                await tab.sleep(120)  # keep open for user to finish payment
                break

            remaining = int(deadline - time.time())
            if remaining % 60 == 0 and remaining > 0:
                logger.info(f"  Waiting for Turnstile solve... {remaining//60}min left")

        if not reservation_done:
            logger.warning("⏰ Timeout — no epay redirect detected")
            send_telegram(TRIGGER_GROUP_CHAT_ID,
                f"⏰ Timeout for {date} {slot_time} — Turnstile may not have solved.\n"
                f"Hold #{hold_id} still active. Use /pay {hold_id} to retry.")
            # Resume server recap since we didn't complete
            try: requests.post(f'{SERVER_URL}/api/v1/holds/{hold_id}/resume-recap/', timeout=5, proxies={'http': None, 'https': None})
            except: pass

    except Exception as e:
        logger.error(f"Checkout failed: {e}")
        import traceback; traceback.print_exc()
        send_telegram(TRIGGER_GROUP_CHAT_ID,
            f"❌ Checkout error for Hold #{hold_id}: {e}\nHold still active — use /pay {hold_id} to retry.")
        try: requests.post(f'{SERVER_URL}/api/v1/holds/{hold_id}/resume-recap/', timeout=5, proxies={'http': None, 'https': None})
        except: pass
        try:
            while True: await asyncio.sleep(60)
        except KeyboardInterrupt:
            pass
    finally:
        try: browser.stop()
        except: pass
        try: _kill_vatican_chrome()
        except: pass
        logger.info("Browser closed.")


async def main():
    """
    Main loop:
    1. Poll server for new held slots → send button to WOR group
    2. Poll Telegram for button clicks → open Chrome
    """
    global last_update_id

    logger.info(f"🤖 Vatican Browser Agent started")
    logger.info(f"Agent ID : {AGENT_ID}")
    logger.info(f"Server   : {SERVER_URL}")
    logger.info(f"Trigger  : {TRIGGER_GROUP_CHAT_ID}")
    logger.info(f"Polling  : long-poll (instant response)")
    logger.info(f"Press Ctrl+C to stop\n")
    logger.info("Polling Vatican server for slots...")

    send_telegram(ADMIN_CHAT_ID, f"🤖 Browser Agent `{AGENT_ID}` started\nPolling for jobs...")

    # pending_browser: hold_id → slot dict (waiting for button click)
    pending_browser = {}
    processing_holds = set()  # prevent duplicate browser opens
    heartbeat_last = 0

    while True:
        try:
            # Register heartbeat every 30s so server knows this agent is online
            now = time.time()
            if now - heartbeat_last > 30:
                try:
                    requests.post(
                        f'{SERVER_URL}/api/v1/agent-heartbeat/',
                        json={'agent_id': AGENT_ID, 'hostname': _platform.node()},
                        timeout=3, proxies={'http': None, 'https': None}
                    )
                except Exception:
                    pass
                heartbeat_last = now
            # ── Check for new held slots ──────────────────────────────────────
            slots = get_pending_slots()
            for slot in slots:
                hold_id = slot.get('id')
                slot_key = f"{hold_id}_{slot.get('date')}_{slot.get('slot_time')}"
                if slot_key not in processed_slots and slot.get('status') in ('held', 'paying'):
                    processed_slots.add(slot_key)
                    pending_browser[str(hold_id)] = slot
                    notify_slot_with_button(slot)
                    logger.info(f"New slot notified: {slot.get('date')} {slot.get('slot_time')}")

            # ── Check for browser open requests (auto + button clicks) ─────────
            pending_reqs = get_telegram_updates()
            for req in pending_reqs:
                data = req.get('data', '')
                user_name = req.get('user', 'Auto')
                is_auto = req.get('auto', False)

                logger.info(f"📥 {'Auto' if is_auto else 'Button'} browser request from {user_name}")

                if data.startswith('open_browser:'):
                    parts = data.split(':')
                    hold_id = parts[1]

                    # Deduplicate
                    if hold_id in processing_holds:
                        logger.debug(f"Hold #{hold_id} already processing — skip")
                        continue
                    processing_holds.add(hold_id)
                    slot = pending_browser.get(hold_id)

                    # Try to decode embedded slot info (format: open_browser:{id}:{base64})
                    if not slot and len(parts) >= 3:
                        try:
                            import base64
                            slot_info = base64.b64decode(parts[2]).decode()
                            s_parts = slot_info.split('|')
                            slot = {
                                'id': hold_id,
                                'date': s_parts[0],
                                'slot_time': s_parts[1],
                                'slot_id': s_parts[2] if len(s_parts) > 2 else '',
                                'visitors': int(s_parts[3]) if len(s_parts) > 3 else 1,
                                'total_price': s_parts[4] if len(s_parts) > 4 else '?',
                                'adult_count': int(s_parts[5]) if len(s_parts) > 5 else int(s_parts[3] if len(s_parts) > 3 else 1),
                                'child_count': int(s_parts[6]) if len(s_parts) > 6 else 0,
                            }
                            logger.info(f"  Decoded slot: {slot['date']} {slot['slot_time']} ({slot['adult_count']}A, {slot['child_count']}C)")
                        except Exception as e:
                            logger.warning(f"  Could not decode slot info: {e}")

                    if not slot:
                        # Last resort: build minimal slot and let agent do full flow
                        slot = {'id': hold_id, 'date': None, 'slot_time': None,
                                'visitors': 1, 'total_price': '?'}
                        logger.warning(f"  Using minimal slot for hold #{hold_id}")

                    send_telegram(TRIGGER_GROUP_CHAT_ID,
                        f"🌐 *{user_name}* clicked Open Browser\n"
                        f"Chrome opening for {slot.get('date','?')} {slot.get('slot_time','?')}...")
                    logger.info(f"Opening Chrome for hold #{hold_id} — {slot.get('date')} {slot.get('slot_time')}")
                    asyncio.create_task(open_checkout(slot))

                elif data.startswith('open_browser_slot:'):
                    import base64
                    # Deduplicate by slot data
                    slot_key = data[:60]
                    if slot_key in processing_holds:
                        logger.debug(f"Slot already processing — skip")
                        continue
                    processing_holds.add(slot_key)
                    try:
                        slot_info = base64.b64decode(data.split(':', 1)[1]).decode()
                        s_parts = slot_info.split('|')
                        date_str = s_parts[0]
                        slot_time_str = s_parts[1]
                        slot_id_str = s_parts[2] if len(s_parts) > 2 else ''
                        visitors_n = int(s_parts[3]) if len(s_parts) > 3 else 1
                        total_str = s_parts[4] if len(s_parts) > 4 else '?'
                        slot = {
                            'date': date_str, 'slot_time': slot_time_str,
                            'slot_id': slot_id_str, 'visitors': visitors_n,
                            'total_price': total_str, 'id': None,
                            'adult_count': int(s_parts[5]) if len(s_parts) > 5 else visitors_n,
                            'child_count': int(s_parts[6]) if len(s_parts) > 6 else 0,
                        }
                        send_telegram(TRIGGER_GROUP_CHAT_ID,
                            f"🌐 *{user_name}* clicked Open Browser\n"
                            f"Chrome opening for {date_str} {slot_time_str}...")
                        logger.info(f"Opening Chrome for {date_str} {slot_time_str}")
                        asyncio.create_task(open_checkout(slot))
                    except Exception as e:
                        logger.error(f"open_browser_slot error: {e}")

        except KeyboardInterrupt:
            logger.info("Stopped.")
            break
        except Exception as e:
            logger.error(f"Main loop error: {e}")

        # Short-poll: sleep 2s between checks
        await asyncio.sleep(2)


if __name__ == '__main__':
    import atexit

    # Kill Chrome when this script exits for any reason
    def _kill_chrome():
        try:
            _kill_vatican_chrome()
        except Exception:
            pass
    atexit.register(_kill_chrome)

    parser = argparse.ArgumentParser(description='Vatican Browser Agent')
    parser.add_argument('--setup',     action='store_true', help='Open browser for manual Vatican login')
    parser.add_argument('--test',      metavar='DATE',      help='Test checkout on a specific date DD/MM/YYYY')
    parser.add_argument('--time',      metavar='TIME',      default='09:00', help='Preferred slot time for --test')
    parser.add_argument('--visitors',  type=int,            default=2,       help='Visitor count for --test')
    parser.add_argument('--agent',     metavar='NAME',      default=None,    help='Agent name/ID for this machine')
    parser.add_argument('--chrome',    metavar='PATH',      default=None,    help='Path to Chrome executable')
    parser.add_argument('--profile',   metavar='PATH',      default=None,    help='Path to Chrome profile folder')
    parser.add_argument('--minimized', action='store_true', help='Hide console window (run silently in background)')
    args = parser.parse_args()

    # Hide console window when running as background service
    if args.minimized:
        try:
            import ctypes
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        except Exception:
            pass

    if args.agent:
        AGENT_ID = args.agent
        logger.info(f"Agent ID set to: {AGENT_ID}")
    if args.chrome:
        CHROME_PATH = args.chrome
        logger.info(f"Chrome path: {CHROME_PATH}")
    if args.profile:
        CHROME_PROFILE = args.profile
        logger.info(f"Chrome profile: {CHROME_PROFILE}")

    if args.setup:
        logger.info("Starting browser in SETUP mode...")
        asyncio.run(open_checkout(None))

    elif args.test:
        # Direct test: find a real slot then open Chrome — same as test_headful_hold_challenge.py
        logger.info(f"TEST MODE: scanning for real slot on {args.test} with {args.visitors} visitors")

        def _find_slot(date, visitors, preferred_time):
            """Find a real available slot_id from timeavail."""
            import requests as _r
            BASE = 'https://tickets.museivaticani.va'
            H = {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}
            s = _r.Session()
            try:
                s.get(f'{BASE}/home', timeout=8, proxies={'http': None, 'https': None})
            except Exception:
                pass
            r = s.get(f'{BASE}/api/search/resultPerTag', params={
                'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date,
                'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
            }, headers=H, timeout=10, proxies={'http': None, 'https': None})
            if r.status_code != 200:
                return None
            ticket = next((v for v in r.json().get('visits', [])
                           if 'musei vaticani' in v.get('name', '').lower()
                           and 'ingresso' in v.get('name', '').lower()), None)
            if not ticket:
                return None
            tid = str(ticket['id'])
            r2 = s.get(f'{BASE}/api/visit/timeavail', params={
                'lang': 'it', 'visitLang': '', 'visitTypeId': tid,
                'visitorNum': str(visitors), 'visitDate': date,
            }, headers=H, timeout=10, proxies={'http': None, 'https': None})
            if r2.status_code != 200:
                return None
            slots = [sl for sl in r2.json().get('timetable', [])
                     if sl.get('availability') in ('AVAILABLE', 'LOW_AVAILABILITY')]
            if not slots:
                return None
            # Pick closest to preferred time
            target_mins = int(preferred_time.split(':')[0]) * 60 + int(preferred_time.split(':')[1])
            best = min(slots, key=lambda sl: abs(
                int(sl['time'].split(':')[0]) * 60 + int(sl['time'].split(':')[1]) - target_mins
            ))
            return {
                'date': date,
                'slot_id': str(best['id']),
                'slot_time': best['time'],
                'ticket_id': tid,
                'visitors': visitors,
                'adult_count': visitors,
                'child_count': 0,
                'id': 'test',
                'total_price': '?',
            }

        slot = _find_slot(args.test, args.visitors, args.time)
        if slot:
            logger.info(f"Found slot: {slot['slot_time']} (id={slot['slot_id']}, ticket={slot['ticket_id']})")
            asyncio.run(open_checkout(slot))
        else:
            logger.error(f"No available slots found for {args.test} with {args.visitors} visitors")
            logger.info("Try a different date or check Vatican website directly")

    else:
        # Normal mode: poll server for jobs from Telegram /pay command
        logger.info("Starting agent — polling server for Telegram-triggered jobs...")
        while True:
            try:
                asyncio.run(main())
            except KeyboardInterrupt:
                logger.info("Agent stopped.")
                sys.exit(0)
            except Exception as e:
                logger.error(f"Agent crashed: {e} — restarting in 10s...")
                time.sleep(10)
