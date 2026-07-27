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
POLL_INTERVAL         = float(_cfg.get('poll_interval', 2.0))
AGENCY_KEY            = _cfg.get('agency_key',   'default')
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
            f'{SERVER_URL}/api/v1/browser-pending/?agent_id={AGENT_ID}&agency_key={AGENCY_KEY}',
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

    if not date:
        logger.error(f"❌ No date in slot — cannot open browser. Hold #{hold_id}")
        send_telegram(TRIGGER_GROUP_CHAT_ID,
            f"❌ Hold #{hold_id} has no date info — use `/open {hold_id}` to retry after the hold is confirmed.")
        return

    day, month, year = date.split('/')
    dt = datetime(int(year), int(month), int(day), 0, 0, 0, tzinfo=rome)
    ts = int(dt.timestamp() * 1000)
    # Use /home/fromtag/ URL — triggers ticket selection flow correctly
    entry_url = f'{BASE}/home/fromtag/{visitors}/{ts}/MV-Biglietti/1'

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

        # [1] Navigate — wait for ticket buttons to render
        logger.info(f"[1] {entry_url}")
        await tab.get(entry_url)
        for attempt in range(3):
            for _ in range(30):
                count = await tab.evaluate("document.querySelectorAll(\"[data-cy^='bookTicket_']\").length")
                if count and int(count) > 0: break
                no_visits = await tab.evaluate("(() => { const b=document.body?.innerText||''; return b.includes('Nessuna visita'); })()")
                if no_visits:
                    logger.info(f"  ⚠️ Nessuna visita — reloading (attempt {attempt+1})")
                    await tab.sleep(1); await tab.get(entry_url); await tab.sleep(2); break
                await tab.sleep(0.5)
            if count and int(count) > 0: break
            await tab.sleep(2)
        await tab.sleep(0.5)
        logger.info(f"  Page loaded — {count} ticket button(s)")

        # [2] Resolve fresh ticket_id via Search API
        logger.info("[2] Resolving ticket_id via Search API...")
        import requests as _req

        def _search_api():
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
            try: _req.post(f'{SERVER_URL}/api/v1/holds/{hold_id}/resume-recap/', timeout=5, proxies={'http': None, 'https': None})
            except: pass
            return
        tid = str(ticket['id'])
        logger.info(f"  ticket_id={tid}")

        # [3] Find PRENOTA button — poll until DOM ready
        logger.info(f"[3] Finding PRENOTA button...")
        dom_tid = None
        for _ in range(10):
            dom_tid = await tab.evaluate("""
                (() => {
                    const cards = Array.from(document.querySelectorAll('[id^="ticket_"]'));
                    for (const card of cards) {
                        const text = card.innerText.toLowerCase();
                        if (text.includes('musei vaticani') && (text.includes('ingresso') || text.includes('biglietti'))) {
                            const btn = card.querySelector("[data-cy^='bookTicket_']");
                            if (btn) return btn.getAttribute('data-cy').replace('bookTicket_', '');
                        }
                    }
                    const allBtns = Array.from(document.querySelectorAll("[data-cy^='bookTicket_']"));
                    for (const btn of allBtns) {
                        if (btn.innerText.trim() === 'PRENOTA')
                            return btn.getAttribute('data-cy').replace('bookTicket_', '');
                    }
                    return null;
                })()
            """)
            if dom_tid: break
            await tab.sleep(0.5)
        if not dom_tid:
            logger.error("Could not find PRENOTA button in DOM")
            return
        logger.info(f"  DOM ticket_id={dom_tid} (API had {tid})")
        tid = dom_tid

        await tab.evaluate(f"document.querySelector(\"[data-cy='bookTicket_{tid}']\")?.click()")
        await tab.sleep(2)

        # [4] Set quantity
        logger.info(f"[4] quantity: {adult_count} adults, {child_count} children")
        for _ in range(10):
            has_qty = await tab.evaluate("!!(document.querySelector('select')||document.querySelector(\"[data-cy='ticketQuantity']\"))")
            if has_qty: break
            await tab.sleep(0.4)
        qty_set = await tab.evaluate(f"""
            (() => {{
                const selects = Array.from(document.querySelectorAll('select'));
                if (selects.length > 0) {{
                    selects[0].value = '{adult_count}';
                    selects[0].dispatchEvent(new Event('change', {{bubbles: true}}));
                    if (selects.length > 1) {{
                        selects[1].value = '{child_count}';
                        selects[1].dispatchEvent(new Event('change', {{bubbles: true}}));
                    }}
                    return 'select:' + selects[0].value;
                }}
                const el = document.querySelector("[data-cy='ticketQuantity']");
                if (el) {{ el.click(); return 'dropdown'; }}
                return 'not-found';
            }})()
        """)
        if 'dropdown' in str(qty_set):
            await tab.sleep(0.8)
            await tab.evaluate(f"""
                (() => {{
                    const items = Array.from(document.querySelectorAll("[data-cy='ticketQuantitySection']"));
                    for (const item of items) {{
                        const t = item.innerText.trim();
                        if (t === '{visitors}' || t.startsWith('{visitors} ')) {{ item.click(); return; }}
                    }}
                    if (items.length >= {visitors}) items[{visitors}-1].click();
                    else if (items.length > 0) items[items.length-1].click();
                }})()
            """)
        logger.info(f"  quantity set: {qty_set}")
        await tab.sleep(1.5)

        # [5] Select time slot — wait for slots to render
        logger.info(f"[5] time={slot_time}")
        target_mins = int(slot_time.split(':')[0]) * 60 + int(slot_time.split(':')[1]) if slot_time else 0
        for _ in range(20):
            count = await tab.evaluate("document.querySelectorAll(\"[data-cy='time']\").length")
            if count and int(count) > 0: break
            await tab.sleep(0.5)
        logger.info(f"  {count} time slot(s) found")
        if target_mins >= 14 * 60:
            await tab.evaluate("(() => { const tabs=Array.from(document.querySelectorAll('.tab')).filter(e=>e.offsetParent); if(tabs[1]) tabs[1].click(); })()")
            await tab.sleep(0.8)
        await tab.evaluate(f"""
            (() => {{
                const cells = Array.from(document.querySelectorAll("[data-cy='time']"));
                for (const cell of cells) {{
                    const txt = cell.innerText.trim();
                    if (txt === '{slot_time}' || txt.startsWith('{slot_time}')) {{ cell.scrollIntoView(); cell.click(); return; }}
                    const num = cell.querySelector('div.muvaCalendarNumber, div');
                    if (num && num.innerText.trim() === '{slot_time}') {{ cell.scrollIntoView(); cell.click(); return; }}
                }}
                const target = {target_mins};
                let best = null, bestDiff = 9999;
                for (const cell of cells) {{
                    const txt = cell.innerText.trim().split('\\n')[0];
                    const parts = txt.split(':');
                    if (parts.length !== 2) continue;
                    const mins = parseInt(parts[0]) * 60 + parseInt(parts[1]);
                    const diff = Math.abs(mins - target);
                    if (diff < bestDiff) {{ bestDiff = diff; best = cell; }}
                }}
                if (best) {{ best.scrollIntoView(); best.click(); }}
            }})()
        """)
        await tab.sleep(2)

        # [6] PROCEDI — wait for button, JS click bypasses overlay
        logger.info("[6] PROCEDI")
        for _ in range(10):
            has_btn = await tab.evaluate("!!(document.querySelector(\"[data-cy='bookVisit']\"))")
            if has_btn: break
            await tab.sleep(0.5)
        await tab.evaluate("""
            (() => {
                const btn = document.querySelector("[data-cy='bookVisit']") ||
                    Array.from(document.querySelectorAll('button')).find(b => /PROCEDI/i.test(b.textContent));
                if (btn) btn.click();
            })()
        """)
        await tab.sleep(5)

        # [7] Wait for checkout form
        logger.info("[7] Filling form...")
        for _ in range(60):
            el = await tab.evaluate("document.querySelector(\"[data-cy='managerSurname']\")?.tagName")
            if el: break
            await tab.sleep(0.5)
        else:
            logger.warning("Form not found — screenshot saved")
            try: await tab.save_screenshot('debug_form_missing.png')
            except: pass

        async def fill_field(selector, value):
            safe = str(value).replace('\\', '\\\\').replace('`', '\\`')
            await tab.evaluate(f"""
                (() => {{
                    const el = document.querySelector(`{selector}`);
                    if (!el) return;
                    el.focus(); el.value = ''; el.value = `{safe}`;
                    el.dispatchEvent(new Event('input',  {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    el.blur();
                }})()
            """)

        # Wait for form
        for _ in range(30):
            el = await tab.evaluate("document.querySelector(\"[data-cy='managerSurname']\")?.tagName")
            if el: break
            await tab.sleep(0.5)

        await fill_field("[data-cy='managerSurname']", profile_data['last_name'])
        await fill_field("[data-cy='managerName']", profile_data['first_name'])
        await fill_field("[data-cy='managerCity']", profile_data['city'])
        await fill_field("[data-cy='managerEmail']", profile_data['email'])
        await fill_field("[data-cy='managerConfirmEmail']", profile_data['email'])
        await fill_field("[data-cy='managerPhone']", profile_data.get('phone','').lstrip('+39').lstrip('+'))

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

        # Birth date
        logger.info("[8b] Birth date...")
        bd_raw = profile_data.get('birth_date', {})
        if isinstance(bd_raw, dict):
            by = str(bd_raw.get('year', 1990))
            bm = str(bd_raw.get('month', 'GEN')).upper()
            bd = str(bd_raw.get('day', 15)).zfill(2)
        elif isinstance(bd_raw, str) and '-' in bd_raw:
            parts = bd_raw.split('-')
            by, bm_num, bd = parts[0], parts[1], parts[2].zfill(2)
            month_names = {'01':'GEN','02':'FEB','03':'MAR','04':'APR','05':'MAG','06':'GIU',
                           '07':'LUG','08':'AGO','09':'SET','10':'OTT','11':'NOV','12':'DIC'}
            bm = month_names.get(bm_num, 'GEN')
        else:
            by, bm, bd = '1990', 'GEN', '15'
        month_map = {'GEN':'01','FEB':'02','MAR':'03','APR':'04','MAG':'05','GIU':'06',
                     'LUG':'07','AGO':'08','SET':'09','OTT':'10','NOV':'11','DIC':'12'}
        bm_num = month_map.get(bm, '01')
        b_display = f"{bd}/{bm_num}/{by}"
        set_ok = await tab.evaluate(f"""
            (() => {{
                const inp = document.querySelector("[data-cy='dateCalendar']");
                if (!inp) return false;
                inp.removeAttribute('readonly');
                inp.focus(); inp.value = '{b_display}';
                inp.dispatchEvent(new Event('input',  {{bubbles: true}}));
                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                inp.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', bubbles: true}}));
                inp.setAttribute('readonly', 'true');
                return inp.value;
            }})()
        """)
        await tab.sleep(0.4)
        if not set_ok or set_ok == '':
            await tab.evaluate("document.querySelector(\"mat-datepicker-toggle button[aria-label='Open calendar']\")?.click()")
            await tab.sleep(0.8)
            for _ in range(2):
                multi = await tab.evaluate("document.querySelectorAll('.mat-calendar-body-cell').length > 12")
                if multi: break
                await tab.evaluate("document.querySelector('button.mat-calendar-period-button')?.click()")
                await tab.sleep(0.4)
            for _ in range(30):
                found = await tab.evaluate(f"""
                    (() => {{
                        const cells = Array.from(document.querySelectorAll('.mat-calendar-body-cell'));
                        const yr = cells.find(c => c.textContent.trim() === '{by}');
                        if (yr) {{ yr.click(); return true; }}
                        document.querySelector('.mat-calendar-previous-button')?.click();
                        return false;
                    }})()
                """)
                await tab.sleep(0.3)
                if found: break
            await tab.sleep(0.4)
            await tab.evaluate(f"(() => {{ const cells=Array.from(document.querySelectorAll('.mat-calendar-body-cell')); const mo=cells.find(c=>c.textContent.trim().toUpperCase()==='{bm}'); if(mo) mo.click(); }})()")
            await tab.sleep(0.4)
            bd_s = bd.lstrip('0') or '1'
            await tab.evaluate(f"(() => {{ const cells=Array.from(document.querySelectorAll('span.mat-calendar-body-cell-content')); const day=cells.find(c=>c.textContent.trim()==='{bd_s}'); if(day) day.click(); }})()")
            await tab.sleep(0.3)
        set_date = await tab.evaluate("document.querySelector(\"[data-cy='dateCalendar']\")?.value || ''")
        logger.info(f"  Birth date: {b_display} → field: {set_date}")

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

        # GDPR checkboxes — sequential with proper waits
        cb1 = await tab.evaluate("document.querySelector('#mat-mdc-checkbox-1-input')?.checked")
        if cb1 is False:
            await tab.evaluate("document.querySelector('#mat-mdc-checkbox-1-input')?.click()")
            await tab.sleep(1.5)
            await tab.evaluate("""
                (() => {
                    const close = document.querySelector("[data-cy='purchase-rules-close-btn']")
                               || Array.from(document.querySelectorAll('button')).find(b => /chiudi|close/i.test(b.textContent));
                    if (close) close.click();
                })()
            """)
            await tab.sleep(1)
        await tab.evaluate("(() => { const cb=document.querySelector('#mat-mdc-checkbox-3-input')||document.querySelector('#mat-mdc-checkbox-4-input'); if(cb&&!cb.checked) cb.click(); })()")
        await tab.sleep(0.5)
        cb_status = await tab.evaluate("({cb1:document.querySelector('#mat-mdc-checkbox-1-input')?.checked,cb3:document.querySelector('#mat-mdc-checkbox-3-input')?.checked,cb4:document.querySelector('#mat-mdc-checkbox-4-input')?.checked})")
        logger.info(f"  Checkboxes: {cb_status}")

        # Turnstile check
        for _ in range(30):
            token = await tab.evaluate("(() => { const inp=document.querySelector('[name=\"cf-turnstile-response\"]'); return (inp&&inp.value&&inp.value.length>10)?inp.value.slice(0,20)+'...':null; })()")
            if token: logger.info(f"  ✅ Turnstile: {token}"); break
            await tab.sleep(0.5)

        logger.info(f"\n{'='*60}")
        logger.info(f"✅ FORM FILLED — clicking BUY")
        logger.info(f"{'='*60}\n")
        send_telegram(TRIGGER_GROUP_CHAT_ID,
            f"✅ *Form filled* — {date} {slot_time} | {visitors}v\nClicking BUY...")

        # [9] BUY
        logger.info("[9] BUY...")
        clicked = await tab.evaluate("""
            (() => {
                const byId = document.querySelector("button#form-submit[type='submit'].btn-submit");
                if (byId && !byId.disabled) { byId.scrollIntoView(); byId.click(); return 'form-submit'; }
                const submits = Array.from(document.querySelectorAll("button[type='submit']")).filter(b=>!b.disabled);
                if (submits.length) { submits[submits.length-1].click(); return 'submit-btn'; }
                return null;
            })()
        """)
        logger.info(f"  BUY: {clicked}")

        # [10] Wait for epay redirect
        logger.info("[10] Waiting for epay...")
        epay_url_found = ''
        for i in range(120):
            await tab.sleep(0.5)
            try:
                cur = await tab.evaluate("window.location.href")
                if cur and 'epay' in cur:
                    epay_url_found = cur
                    logger.info(f"✅ Redirected to epay: {cur[:80]}")
                    break
                if cur and ('error' in cur.lower() or 'errore' in cur.lower()):
                    logger.warning(f"  Vatican error page: {cur}")
                    try: await tab.save_screenshot('debug_vatican_error.png')
                    except: pass
                    break
                if i == 10:
                    err = await tab.evaluate("(() => { for(const s of ['[class*=\"error\"]','[role=\"alert\"]','mat-snack-bar-container']){const e=document.querySelector(s);if(e&&e.innerText.trim().length>3)return e.innerText.trim().slice(0,150);} return null; })()")
                    if err: logger.warning(f"  Page message: {err}")
            except Exception:
                pass

        if not epay_url_found:
            send_telegram(TRIGGER_GROUP_CHAT_ID, f"❌ No epay redirect for {date} {slot_time}")
            try: requests.post(f'{SERVER_URL}/api/v1/holds/{hold_id}/resume-recap/', timeout=5, proxies={'http': None, 'https': None})
            except: pass
            return

        send_telegram(TRIGGER_GROUP_CHAT_ID, f"💳 *Redirected to epay*\n{date} {slot_time}\nFilling card...")

        # [11] Fill epay form
        logger.info("[11] Filling epay...")
        await tab.sleep(3)

        async def epay_fill(fid, val):
            safe = str(val).replace('`', '\\`')
            await tab.evaluate(f"""
                (() => {{
                    const el = document.querySelector('#{fid}');
                    if (!el) return;
                    el.focus(); el.value = `{safe}`;
                    el.dispatchEvent(new Event('input',  {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    el.blur();
                }})()
            """)

        card = {'holder': '', 'number': '', 'expiry': '', 'cvv': ''}
        try:
            card_r = await asyncio.to_thread(lambda: requests.get(
                f'{SERVER_URL}/api/v1/buyer-card/', timeout=5, proxies={'http': None, 'https': None}
            ))
            if card_r.status_code == 200:
                cd = card_r.json()
                card = {'holder': cd.get('card_holder',''), 'number': cd.get('card_number','').replace(' ',''),
                        'expiry': cd.get('card_expiry',''), 'cvv': cd.get('card_cvv','')}
        except Exception:
            pass

        card_first, *rest = (card['holder'] or f"{profile_data['first_name']} {profile_data['last_name']}").split(' ', 1)
        card_last = rest[0] if rest else card_first
        await epay_fill('name',        card_first)
        await epay_fill('surname',     card_last)
        await epay_fill('email',       profile_data['email'])
        await epay_fill('repeatEmail', profile_data['email'])
        await tab.sleep(0.3)

        if card['number']:
            iframe_el = await tab.query_selector('iframe[name*="cardNumber"],iframe[id*="cardNumber"]')
            if iframe_el:
                await iframe_el.click(); await tab.sleep(0.5)
                for ch in card['number']:
                    await iframe_el.send_keys(ch); await tab.sleep(0.05)
                await tab.sleep(0.3)
                logger.info(f"  Card: {card['number'][:4]}...{card['number'][-4:]}")

        if card['cvv']:
            cvv_el = await tab.query_selector('iframe[name*="cvv"],iframe[id*="cvv"]')
            if cvv_el:
                await cvv_el.click(); await tab.sleep(0.5)
                for ch in card['cvv']:
                    await cvv_el.send_keys(ch); await tab.sleep(0.05)
                await cvv_el.send_keys('\t')
                await tab.sleep(0.3)
                logger.info("  CVV typed")

        if card['expiry']:
            exp_m, exp_y = card['expiry'].split('/')
            exp_m = exp_m.strip().zfill(2)
            exp_y = ('20' + exp_y.strip()) if len(exp_y.strip()) == 2 else exp_y.strip()
            await tab.evaluate("document.querySelectorAll('app-dropdown')[0]?.querySelector('.select__box--selectedValue')?.click()")
            await tab.sleep(0.4)
            await tab.evaluate(f"(() => {{ const items=Array.from(document.querySelectorAll('.select__list--item span')); const mo=items.find(e=>e.textContent.trim()==='{exp_m}'); if(mo) mo.click(); }})()")
            await tab.sleep(0.3)
            await tab.evaluate("document.querySelectorAll('app-dropdown')[1]?.querySelector('.select__box--selectedValue')?.click()")
            await tab.sleep(0.4)
            await tab.evaluate(f"(() => {{ const items=Array.from(document.querySelectorAll('.select__list--item span')); const yr=items.find(e=>e.textContent.trim()==='{exp_y}'); if(yr) yr.click(); }})()")
            await tab.sleep(0.3)
            logger.info(f"  Expiry: {exp_m}/{exp_y}")

        await tab.evaluate("(() => { const cb=document.querySelector('#mat-checkbox-1-input'); if(cb&&!cb.checked) cb.click(); })()")
        await tab.sleep(0.3)

        # [12] PAY
        logger.info("[12] PAY...")
        await tab.evaluate("(() => { document.body.click(); document.activeElement?.blur(); })()")
        await tab.sleep(0.5)
        pay_clicked = await tab.evaluate("""
            (() => {
                const byId = document.querySelector("button#form-submit[type='submit'].btn-submit");
                if (byId && !byId.disabled) { byId.scrollIntoView(); byId.focus(); byId.click(); return 'form-submit'; }
                const byText = Array.from(document.querySelectorAll("button[type='submit']")).find(b=>b.textContent.includes('Paga')&&!b.disabled);
                if (byText) { byText.scrollIntoView(); byText.focus(); byText.click(); return 'paga-text'; }
                return null;
            })()
        """)
        logger.info(f"  PAY clicked: {pay_clicked}")
        send_telegram(TRIGGER_GROUP_CHAT_ID, f"🔄 *PAY clicked* — {date} {slot_time}\nWaiting for bank...")

        # [13] Wait for confirmation / 3DS
        logger.info("[13] Waiting for confirmation...")
        reservation_done = False
        deadline = time.time() + BROWSER_TIMEOUT
        while time.time() < deadline and not reservation_done:
            await asyncio.sleep(0.5)
            try: current_url = await tab.evaluate("window.location.href")
            except: current_url = ''
            if not current_url or current_url == epay_url_found: continue
            if 'feedback/fail' in current_url or ('error' in current_url and 'epay' in current_url):
                logger.warning(f"  ❌ Payment failed: {current_url}")
                send_telegram(TRIGGER_GROUP_CHAT_ID, f"❌ *Payment failed* — {date} {slot_time}\nCheck card details.")
                reservation_done = True; break
            if any(x in current_url for x in ('feedback/success','confirm','success','thank','grazie','receipt')):
                reservation_done = True
                logger.info(f"✅ Payment confirmed: {current_url}")
                send_telegram(TRIGGER_GROUP_CHAT_ID,
                    f"✅ *TICKET BOOKED!*\n📅 {date} {slot_time} | 👥 {visitors}v | €{total}\n🎉 Payment confirmed!")
                try: requests.post(f'{SERVER_URL}/api/v1/mark-paid/', json={'hold_id': hold_id, 'reference': '', 'epay_url': current_url}, timeout=5, proxies={'http': None, 'https': None})
                except: pass
                break
            if current_url != epay_url_found:
                logger.info(f"  Redirected: {current_url[:80]} — waiting for 3DS...")
                send_telegram(TRIGGER_GROUP_CHAT_ID, f"📱 *Approve on your phone!*\n{date} {slot_time}")
                for _ in range(240):
                    await asyncio.sleep(0.5)
                    try: cur2 = await tab.evaluate("window.location.href")
                    except: cur2 = ''
                    if 'feedback/success' in (cur2 or '') or 'confirm' in (cur2 or ''):
                        reservation_done = True
                        send_telegram(TRIGGER_GROUP_CHAT_ID, f"✅ *TICKET BOOKED!*\n📅 {date} {slot_time} | 👥 {visitors}v\n🎉 3DS approved!")
                        try: requests.post(f'{SERVER_URL}/api/v1/mark-paid/', json={'hold_id': hold_id, 'reference': '', 'epay_url': cur2}, timeout=5, proxies={'http': None, 'https': None})
                        except: pass
                        break
                    if 'feedback/fail' in (cur2 or '') or ('error' in (cur2 or '') and 'epay' in (cur2 or '')):
                        send_telegram(TRIGGER_GROUP_CHAT_ID, f"❌ *3DS failed* — {date} {slot_time}")
                        reservation_done = True; break
                break

        if not reservation_done:
            logger.warning("⏰ Timeout — no confirmation")
            send_telegram(TRIGGER_GROUP_CHAT_ID,
                f"⏰ Timeout for {date} {slot_time} — Hold #{hold_id} still active.")
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

    global POLL_INTERVAL
    while True:
        try:
            # ── Register heartbeat every 30s ──
            now = time.time()
            if now - heartbeat_last > 30:
                try:
                    requests.post(
                        f'{SERVER_URL}/api/v1/agent-heartbeat/',
                        json={'agent_id': AGENT_ID, 'hostname': _platform.node(), 'agency_key': AGENCY_KEY},
                        timeout=3, proxies={'http': None, 'https': None}
                    )
                    # Also refresh dynamic config (poll interval) while we're at it
                    cfg_r = requests.get(f'{SERVER_URL}/api/v1/agent-config/', timeout=3, proxies={'http': None, 'https': None})
                    if cfg_r.status_code == 200:
                        new_interval = cfg_r.json().get('poll_interval', POLL_INTERVAL)
                        if float(new_interval) != POLL_INTERVAL:
                            POLL_INTERVAL = float(new_interval)
                            logger.info(f"Dynamic poll interval updated to {POLL_INTERVAL}s")
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

                    async def _run_checkout(s=slot):
                        try:
                            await open_checkout(s)
                        except Exception as exc:
                            logger.error(f"open_checkout crashed: {exc}", exc_info=True)
                            send_telegram(TRIGGER_GROUP_CHAT_ID, f"❌ Browser agent error: {exc}")
                        finally:
                            # Remove from processing set so it can be retried
                            processing_holds.discard(hold_id)

                    asyncio.create_task(_run_checkout())

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

                        async def _run_checkout_slot(s=slot):
                            try:
                                await open_checkout(s)
                            except Exception as exc:
                                logger.error(f"open_checkout crashed: {exc}", exc_info=True)
                                send_telegram(TRIGGER_GROUP_CHAT_ID, f"❌ Browser agent error: {exc}")
                            finally:
                                processing_holds.discard(slot_key)

                        asyncio.create_task(_run_checkout_slot())
                    except Exception as e:
                        logger.error(f"open_browser_slot error: {e}")

        except KeyboardInterrupt:
            logger.info("Stopped.")
            break
        except Exception as e:
            logger.error(f"Main loop error: {e}")

        # Dynamic poll sleep
        await asyncio.sleep(POLL_INTERVAL)


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
