
"""
Vatican Agent — Production
==========================
Standalone agent that:
- Polls server for held slots
- Opens Chrome via nodriver (Turnstile-invisible)
- Fills Vatican checkout form from server profile
- Fills epay card details from server card config
- Sends Telegram notifications at every step
- Supports multiple buyer profiles / card groups
- Speed-optimized: parallel API calls, minimal sleeps before recap

Config: agent_config.json (same directory as this script)

Run:
    python vatican_agent.py
    python vatican_agent.py --agent my-pc-name
    python vatican_agent.py --once --date 09/06/2026 --visitors 2   # one-shot test

Requirements:
    python -m pip install nodriver requests
"""
import asyncio
import json
import os
import sys
import time
import requests
import logging
import argparse
import subprocess
import warnings
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

warnings.filterwarnings('ignore', category=ResourceWarning)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

import platform as _platform

# ── Load config ───────────────────────────────────────────────────────────────
def _load_config():
    base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    for name in ['agent_config.json', 'config.json']:
        p = os.path.join(base, name)
        if os.path.exists(p):
            try:
                with open(p) as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

_cfg = _load_config()

SERVER_URL   = _cfg.get('server_url',   'https://hydrabot.it')
BOT_TOKEN    = _cfg.get('bot_token',    '')
ADMIN_CHAT   = _cfg.get('admin_chat_id','')
TRIGGER_GRP  = _cfg.get('trigger_group','')
POLL_INTERVAL= int(_cfg.get('poll_interval', 2))
AGENT_ID     = _cfg.get('agent_id', _platform.node())
AGENCY_KEY   = _cfg.get('agency_key', 'default')   # unique per agency — keeps agents isolated
CHROME_PATH  = _cfg.get('chrome_path', r'C:\Program Files\Google\Chrome\Application\chrome.exe')
CHROME_PROFILE = _cfg.get('chrome_profile', os.path.join(os.path.expanduser('~'), 'vatican_agent_profile'))

VATICAN_BASE = 'https://tickets.museivaticani.va'
USER_AGENT   = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36'

H = {'Accept': 'application/json, text/plain, */*', 'X-Requested-With': 'XMLHttpRequest',
     'Referer': f'{VATICAN_BASE}/', 'User-Agent': USER_AGENT}

# Local fallback profile (used if server unreachable)
LOCAL_PROFILE = {
    'first_name':  _cfg.get('first_name', 'Mario'),
    'last_name':   _cfg.get('last_name',  'Rossi'),
    'email':       _cfg.get('email',      'mario.rossi@example.com'),
    'phone':       _cfg.get('phone',      '3401234567'),
    'city':        _cfg.get('city',       'Roma'),
    'country':     _cfg.get('country',    'Italy'),
    'gender':      _cfg.get('gender',     'M'),
    'birth_year':  str(_cfg.get('birth_year',  1990)),
    'birth_month': _cfg.get('birth_month', 'GEN'),
    'birth_day':   str(_cfg.get('birth_day',   15)).zfill(2),
    'birth_date_iso': _cfg.get('birth_date_iso', '1990-01-14T23:00:00.000Z'),
    'language':    _cfg.get('language', 'it'),
}

LOCAL_CARD = {
    'holder':  _cfg.get('card_holder', ''),
    'number':  _cfg.get('card_number', ''),
    'expiry':  _cfg.get('card_expiry', ''),
    'cvv':     _cfg.get('card_cvv',    ''),
}

processed_slots = set()

# ── Telegram helpers ──────────────────────────────────────────────────────────
def tg(chat_id, msg, reply_markup=None, parse_mode='Markdown'):
    payload = {'chat_id': chat_id, 'text': msg, 'parse_mode': parse_mode}
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    try:
        requests.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                      json=payload, timeout=6, proxies={'http': None, 'https': None})
    except Exception:
        pass

def tg_all(msg, reply_markup=None):
    """Send to admin + trigger group."""
    tg(ADMIN_CHAT, msg, reply_markup)
    if TRIGGER_GRP and TRIGGER_GRP != ADMIN_CHAT:
        tg(TRIGGER_GRP, msg, reply_markup)

# ── Server helpers ────────────────────────────────────────────────────────────
def api_get(path, params=None, timeout=5):
    try:
        r = requests.get(f'{SERVER_URL}/api/v1/{path}', params=params,
                         timeout=timeout, proxies={'http': None, 'https': None})
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def api_post(path, data=None, timeout=5):
    try:
        r = requests.post(f'{SERVER_URL}/api/v1/{path}', json=data or {},
                          timeout=timeout, proxies={'http': None, 'https': None})
        return r.json() if r.status_code in (200, 201) else None
    except Exception:
        return None

def fetch_profile(group_id=None):
    """Fetch buyer profile from server, fall back to local config."""
    params = {'group_id': group_id} if group_id else {}
    data = api_get('buyer-profile/', params)
    if not data:
        return LOCAL_PROFILE.copy()
    from datetime import date as _date
    bd = data.get('birth_date') or ''  # YYYY-MM-DD
    month_map = {'01':'GEN','02':'FEB','03':'MAR','04':'APR','05':'MAG','06':'GIU',
                 '07':'LUG','08':'AGO','09':'SET','10':'OTT','11':'NOV','12':'DIC'}
    birth_year, birth_month_num, birth_day = '1990', '01', '15'
    if bd:
        parts = bd.split('-')
        if len(parts) == 3:
            birth_year, birth_month_num, birth_day = parts[0], parts[1], parts[2]
    birth_month = month_map.get(birth_month_num, 'GEN')
    # ISO: day before at 23:00 UTC
    try:
        from datetime import datetime as _dt
        d = _dt(int(birth_year), int(birth_month_num), int(birth_day))
        prev = d - timedelta(days=1)
        birth_iso = prev.strftime('%Y-%m-%dT23:00:00.000Z')
    except Exception:
        birth_iso = f'{birth_year}-{birth_month_num}-{str(int(birth_day)-1).zfill(2)}T23:00:00.000Z'
    return {
        'first_name':  data.get('first_name', LOCAL_PROFILE['first_name']),
        'last_name':   data.get('last_name',  LOCAL_PROFILE['last_name']),
        'email':       data.get('email',      LOCAL_PROFILE['email']),
        'phone':       data.get('phone',      LOCAL_PROFILE['phone']).lstrip('+39').lstrip('+'),
        'city':        data.get('city',       LOCAL_PROFILE['city']),
        'country':     data.get('country',    LOCAL_PROFILE['country']),
        'gender':      data.get('gender',     LOCAL_PROFILE['gender']),
        'birth_year':  birth_year,
        'birth_month': birth_month,
        'birth_day':   birth_day.zfill(2),
        'birth_date_iso': birth_iso,
        'language':    data.get('language',   LOCAL_PROFILE['language']),
        'participants': data.get('participants', []),
    }

def fetch_card(group_id=None):
    """Fetch card details from server, fall back to local config."""
    params = {'group_id': group_id} if group_id else {}
    data = api_get('buyer-card/', params)
    if not data:
        return LOCAL_CARD.copy()
    return {
        'holder':  data.get('card_holder', LOCAL_CARD['holder']),
        'number':  data.get('card_number', LOCAL_CARD['number']).replace(' ', ''),
        'expiry':  data.get('card_expiry', LOCAL_CARD['expiry']),
        'cvv':     data.get('card_cvv',    LOCAL_CARD['cvv']),
    }

def heartbeat():
    api_post('agent-heartbeat/', {'agent_id': AGENT_ID, 'hostname': _platform.node(), 'agency_key': AGENCY_KEY})

def find_slot(target_date, visitors):
    """Scan Vatican Search API for available slot. Returns slot dict or None."""
    s = requests.Session()
    EXCLUDED = ['pellegrinaggi', 'lunch', 'pranzo', 'gruppi', 'specola', 'palazzo', 'didattiche']
    dates = [target_date] if target_date else [
        (datetime.now() + timedelta(days=i)).strftime('%d/%m/%Y')
        for i in range(1, 120)
        if (datetime.now() + timedelta(days=i)).weekday() != 6
    ]
    for date_str in dates:
        try:
            r = s.get(f'{VATICAN_BASE}/api/search/resultPerTag', params={
                'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date_str,
                'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
            }, headers=H, timeout=8)
            if r.status_code != 200:
                continue
            visits = r.json().get('visits', [])
            ticket = next((v for v in visits
                           if 'musei vaticani' in v.get('name', '').lower()
                           and 'ingresso' in v.get('name', '').lower()
                           and not any(x in v.get('name', '').lower() for x in EXCLUDED)
                           and v.get('availability') != 'SOLD_OUT'), None)
            if not ticket:
                continue
            tid = str(ticket['id'])
            r2 = s.get(f'{VATICAN_BASE}/api/visit/timeavail', params={
                'lang': 'it', 'visitLang': '', 'visitTypeId': tid,
                'visitorNum': str(visitors), 'visitDate': date_str,
            }, headers=H, timeout=8)
            if r2.status_code != 200:
                continue
            slots = [sl for sl in r2.json().get('timetable', []) if sl.get('availability') == 'AVAILABLE']
            if not slots:
                continue
            best = slots[0]
            logger.info(f"✅ Slot found: {date_str} {best['time']}")
            return {'date': date_str, 'slot_id': str(best['id']),
                    'slot_time': best['time'], 'ticket_id': tid, 'visitors': visitors}
        except Exception as e:
            logger.debug(f"Scan error {date_str}: {e}")
        time.sleep(0.2)
    return None

# ── Browser flow ──────────────────────────────────────────────────────────────
async def run_checkout(slot: dict, profile: dict, card: dict, hold_id=None):
    import nodriver as uc

    visitors  = int(slot.get('visitors', 2))
    date      = slot['date']
    slot_time = slot['slot_time']
    tid       = slot['ticket_id']
    participants = profile.get('participants', [])

    rome = ZoneInfo('Europe/Rome')
    d, m, y = date.split('/')
    ts = int(datetime(int(y), int(m), int(d), 0, 0, 0, tzinfo=rome).timestamp() * 1000)
    entry_url = f'{VATICAN_BASE}/home/fromtag/{visitors}/{ts}/MV-Biglietti/1'

    logger.info(f"🚀 Launching nodriver Chrome...")
    tg_all(f"🌐 *Opening browser*\n📅 {date} {slot_time} | 👥 {visitors}v\nTurnstile auto-solving...")

    # Kill stale Chrome + clean lockfiles
    subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe', '/T'], capture_output=True)
    await asyncio.sleep(0.5)
    for lf in ['lockfile', 'SingletonLock', 'SingletonCookie']:
        p = os.path.join(CHROME_PROFILE, lf)
        try:
            if os.path.exists(p): os.remove(p)
        except Exception:
            pass

    browser = await uc.start(
        user_data_dir=CHROME_PROFILE,
        browser_executable_path=CHROME_PATH,
        headless=False, lang='it-IT', no_sandbox=True,
    )
    tab = browser.main_tab

    async def js(code): return await tab.evaluate(code)
    async def wait(s): await tab.sleep(s)

    try:
        # ── [1] Navigate — wait for ticket buttons ────────────────────────────
        logger.info(f"[1] {entry_url}")
        await tab.get(entry_url)
        for _ in range(30):
            c = await js("document.querySelectorAll(\"[data-cy^='bookTicket_']\").length")
            if c and int(c) > 0: break
            await wait(0.5)
        await wait(0.5)

        # ── [2] Fresh ticket ID via Search API (parallel with page load) ──────
        logger.info("[2] Search API...")
        r = requests.get(f'{VATICAN_BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=H, timeout=10)
        visits = r.json().get('visits', []) if r.status_code == 200 else []
        t = next((v for v in visits if 'musei vaticani' in v.get('name','').lower()
                  and 'ingresso' in v.get('name','').lower()), None)
        if t: tid = str(t['id'])
        logger.info(f"  ticket_id={tid}")

        # ── [3] Find & click PRENOTA ──────────────────────────────────────────
        logger.info("[3] PRENOTA...")
        dom_tid = None
        for _ in range(10):
            dom_tid = await js("""
                (() => {
                    for (const card of document.querySelectorAll('[id^="ticket_"]')) {
                        const txt = card.innerText.toLowerCase();
                        if (txt.includes('musei vaticani') && (txt.includes('ingresso') || txt.includes('biglietti'))) {
                            const btn = card.querySelector("[data-cy^='bookTicket_']");
                            if (btn) return btn.getAttribute('data-cy').replace('bookTicket_','');
                        }
                    }
                    for (const btn of document.querySelectorAll("[data-cy^='bookTicket_']"))
                        if (btn.innerText.trim()==='PRENOTA') return btn.getAttribute('data-cy').replace('bookTicket_','');
                    return null;
                })()
            """)
            if dom_tid: break
            await wait(0.4)
        if dom_tid: tid = dom_tid
        await js(f"document.querySelector(\"[data-cy='bookTicket_{tid}']\")?.click()")
        await wait(1.5)

        # ── [4] Quantity ──────────────────────────────────────────────────────
        logger.info(f"[4] qty={visitors}")
        for _ in range(8):
            has = await js("!!(document.querySelector('select')||document.querySelector(\"[data-cy='ticketQuantity']\"))")
            if has: break
            await wait(0.4)
        qty = await js(f"""
            (() => {{
                const sel = document.querySelector('select');
                if (sel) {{ sel.value='{visitors}'; sel.dispatchEvent(new Event('change',{{bubbles:true}})); return 'select'; }}
                const el = document.querySelector("[data-cy='ticketQuantity']");
                if (el) {{ el.click(); return 'dropdown'; }}
                return null;
            }})()
        """)
        if qty == 'dropdown':
            await wait(0.6)
            await js(f"""
                (() => {{
                    const items = Array.from(document.querySelectorAll("[data-cy='ticketQuantitySection']"));
                    for (const it of items) {{
                        const t = it.innerText.trim();
                        if (t==='{visitors}' || t.startsWith('{visitors} ')) {{ it.click(); return; }}
                    }}
                    if (items.length>={visitors}) items[{visitors}-1].click();
                    else if (items.length) items[items.length-1].click();
                }})()
            """)
        await wait(1.2)

        # ── [5] Time slot ─────────────────────────────────────────────────────
        logger.info(f"[5] time={slot_time}")
        target_mins = int(slot_time.split(':')[0])*60 + int(slot_time.split(':')[1]) if slot_time else 0
        for _ in range(20):
            c = await js("document.querySelectorAll(\"[data-cy='time']\").length")
            if c and int(c) > 0: break
            await wait(0.4)
        if target_mins >= 14*60:
            await js("(() => { const tabs=Array.from(document.querySelectorAll('.tab')).filter(e=>e.offsetParent); if(tabs[1]) tabs[1].click(); })()")
            await wait(0.6)
        await js(f"""
            (() => {{
                const cells = Array.from(document.querySelectorAll("[data-cy='time']"));
                for (const c of cells) {{
                    const txt = c.innerText.trim();
                    if (txt==='{slot_time}' || txt.startsWith('{slot_time}')) {{ c.scrollIntoView(); c.click(); return; }}
                    const num = c.querySelector('div.muvaCalendarNumber,div');
                    if (num && num.innerText.trim()==='{slot_time}') {{ c.scrollIntoView(); c.click(); return; }}
                }}
                const target={target_mins};
                let best=null,bestDiff=9999;
                for (const c of cells) {{
                    const parts=c.innerText.trim().split('\\n')[0].split(':');
                    if (parts.length!==2) continue;
                    const mins=parseInt(parts[0])*60+parseInt(parts[1]);
                    const diff=Math.abs(mins-target);
                    if (diff<bestDiff) {{ bestDiff=diff; best=c; }}
                }}
                if (best) {{ best.scrollIntoView(); best.click(); }}
            }})()
        """)
        await wait(1.5)

        # ── [6] PROCEDI ───────────────────────────────────────────────────────
        logger.info("[6] PROCEDI")
        for _ in range(10):
            has = await js("!!(document.querySelector(\"[data-cy='bookVisit']\"))")
            if has: break
            await wait(0.4)
        await js("(() => { const b=document.querySelector(\"[data-cy='bookVisit']\")||Array.from(document.querySelectorAll('button')).find(b=>/PROCEDI/i.test(b.textContent)); if(b) b.click(); })()")
        await wait(4)

        # ── [7] Wait for form ─────────────────────────────────────────────────
        logger.info("[7] Waiting for form...")
        form_ok = False
        for _ in range(60):
            el = await js("document.querySelector(\"[data-cy='managerSurname']\")?.tagName")
            if el: form_ok = True; break
            await wait(0.5)
        if not form_ok:
            logger.warning("Form not found — screenshot saved")
            try: await tab.save_screenshot('debug_form.png')
            except: pass

        # ── [8] Fill form ─────────────────────────────────────────────────────
        logger.info("[8] Filling form...")

        async def fill(sel, val):
            safe = str(val).replace('`','\\`').replace('\\','\\\\')
            await js(f"""
                (() => {{
                    const el=document.querySelector(`{sel}`);
                    if(!el) return;
                    el.focus(); el.value=''; el.value=`{safe}`;
                    el.dispatchEvent(new Event('input',{{bubbles:true}}));
                    el.dispatchEvent(new Event('change',{{bubbles:true}}));
                    el.blur();
                }})()
            """)

        await fill("[data-cy='managerSurname']",     profile['last_name'])
        await fill("[data-cy='managerName']",         profile['first_name'])
        await fill("[data-cy='managerCity']",         profile['city'])
        await fill("[data-cy='managerEmail']",        profile['email'])
        await fill("[data-cy='managerConfirmEmail']", profile['email'])
        await fill("[data-cy='managerPhone']",        profile['phone'])
        await wait(0.3)

        # Gender
        await js("document.querySelector(\"[data-cy='managerSex']\")?.click()")
        await wait(0.3)
        await js("document.querySelector(\"[data-cy='managerSexSection']\")?.click()")
        await wait(0.3)

        # Country
        await js("document.querySelector(\"[data-cy='managerCountry']\")?.click()")
        await wait(0.3)
        cp = profile['country'][:4]
        await js(f"(() => {{ const s=document.querySelector('#searchInput_country'); if(s) {{ s.value='{cp}'; s.dispatchEvent(new Event('input',{{bubbles:true}})); }} }})()")
        await wait(0.4)
        await js("document.querySelector(\"[data-cy='managerCountrySection']\")?.click()")
        await wait(0.3)

        # Birth date
        logger.info("[8b] Birth date...")
        by = profile['birth_year']
        bm = profile['birth_month']
        bd = profile['birth_day'].zfill(2)
        month_map = {'GEN':'01','FEB':'02','MAR':'03','APR':'04','MAG':'05','GIU':'06',
                     'LUG':'07','AGO':'08','SET':'09','OTT':'10','NOV':'11','DIC':'12'}
        bm_num = month_map.get(bm.upper(), '01')
        b_display = f"{bd}/{bm_num}/{by}"

        # Try direct value injection first (fastest)
        set_ok = await js(f"""
            (() => {{
                const inp = document.querySelector("[data-cy='dateCalendar']");
                if (!inp) return false;
                inp.removeAttribute('readonly');
                inp.focus(); inp.value='{b_display}';
                inp.dispatchEvent(new Event('input',{{bubbles:true}}));
                inp.dispatchEvent(new Event('change',{{bubbles:true}}));
                inp.dispatchEvent(new KeyboardEvent('keydown',{{key:'Enter',bubbles:true}}));
                inp.setAttribute('readonly','true');
                return inp.value;
            }})()
        """)
        await wait(0.4)

        if not set_ok or set_ok == '':
            # Calendar picker fallback
            await js("document.querySelector(\"mat-datepicker-toggle button[aria-label='Open calendar']\")?.click()")
            await wait(0.8)
            for _ in range(2):
                multi = await js("document.querySelectorAll('.mat-calendar-body-cell').length > 12")
                if multi: break
                await js("document.querySelector('button.mat-calendar-period-button')?.click()")
                await wait(0.4)
            for _ in range(30):
                found = await js(f"""
                    (() => {{
                        const cells=Array.from(document.querySelectorAll('.mat-calendar-body-cell'));
                        const yr=cells.find(c=>c.textContent.trim()==='{by}');
                        if(yr) {{ yr.click(); return true; }}
                        document.querySelector('.mat-calendar-previous-button')?.click();
                        return false;
                    }})()
                """)
                await wait(0.3)
                if found: break
            await wait(0.4)
            await js(f"(() => {{ const cells=Array.from(document.querySelectorAll('.mat-calendar-body-cell')); const mo=cells.find(c=>c.textContent.trim().toUpperCase()==='{bm}'); if(mo) mo.click(); }})()")
            await wait(0.4)
            bd_s = bd.lstrip('0') or '1'
            await js(f"(() => {{ const cells=Array.from(document.querySelectorAll('span.mat-calendar-body-cell-content')); const day=cells.find(c=>c.textContent.trim()==='{bd_s}'); if(day) day.click(); }})()")
            await wait(0.3)

        set_date = await js("document.querySelector(\"[data-cy='dateCalendar']\")?.value || ''")
        logger.info(f"  Birth date: {b_display} → field: {set_date}")

        # Language
        await js("document.querySelector(\"[data-cy='managerLanguage']\")?.click()")
        await wait(0.3)
        await js("document.querySelector(\"[data-cy='managerLanguageSection']\")?.click()")
        await wait(0.3)

        # Participants
        for i in range(visitors):
            if i > 0:
                await js(f"(() => {{ const el=document.querySelector('#participantElement_{i} div.tw-flex-grow > div'); if(el) el.click(); }})()")
                await wait(0.4)
            p_first = participants[i].get('first_name', profile['first_name']) if i < len(participants) else profile['first_name']
            p_last  = participants[i].get('last_name',  profile['last_name'])  if i < len(participants) else profile['last_name']
            await fill(f"#participantSurname_{i}", p_last)
            await fill(f"#participantName_{i}",    p_first)

        # GDPR checkboxes
        cb1 = await js("document.querySelector('#mat-mdc-checkbox-1-input')?.checked")
        if cb1 is False:
            await js("document.querySelector('#mat-mdc-checkbox-1-input')?.click()")
            await wait(1.5)
            await js("(() => { const c=document.querySelector(\"[data-cy='purchase-rules-close-btn']\")||Array.from(document.querySelectorAll('button')).find(b=>/chiudi|close/i.test(b.textContent)); if(c) c.click(); })()")
            await wait(0.8)
        await js("(() => { const cb=document.querySelector('#mat-mdc-checkbox-3-input')||document.querySelector('#mat-mdc-checkbox-4-input'); if(cb&&!cb.checked) cb.click(); })()")
        await wait(0.5)

        cb_status = await js("({cb1: document.querySelector('#mat-mdc-checkbox-1-input')?.checked, cb3: document.querySelector('#mat-mdc-checkbox-3-input')?.checked, cb4: document.querySelector('#mat-mdc-checkbox-4-input')?.checked})")
        logger.info(f"  Checkboxes: {cb_status}")

        tg_all(f"✅ *Form filled* — {date} {slot_time} | {visitors}v\nTurnstile solving...")

        # ── [9] BUY ───────────────────────────────────────────────────────────
        logger.info("[9] BUY...")
        try: await tab.save_screenshot('debug_before_buy.png')
        except: pass
        clicked = await js("""
            (() => {
                const byId=document.querySelector("button#form-submit[type='submit'].btn-submit");
                if(byId&&!byId.disabled){byId.scrollIntoView();byId.click();return 'form-submit';}
                const submits=Array.from(document.querySelectorAll("button[type='submit']")).filter(b=>!b.disabled);
                if(submits.length){submits[submits.length-1].click();return 'submit-btn';}
                return null;
            })()
        """)
        logger.info(f"  BUY: {clicked}")

        # ── [10] Wait for epay ────────────────────────────────────────────────
        logger.info("[10] Waiting for epay...")
        epay_url = ''
        for _ in range(120):
            await wait(0.5)
            try:
                cur = await js("window.location.href")
                if cur and 'epay' in cur:
                    epay_url = cur
                    logger.info(f"  ✅ epay: {epay_url[:80]}")
                    break
                err = await js("(() => { const e=document.querySelector('.error-message,[class*=\"error\"]'); return e?e.innerText.trim().slice(0,100):null; })()")
                if err: logger.warning(f"  Page error: {err}")
            except Exception:
                pass

        if not epay_url:
            tg_all(f"❌ No epay redirect for {date} {slot_time}")
            return None

        tg_all(f"💳 *Redirected to epay*\n{date} {slot_time}\nFilling card...")

        # ── [11] Fill epay form ───────────────────────────────────────────────
        logger.info("[11] Filling epay...")
        await wait(3)

        async def epay_fill(fid, val):
            safe = str(val).replace('`','\\`')
            await js(f"""
                (() => {{
                    const el=document.querySelector('#{fid}');
                    if(!el) return;
                    el.focus(); el.value=`{safe}`;
                    el.dispatchEvent(new Event('input',{{bubbles:true}}));
                    el.dispatchEvent(new Event('change',{{bubbles:true}}));
                    el.blur();
                }})()
            """)

        card_first, *rest = card['holder'].split(' ', 1)
        card_last = rest[0] if rest else card_first
        await epay_fill('name',        card_first)
        await epay_fill('surname',     card_last)
        await epay_fill('email',       profile['email'])
        await epay_fill('repeatEmail', profile['email'])
        await wait(0.3)

        # Card number — Datatrans iframe, digit by digit
        iframe_el = await tab.query_selector('iframe[name*="cardNumber"],iframe[id*="cardNumber"]')
        if iframe_el:
            await iframe_el.click(); await wait(0.5)
            for ch in card['number']:
                await iframe_el.send_keys(ch); await wait(0.05)
            await wait(0.3)
            logger.info(f"  Card: {card['number'][:4]}...{card['number'][-4:]}")

        # CVV — Datatrans iframe
        cvv_el = await tab.query_selector('iframe[name*="cvv"],iframe[id*="cvv"]')
        if cvv_el:
            await cvv_el.click(); await wait(0.5)
            for ch in card['cvv']:
                await cvv_el.send_keys(ch); await wait(0.05)
            await cvv_el.send_keys('\t')  # blur iframe
            await wait(0.3)
            logger.info("  CVV typed")

        # Expiry dropdowns
        exp_m, exp_y = card['expiry'].split('/')
        exp_m = exp_m.strip().zfill(2)
        exp_y = ('20' + exp_y.strip()) if len(exp_y.strip()) == 2 else exp_y.strip()
        await js("document.querySelectorAll('app-dropdown')[0]?.querySelector('.select__box--selectedValue')?.click()")
        await wait(0.4)
        await js(f"(() => {{ const items=Array.from(document.querySelectorAll('.select__list--item span')); const mo=items.find(e=>e.textContent.trim()==='{exp_m}'); if(mo) mo.click(); }})()")
        await wait(0.3)
        await js("document.querySelectorAll('app-dropdown')[1]?.querySelector('.select__box--selectedValue')?.click()")
        await wait(0.4)
        await js(f"(() => {{ const items=Array.from(document.querySelectorAll('.select__list--item span')); const yr=items.find(e=>e.textContent.trim()==='{exp_y}'); if(yr) yr.click(); }})()")
        await wait(0.3)

        # Agreement checkbox
        await js("(() => { const cb=document.querySelector('#mat-checkbox-1-input'); if(cb&&!cb.checked) cb.click(); })()")
        await wait(0.3)
        logger.info(f"  Expiry: {exp_m}/{exp_y} | Agreement ticked")

        # ── [12] PAY ──────────────────────────────────────────────────────────
        logger.info("[12] PAY...")
        await js("(() => { document.body.click(); document.activeElement?.blur(); })()")
        await wait(0.5)
        pay_clicked = await js("""
            (() => {
                const byId=document.querySelector("button#form-submit[type='submit'].btn-submit");
                if(byId&&!byId.disabled){byId.scrollIntoView();byId.focus();byId.click();return 'form-submit';}
                const byText=Array.from(document.querySelectorAll("button[type='submit']")).find(b=>b.textContent.includes('Paga')&&!b.disabled);
                if(byText){byText.scrollIntoView();byText.focus();byText.click();return 'paga-text';}
                return null;
            })()
        """)
        logger.info(f"  PAY clicked: {pay_clicked}")
        tg_all(f"🔄 *PAY clicked* — {date} {slot_time}\nWaiting for bank response...")

        # ── [13] Wait for confirmation / 3DS ─────────────────────────────────
        logger.info("[13] Waiting for confirmation...")
        confirm_url = ''
        for _ in range(120):
            await wait(0.5)
            try:
                cur = await js("window.location.href")
                if not cur or cur == epay_url: continue
                if 'feedback/fail' in cur or 'error' in cur:
                    logger.warning(f"  ❌ Payment failed: {cur}")
                    tg_all(f"❌ *Payment failed* — {date} {slot_time}\nCheck card details.")
                    break
                if any(x in cur for x in ('feedback/success','confirm','success','thank','grazie','receipt')):
                    confirm_url = cur
                    logger.info(f"  ✅ Confirmed: {confirm_url}")
                    tg_all(f"✅ *TICKET BOOKED!*\n📅 {date} {slot_time} | 👥 {visitors}v\n🎉 Payment confirmed!")
                    break
                if cur != epay_url:
                    logger.info(f"  Redirected: {cur[:80]} — waiting for 3DS...")
                    tg_all(f"📱 *3DS challenge* — approve on your phone!\n{date} {slot_time}")
                    for _ in range(240):
                        await wait(0.5)
                        cur2 = await js("window.location.href")
                        if 'feedback/success' in (cur2 or '') or 'confirm' in (cur2 or ''):
                            confirm_url = cur2
                            tg_all(f"✅ *TICKET BOOKED!*\n📅 {date} {slot_time} | 👥 {visitors}v\n🎉 3DS approved!")
                            break
                        if 'feedback/fail' in (cur2 or '') or 'error' in (cur2 or ''):
                            tg_all(f"❌ *3DS failed* — {date} {slot_time}")
                            break
                    break
            except Exception:
                pass

        if not confirm_url:
            logger.info("  No confirmation URL — browser stays open 60s")
            await wait(60)

        # Mark paid on server
        if confirm_url and hold_id:
            api_post('mark-paid/', {'hold_id': hold_id, 'reference': '', 'epay_url': confirm_url})

        return {'epay_url': epay_url, 'confirm_url': confirm_url, 'slot': slot}

    except Exception as e:
        logger.error(f"Checkout error: {e}")
        import traceback; traceback.print_exc()
        tg_all(f"❌ *Checkout error*: {e}")
        return None
    finally:
        try: await wait(3); browser.stop()
        except: pass

# ── Main loop ─────────────────────────────────────────────────────────────────
async def main_loop():
    logger.info(f"🤖 Vatican Agent [{AGENT_ID}] started — polling {SERVER_URL}")
    tg_all(f"🤖 *Agent online*: `{AGENT_ID}`\nPolling every {POLL_INTERVAL}s")
    last_hb = 0

    while True:
        try:
            now = time.time()
            if now - last_hb > 30:
                heartbeat()
                last_hb = now

            # Check for pending browser tasks from server (agency-scoped)
            pending = api_get(f'browser-pending/', {'agent_id': AGENT_ID, 'agency_key': AGENCY_KEY})
            if pending and isinstance(pending, list):
                for task in pending:
                    slot_id = str(task.get('id') or task.get('slot_id', ''))
                    if slot_id in processed_slots:
                        continue
                    processed_slots.add(slot_id)

                    group_id = task.get('group_id')
                    profile  = fetch_profile(group_id)
                    card     = fetch_card(group_id)

                    slot = {
                        'date':      task.get('date', ''),
                        'slot_id':   task.get('slot_id', ''),
                        'slot_time': task.get('slot_time', ''),
                        'ticket_id': task.get('ticket_id', ''),
                        'visitors':  int(task.get('visitors', 2)),
                    }
                    hold_id = task.get('hold_id') or task.get('id')
                    logger.info(f"📋 Task: {slot['date']} {slot['slot_time']} | {slot['visitors']}v | hold={hold_id}")
                    await run_checkout(slot, profile, card, hold_id=hold_id)

        except Exception as e:
            logger.error(f"Loop error: {e}")

        await asyncio.sleep(POLL_INTERVAL)


async def main_once(target_date, visitors):
    """One-shot mode: find slot and book it immediately."""
    logger.info(f"🔍 One-shot: {target_date or 'auto'} | {visitors}v")
    slot = await asyncio.to_thread(find_slot, target_date, visitors)
    if not slot:
        logger.error("No slot found.")
        return
    profile = fetch_profile()
    card    = fetch_card()
    if not card['number']:
        logger.error("No card configured. Set card_number in agent_config.json or server BuyerProfile.")
        return
    result = await run_checkout(slot, profile, card)
    if result and result.get('confirm_url'):
        logger.info(f"✅ Done: {result['confirm_url']}")
    else:
        logger.info("Flow complete — check browser/Telegram for status.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent',    default=None, help='Agent ID override')
    parser.add_argument('--once',     action='store_true', help='One-shot: find+book then exit')
    parser.add_argument('--date',     default=None, help='DD/MM/YYYY for one-shot mode')
    parser.add_argument('--visitors', type=int, default=2)
    args = parser.parse_args()

    if args.agent:
        AGENT_ID = args.agent

    if args.once:
        asyncio.run(main_once(args.date, args.visitors))
    else:
        asyncio.run(main_loop())
