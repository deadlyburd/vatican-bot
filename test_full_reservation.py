"""
Full Vatican Reservation Test — nodriver (Cloudflare Turnstile bypass)
=======================================================================
1. Scan for available slot (via Search API)
2. Open Chrome via nodriver (invisible to Cloudflare Turnstile)
3. Full UI flow: ticket → quantity → time → PROCEDI → form → BUY
4. Captures epay URL

Run:
    python test_full_reservation.py
    python test_full_reservation.py --date 09/06/2026 --visitors 2

Requirements:
    pip install nodriver requests
"""
import asyncio
import sys
import os
import time
import json
import requests
import argparse
import warnings
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Suppress nodriver/Windows pipe cleanup noise on exit
warnings.filterwarnings('ignore', category=ResourceWarning)

# ── CONFIG ────────────────────────────────────────────────────────────────────
VATICAN_BASE   = 'https://tickets.museivaticani.va'
CHROME_PATH    = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
CHROME_PROFILE = os.path.join(os.path.expanduser('~'), 'vatican_test_profile')
USER_AGENT     = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/136.0.0.0 Safari/537.36')

PROFILE = {
    'first_name':  'Mario',
    'last_name':   'Rossi',
    'email':       'mario.rossi@example.com',
    # Vatican phone field: no country code, digits only
    'phone':       '3401234567',
    'city':        'Roma',
    'country':     'Italia',   # Must be Italian — Vatican validates this server-side
    # Birth date — must be an adult (18+). Vatican rejects minors.
    # Calendar uses Italian month abbreviations.
    'birth_year':  '1990',
    'birth_month': 'GEN',   # GEN FEB MAR APR MAG GIU LUG AGO SET OTT NOV DIC
    'birth_day':   '15',
    # ISO date sent in reservation body — must match above
    # Format: day before at 23:00 UTC (Vatican's timezone offset)
    'birth_date_iso': '1990-01-14T23:00:00.000Z',
}

# ── PAYMENT CARD ─────────────────────────────────────────────────────────────
# Fill in your real card details here, then run with --autopay to complete payment.
# AUTO_PAY = False  → bot fills the form but stops before clicking PAY (safe to test)
# AUTO_PAY = True   → bot clicks PAY automatically (use only with a real card)
AUTO_PAY = True    # ← change to False if you just want to review before paying

CARD = {
    'holder':  'ABIILESH SEKAR',   # ← Name exactly as printed on card (uppercase)
    'number':  '4569331515529372',  # ← Your card number (no spaces)
    'expiry':  '07/28',         # ← MM/YY
    'cvv':     '721',           # ← 3 or 4 digit security code
}

H = {
    'Accept': 'application/json, text/plain, */*',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{VATICAN_BASE}/',
    'User-Agent': USER_AGENT,
}
# ─────────────────────────────────────────────────────────────────────────────


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# ── STEP 1: Find slot via Search API ─────────────────────────────────────────

def find_slot(target_date, visitors):
    proxy_str = None
    try:
        sys.path.insert(0, 'backend')
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
        import django; django.setup()
        from monitors.tasks_search_api import get_proxy_str
        proxy_str, _ = get_proxy_str('vatican')
    except Exception:
        pass

    s = requests.Session()
    if proxy_str:
        s.proxies = {'http': proxy_str, 'https': proxy_str}
        print(f"  Proxy: {proxy_str.split('@')[1] if '@' in proxy_str else proxy_str}")

    try:
        s.get(f'{VATICAN_BASE}/home', headers={'User-Agent': USER_AGENT}, timeout=8)
    except Exception:
        pass

    EXCLUDED = ['pellegrinaggi', 'lunch', 'pranzo', 'gruppi', 'specola', 'palazzo', 'didattiche']
    
    if target_date:
        dates = [target_date]
    else:
        # Scan from today up to 120 days ahead, skip Sundays
        dates = []
        for i in range(1, 120):
            future_date = datetime.now() + timedelta(days=i)
            # Skip Sundays (weekday 6)
            if future_date.weekday() != 6:
                dates.append(future_date.strftime('%d/%m/%Y'))

    for date_str in dates:
        sys.stdout.write(f"\r  Scanning {date_str}...")
        sys.stdout.flush()
        try:
            r = s.get(f'{VATICAN_BASE}/api/search/resultPerTag', params={
                'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date_str,
                'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
            }, headers=H, timeout=8)
            if r.status_code != 200:
                continue

            visits = r.json().get('visits', [])
            for v in visits:
                if 'musei vaticani' in v.get('name', '').lower():
                    try:
                        avail_status = v.get('availability', '')
                        # Show availability status
                        if avail_status == 'AVAILABLE':
                            sys.stdout.write(f"\r  {date_str} -> {v.get('name','')} [AVAILABLE] - checking slots...   ")
                        else:
                            sys.stdout.write(f"\r  {date_str} -> {v.get('name','')} [{avail_status}]   ")
                        sys.stdout.flush()
                    except UnicodeEncodeError:
                        # Windows console encoding issue - skip the arrow
                        sys.stdout.write(f"\r  {date_str} {v.get('name','')} [{v.get('availability','')}]   ")
                        sys.stdout.flush()

            ticket = next((v for v in visits
                           if 'musei vaticani' in v.get('name', '').lower()
                           and 'ingresso' in v.get('name', '').lower()
                           and not any(x in v.get('name', '').lower() for x in EXCLUDED)
                           and v.get('availability') == 'AVAILABLE'), None)
            if not ticket:
                continue

            tid = str(ticket['id'])
            r2 = s.get(f'{VATICAN_BASE}/api/visit/timeavail', params={
                'lang': 'it', 'visitLang': '', 'visitTypeId': tid,
                'visitorNum': str(visitors), 'visitDate': date_str,
            }, headers=H, timeout=8)
            if r2.status_code != 200:
                continue

            # Only accept slots with AVAILABLE status (not SOLD_OUT or other statuses)
            slots = [sl for sl in r2.json().get('timetable', [])
                     if sl.get('availability') == 'AVAILABLE']
            if not slots:
                # Skip this date if no AVAILABLE slots
                continue

            best = slots[0]
            try:
                print(f"\n  Found: {date_str} {best['time']} (slot_id={best['id']})")
            except UnicodeEncodeError:
                print(f"\n  Found: {date_str} {best['time']} (slot_id={best['id']})")
            return {'date': date_str, 'slot_id': str(best['id']),
                    'slot_time': best['time'], 'ticket_id': tid, 'visitors': visitors}

        except Exception as e:
            print(f"\n  Error {date_str}: {e}")
        time.sleep(0.3)

    print("\n  No slots found.")
    return None


# ── STEP 2: Full browser flow via nodriver ────────────────────────────────────

async def run_in_browser(slot):
    import nodriver as uc

    visitors  = slot['visitors']
    date      = slot['date']
    slot_time = slot['slot_time']
    tid       = slot['ticket_id']

    rome = ZoneInfo('Europe/Rome')
    d, m, y = date.split('/')
    ts = int(datetime(int(y), int(m), int(d), 0, 0, 0, tzinfo=rome).timestamp() * 1000)
    entry_url = f'{VATICAN_BASE}/home/fromtag/{visitors}/{ts}/MV-Biglietti/1'

    log("Launching nodriver Chrome (Turnstile-invisible)...")

    # Kill any stale Chrome using this profile
    import subprocess
    subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe', '/T'], capture_output=True)
    await asyncio.sleep(1)
    # Remove stale lockfile
    for lf in ['lockfile', 'SingletonLock', 'SingletonCookie']:
        p = os.path.join(CHROME_PROFILE, lf)
        try:
            if os.path.exists(p): os.remove(p)
        except Exception:
            pass

    browser = await uc.start(
        user_data_dir=CHROME_PROFILE,
        browser_executable_path=CHROME_PATH,
        headless=False,
        lang='it-IT',
        no_sandbox=True,
    )
    tab = browser.main_tab

    try:
        # [1] Navigate to ticket page — wait for Angular to render tickets
        log(f"[1] {entry_url}")
        await tab.get(entry_url)
        # Wait until at least one bookTicket button appears (up to 15s)
        # If "Nessuna visita" appears, reload once
        for attempt in range(3):
            for _ in range(30):
                count = await tab.evaluate(
                    "document.querySelectorAll(\"[data-cy^='bookTicket_']\").length"
                )
                if count and int(count) > 0:
                    break
                # Check for "no visits" error state
                no_visits = await tab.evaluate("""
                    (() => {
                        const body = document.body?.innerText || '';
                        return body.includes('Nessuna visita') || body.includes('nessuna visita');
                    })()
                """)
                if no_visits:
                    log(f"  ⚠️ 'Nessuna visita' detected — reloading (attempt {attempt+1})")
                    await tab.sleep(1)
                    await tab.get(entry_url)
                    await tab.sleep(2)
                    break
                await tab.sleep(0.5)
            if count and int(count) > 0:
                break
            await tab.sleep(2)
        await tab.sleep(0.5)
        log(f"  Page loaded — {count} ticket button(s) found")

        # [2] Resolve fresh ticket_id via Search API
        log("[2] Resolving ticket_id via Search API...")
        r = requests.get(f'{VATICAN_BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=H, timeout=10)
        visits = r.json().get('visits', []) if r.status_code == 200 else []
        ticket = next((v for v in visits
                       if 'musei vaticani' in v.get('name', '').lower()
                       and 'ingresso' in v.get('name', '').lower()), None)
        if ticket:
            tid = str(ticket['id'])
        log(f"  ticket_id={tid}")

        # [3] Find PRENOTA button — poll until DOM is ready
        log("[3] Finding PRENOTA button...")
        dom_tid = None
        for _ in range(10):
            dom_tid = await tab.evaluate("""
                (() => {
                    // Match by card text
                    const cards = Array.from(document.querySelectorAll('[id^="ticket_"]'));
                    for (const card of cards) {
                        const text = card.innerText.toLowerCase();
                        if (text.includes('musei vaticani') && (text.includes('ingresso') || text.includes('biglietti'))) {
                            const btn = card.querySelector("[data-cy^='bookTicket_']");
                            if (btn) return btn.getAttribute('data-cy').replace('bookTicket_', '');
                        }
                    }
                    // Fallback: first visible PRENOTA button
                    const allBtns = Array.from(document.querySelectorAll("[data-cy^='bookTicket_']"));
                    for (const btn of allBtns) {
                        if (btn.innerText.trim() === 'PRENOTA') {
                            return btn.getAttribute('data-cy').replace('bookTicket_', '');
                        }
                    }
                    return null;
                })()
            """)
            if dom_tid:
                break
            await tab.sleep(0.5)

        if dom_tid:
            log(f"  DOM ticket_id={dom_tid} (API had {tid})")
            tid = dom_tid
        else:
            log(f"  DOM lookup failed — using API id={tid}, clicking directly")

        await tab.evaluate(f"document.querySelector(\"[data-cy='bookTicket_{tid}']\")?.click()")
        await tab.sleep(2)

        # [4] Set quantity — wait for quantity widget to appear
        log(f"[4] Setting quantity={visitors}...")
        # Wait for either a <select> or the custom dropdown
        qty_found = False
        for attempt in range(20):
            has_qty = await tab.evaluate("""
                (() => {
                    // Check for select dropdown
                    if (document.querySelector('select')) return 'select';
                    // Check for custom dropdown
                    if (document.querySelector("[data-cy='ticketQuantity']")) return 'custom';
                    // Check for any quantity-related elements
                    const qtyElements = Array.from(document.querySelectorAll('[class*="quantity"], [id*="quantity"], [data-cy*="quantity"]'));
                    if (qtyElements.length > 0) return 'generic';
                    return null;
                })()
            """)
            if has_qty:
                qty_found = True
                log(f"  Found quantity widget: {has_qty}")
                break
            await tab.sleep(0.5)

        if not qty_found:
            log(f"  ⚠️ Quantity widget not found after 10s - may already be set to {visitors}")
            # Take screenshot for debugging
            try:
                await tab.save_screenshot('debug_no_quantity.png')
                log("  Saved debug_no_quantity.png")
            except:
                pass
        else:
            qty_set = await tab.evaluate(f"""
                (() => {{
                    // Strategy 1: <select> dropdown
                    const selects = Array.from(document.querySelectorAll('select'));
                    for (const sel of selects) {{
                        // Check if this is a quantity selector
                        const parent = sel.closest('[class*="quantity"], [id*="quantity"]') || sel.parentElement;
                        if (parent || selects.length === 1) {{
                            sel.value = '{visitors}';
                            sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                            return 'select:' + sel.value;
                        }}
                    }}
                    
                    // Strategy 2: Custom dropdown with data-cy
                    const el = document.querySelector("[data-cy='ticketQuantity']");
                    if (el) {{ 
                        el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                        el.click(); 
                        return 'dropdown-opened'; 
                    }}
                    
                    // Strategy 3: Any clickable quantity element
                    const qtyBtn = document.querySelector('[class*="quantity"] button, [id*="quantity"] button');
                    if (qtyBtn) {{
                        qtyBtn.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                        qtyBtn.click();
                        return 'generic-opened';
                    }}
                    
                    return 'not-found';
                }})()
            """)
            
            if 'dropdown' in str(qty_set) or 'opened' in str(qty_set):
                await tab.sleep(0.8)
                # Click the quantity option
                clicked = await tab.evaluate(f"""
                    (() => {{
                        // Try data-cy selector
                        const items = Array.from(document.querySelectorAll("[data-cy='ticketQuantitySection']"));
                        for (const item of items) {{
                            const t = item.innerText.trim();
                            if (t === '{visitors}' || t.startsWith('{visitors} ')) {{
                                item.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                                item.click(); 
                                return 'clicked:' + t;
                            }}
                        }}
                        
                        // Fallback: any list item with the number
                        const allItems = Array.from(document.querySelectorAll('li, [role="option"], .option, [class*="item"]'));
                        for (const item of allItems) {{
                            const t = item.innerText.trim();
                            if (t === '{visitors}' || t.startsWith('{visitors} ')) {{
                                item.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                                item.click();
                                return 'fallback:' + t;
                            }}
                        }}
                        
                        // Last resort: click by index
                        if (items.length >= {visitors}) {{
                            items[{visitors}-1].click();
                            return 'index:' + ({visitors}-1);
                        }}
                        if (items.length > 0) {{
                            items[items.length-1].click();
                            return 'last';
                        }}
                        
                        return 'no-option-found';
                    }})()
                """)
                log(f"  Quantity option: {clicked}")
            
            log(f"  Quantity: {qty_set}")
        
        await tab.sleep(1.5)

        # [5] Select time slot — wait up to 10s for slots to render
        log(f"[5] Selecting time={slot_time}...")
        target_mins = int(slot_time.split(':')[0]) * 60 + int(slot_time.split(':')[1]) if slot_time else 0

        slots_found = False
        for attempt in range(30):
            count = await tab.evaluate("""
                (() => {
                    // Try multiple selectors for time slots
                    const byCy = document.querySelectorAll("[data-cy='time']");
                    if (byCy.length > 0) return byCy.length;
                    
                    const byClass = document.querySelectorAll('[class*="time"], [class*="slot"]');
                    if (byClass.length > 0) return byClass.length;
                    
                    const byButton = document.querySelectorAll('button[class*="calendar"], button[class*="time"]');
                    if (byButton.length > 0) return byButton.length;
                    
                    return 0;
                })()
            """)
            if count and int(count) > 0:
                slots_found = True
                break
            await tab.sleep(0.5)
        
        if not slots_found:
            log(f"  ⚠️ No time slots found after 15s")
            try:
                await tab.save_screenshot('debug_no_timeslots.png')
                log("  Saved debug_no_timeslots.png")
            except:
                pass
        else:
            log(f"  {count} time slot(s) found")

        # Switch to afternoon tab if needed (14:00+)
        if target_mins >= 14 * 60:
            switched = await tab.evaluate("""
                (() => {
                    // Try multiple strategies to find afternoon tab
                    // Strategy 1: Look for POMERIGGIO text
                    const tabs = Array.from(document.querySelectorAll('.tab, [role="tab"], button[class*="tab"]'))
                        .filter(el => el.offsetParent !== null);
                    const afternoon = tabs.find(t => /pomeriggio|afternoon/i.test(t.innerText));
                    if (afternoon) {
                        afternoon.scrollIntoView({behavior: 'smooth', block: 'center'});
                        afternoon.click();
                        return 'pomeriggio-clicked';
                    }
                    
                    // Strategy 2: Click second visible tab
                    if (tabs.length >= 2) {
                        tabs[1].scrollIntoView({behavior: 'smooth', block: 'center'});
                        tabs[1].click();
                        return 'second-tab-clicked';
                    }
                    
                    return 'no-tab-found';
                })()
            """)
            log(f"  Afternoon tab: {switched}")
            await tab.sleep(0.8)

        clicked_time = await tab.evaluate(f"""
            (() => {{
                // Strategy 1: Exact match on the time text inside [data-cy='time']
                const cells = Array.from(document.querySelectorAll("[data-cy='time']"));
                for (const cell of cells) {{
                    const txt = cell.innerText.trim();
                    if (txt === '{slot_time}' || txt.startsWith('{slot_time}')) {{
                        cell.scrollIntoView({{behavior: 'smooth', block: 'center'}}); 
                        cell.click(); 
                        return 'exact:' + txt;
                    }}
                    // Also check child div
                    const num = cell.querySelector('div.muvaCalendarNumber, div');
                    if (num && num.innerText.trim() === '{slot_time}') {{
                        cell.scrollIntoView({{behavior: 'smooth', block: 'center'}}); 
                        cell.click(); 
                        return 'child:' + num.innerText.trim();
                    }}
                }}
                
                // Strategy 2: Try generic time selectors
                const allTimeElements = Array.from(document.querySelectorAll(
                    'button[class*="time"], [class*="slot"], [class*="calendar-cell"]'
                ));
                for (const el of allTimeElements) {{
                    const txt = el.innerText.trim();
                    if (txt === '{slot_time}' || txt.startsWith('{slot_time}')) {{
                        el.scrollIntoView({{behavior: 'smooth', block: 'center'}}); 
                        el.click(); 
                        return 'generic:' + txt;
                    }}
                }}
                
                // Strategy 3: Closest time (fallback)
                const target = {target_mins};
                let best = null, bestTxt = null, bestDiff = 9999;
                for (const cell of cells) {{
                    const txt = cell.innerText.trim().split('\\n')[0];
                    const parts = txt.split(':');
                    if (parts.length !== 2) continue;
                    const mins = parseInt(parts[0]) * 60 + parseInt(parts[1]);
                    const diff = Math.abs(mins - target);
                    if (diff < bestDiff) {{ bestDiff = diff; best = cell; bestTxt = txt; }}
                }}
                if (best) {{ 
                    best.scrollIntoView({{behavior: 'smooth', block: 'center'}}); 
                    best.click(); 
                    return 'closest:' + bestTxt + '(diff=' + bestDiff + 'min)';
                }}
                
                // Strategy 4: First available slot (last resort)
                if (cells.length > 0) {{
                    cells[0].scrollIntoView({{behavior: 'smooth', block: 'center'}}); 
                    cells[0].click();
                    return 'first-available:' + cells[0].innerText.trim();
                }}
                
                return null;
            }})()
        """)
        
        if clicked_time:
            log(f"  Time clicked: {clicked_time}")
        else:
            log(f"  ⚠️ Could not click time slot - trying to proceed anyway")
            try:
                await tab.save_screenshot('debug_no_time_click.png')
                log("  Saved debug_no_time_click.png")
            except:
                pass
        
        await tab.sleep(2)

        # [6] Click PROCEDI — wait for button to be present first
        log("[6] Clicking PROCEDI...")
        for _ in range(10):
            has_btn = await tab.evaluate(
                "!!(document.querySelector(\"[data-cy='bookVisit']\"))"
            )
            if has_btn:
                break
            await tab.sleep(0.5)
        await tab.evaluate("""
            (() => {
                const btn = document.querySelector("[data-cy='bookVisit']") ||
                    Array.from(document.querySelectorAll('button')).find(b => /PROCEDI/i.test(b.textContent));
                if (btn) btn.click();
            })()
        """)
        await tab.sleep(5)

        # [7] Wait for checkout form — poll up to 30s
        log("[7] Waiting for form...")
        form_found = False
        for _ in range(60):
            el = await tab.evaluate("document.querySelector(\"[data-cy='managerSurname']\")?.tagName")
            if el:
                form_found = True
                break
            await tab.sleep(0.5)

        if not form_found:
            log("  Form not found after 30s — saving screenshot")
            try:
                await tab.save_screenshot('debug_form_missing.png')
                log("  Saved → debug_form_missing.png")
            except Exception:
                pass
            cur_url = await tab.evaluate("window.location.href")
            log(f"  Current URL: {cur_url}")
            # Don't crash — maybe form is there under a different selector
        else:
            log("  Form loaded ✅")

        # Helper: fill an Angular input field
        async def fill_field(selector, value):
            safe = str(value).replace('\\', '\\\\').replace('`', '\\`')
            await tab.evaluate(f"""
                (() => {{
                    const el = document.querySelector(`{selector}`);
                    if (!el) return;
                    el.focus();
                    el.value = '';
                    el.value = `{safe}`;
                    el.dispatchEvent(new Event('input',  {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    el.dispatchEvent(new Event('blur',   {{bubbles: true}}));
                }})()
            """)

        # Helper: fill phone via send_keys (more reliable for Angular validation)
        async def fill_phone(selector, value):
            el = await tab.query_selector(selector)
            if el:
                await el.click()
                await tab.sleep(0.2)
                # Clear existing value
                await tab.evaluate(f"""
                    (() => {{
                        const el = document.querySelector(`{selector}`);
                        if (el) {{ el.value = ''; el.dispatchEvent(new Event('input', {{bubbles:true}})); }}
                    }})()
                """)
                # Type digit by digit
                for ch in str(value):
                    await el.send_keys(ch)
                    await tab.sleep(0.03)
                await tab.evaluate(f"""
                    (() => {{
                        const el = document.querySelector(`{selector}`);
                        if (el) {{
                            el.dispatchEvent(new Event('change', {{bubbles:true}}));
                            el.dispatchEvent(new Event('blur',   {{bubbles:true}}));
                        }}
                    }})()
                """)

        log("[8] Filling form fields...")
        await fill_field("[data-cy='managerSurname']",     PROFILE['last_name'])
        await fill_field("[data-cy='managerName']",        PROFILE['first_name'])
        await fill_field("[data-cy='managerCity']",        PROFILE['city'])
        await fill_field("[data-cy='managerEmail']",       PROFILE['email'])
        await fill_field("[data-cy='managerConfirmEmail']",PROFILE['email'])
        # Phone: type digit by digit so Angular validation accepts it
        await fill_phone("[data-cy='managerPhone']",       PROFILE['phone'])
        await tab.sleep(0.3)

        # Gender
        await tab.evaluate("document.querySelector(\"[data-cy='managerSex']\")?.click()")
        await tab.sleep(0.3)
        await tab.evaluate("document.querySelector(\"[data-cy='managerSexSection']\")?.click()")
        await tab.sleep(0.3)

        # Country — search for "Ital" to match "Italia" in the dropdown
        await tab.evaluate("document.querySelector(\"[data-cy='managerCountry']\")?.click()")
        await tab.sleep(0.3)
        await tab.evaluate(f"""
            (() => {{
                const s = document.querySelector('#searchInput_country');
                if (s) {{
                    s.value = 'Ital';
                    s.dispatchEvent(new Event('input', {{bubbles: true}}));
                }}
            }})()
        """)
        await tab.sleep(0.4)
        # Click the first result (Italia)
        await tab.evaluate("""
            (() => {
                const items = Array.from(document.querySelectorAll("[data-cy='managerCountrySection']"));
                const italia = items.find(el => /^ital/i.test(el.innerText.trim()));
                if (italia) italia.click();
                else if (items[0]) items[0].click();
            })()
        """)
        await tab.sleep(0.3)

        # Birth date — inject directly into Angular form control (readonly input, calendar picker)
        log("[8b] Setting birth date...")
        birth_year  = PROFILE['birth_year']   # '1990'
        birth_month = PROFILE['birth_month']  # 'GEN'
        birth_day   = PROFILE['birth_day'].zfill(2)  # '15'
        birth_iso   = PROFILE['birth_date_iso']  # '1990-01-14T23:00:00.000Z'

        # Map Italian month abbreviation → month number
        month_map = {'GEN':'01','FEB':'02','MAR':'03','APR':'04','MAG':'05','GIU':'06',
                     'LUG':'07','AGO':'08','SET':'09','OTT':'10','NOV':'11','DIC':'12'}
        birth_month_num = month_map.get(birth_month.upper(), '01')
        # Vatican date format: dd/mm/yyyy
        birth_display = f"{birth_day}/{birth_month_num}/{birth_year}"

        # Strategy 1: set via Angular NgControl on the datepicker input
        set_ok = await tab.evaluate(f"""
            (() => {{
                const inp = document.querySelector("[data-cy='dateCalendar']");
                if (!inp) return false;
                // Get Angular component reference
                const keys = Object.keys(inp).filter(k => k.startsWith('__ngContext__') || k.startsWith('_ngModel') || k.startsWith('ng-'));
                // Try setting via nativeElement value + MatDatepicker
                const nativeEl = inp;
                // Unlock readonly temporarily
                nativeEl.removeAttribute('readonly');
                nativeEl.focus();
                nativeEl.value = '{birth_display}';
                nativeEl.dispatchEvent(new Event('input', {{bubbles: true}}));
                nativeEl.dispatchEvent(new Event('change', {{bubbles: true}}));
                nativeEl.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', bubbles: true}}));
                nativeEl.dispatchEvent(new KeyboardEvent('keyup',  {{key: 'Enter', bubbles: true}}));
                nativeEl.setAttribute('readonly', 'true');
                return nativeEl.value;
            }})()
        """)
        await tab.sleep(0.5)

        # Strategy 2: use the calendar picker UI if strategy 1 didn't work
        if not set_ok or set_ok == '':
            # Open calendar
            await tab.evaluate("""
                document.querySelector("mat-datepicker-toggle button[aria-label='Open calendar']")?.click()
            """)
            await tab.sleep(1)

            # Go to multi-year view
            for _ in range(2):
                in_multi = await tab.evaluate("""
                    document.querySelectorAll('.mat-calendar-body-cell').length > 12
                """)
                if in_multi:
                    break
                await tab.evaluate("document.querySelector('button.mat-calendar-period-button')?.click()")
                await tab.sleep(0.5)

            # Scroll back to find the year
            for _ in range(30):
                found = await tab.evaluate(f"""
                    (() => {{
                        const cells = Array.from(document.querySelectorAll('.mat-calendar-body-cell'));
                        const yr = cells.find(c => c.textContent.trim() === '{birth_year}');
                        if (yr) {{ yr.click(); return true; }}
                        document.querySelector('.mat-calendar-previous-button')?.click();
                        return false;
                    }})()
                """)
                await tab.sleep(0.3)
                if found:
                    break
            await tab.sleep(0.5)

            # Select month
            await tab.evaluate(f"""
                (() => {{
                    const cells = Array.from(document.querySelectorAll('.mat-calendar-body-cell'));
                    const mo = cells.find(c => c.textContent.trim().toUpperCase() === '{birth_month}');
                    if (mo) mo.click();
                }})()
            """)
            await tab.sleep(0.5)

            # Select day
            birth_day_stripped = birth_day.lstrip('0') or '1'
            await tab.evaluate(f"""
                (() => {{
                    const cells = Array.from(document.querySelectorAll('span.mat-calendar-body-cell-content'));
                    const day = cells.find(c => c.textContent.trim() === '{birth_day_stripped}');
                    if (day) day.click();
                }})()
            """)
            await tab.sleep(0.4)

        # Verify
        set_date = await tab.evaluate("""
            document.querySelector("[data-cy='dateCalendar']")?.value || 'not found'
        """)
        log(f"  Birth date: {birth_display} → field shows: {set_date}")

        # Language
        await tab.evaluate("document.querySelector(\"[data-cy='managerLanguage']\")?.click()")
        await tab.sleep(0.3)
        await tab.evaluate("document.querySelector(\"[data-cy='managerLanguageSection']\")?.click()")
        await tab.sleep(0.3)

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
            await fill_field(f"#participantSurname_{i}", PROFILE['last_name'])
            await fill_field(f"#participantName_{i}",    PROFILE['first_name'])

        # GDPR checkboxes — find by position
        all_cbs = await tab.evaluate("""
            (() => {
                const cbs = Array.from(document.querySelectorAll('input[type="checkbox"]'));
                return cbs.map((cb, i) => ({
                    index: i, id: cb.id, checked: cb.checked,
                    label: cb.closest('mat-checkbox')?.innerText?.trim()?.slice(0, 60)
                }));
            })()
        """)
        log(f"  All checkboxes: {all_cbs}")

        # Click first checkbox (terms) — opens modal, must close it
        cb0 = await tab.evaluate("document.querySelectorAll('input[type=\"checkbox\"]')[0]?.checked")
        if cb0 is False:
            await tab.evaluate("document.querySelectorAll('input[type=\"checkbox\"]')[0]?.click()")
            await tab.sleep(1.5)
            await tab.evaluate("""
                (() => {
                    const close = document.querySelector("[data-cy='purchase-rules-close-btn']")
                               || Array.from(document.querySelectorAll('button')).find(b => /chiudi|close/i.test(b.textContent));
                    if (close) close.click();
                })()
            """)
            await tab.sleep(1)

        # Click second checkbox (privacy consent)
        cb1 = await tab.evaluate("document.querySelectorAll('input[type=\"checkbox\"]')[1]?.checked")
        if cb1 is False:
            await tab.evaluate("document.querySelectorAll('input[type=\"checkbox\"]')[1]?.click()")
        await tab.sleep(0.5)

        # Verify both are checked
        cb_status = await tab.evaluate("""
            (() => {
                const cbs = Array.from(document.querySelectorAll('input[type="checkbox"]'));
                return cbs.map((cb, i) => [i, cb.id, cb.checked]);
            })()
        """)
        log(f"  Checkboxes after: {cb_status}")

        cb_status = await tab.evaluate("""
            (() => {
                const cbs = Array.from(document.querySelectorAll('input[type="checkbox"]'));
                return cbs.map((cb, i) => [i, cb.id, cb.checked]);
            })()
        """)
        log(f"  Checkboxes after: {cb_status}")
        await tab.sleep(1)

        log(f"\n{'='*60}")
        log("✅ FORM FILLED — waiting for Turnstile to solve...")
        log(f"{'='*60}\n")

        # Keep the recap alive while waiting for Turnstile
        # Vatican expires recap sessions if no activity
        await tab.evaluate(f"""
            (() => {{
                // Ping recap every 60s to keep session alive
                window._keepalive = setInterval(() => {{
                    fetch('/api/visit/recap', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}},
                        credentials: 'include',
                        body: JSON.stringify({{
                            visitId: '{slot["slot_id"]}',
                            visitTypeId: parseInt('{tid}'),
                            visitorNum: {visitors},
                            lang: 'it',
                            tickets: [
                                {{id: 60, name: 'Biglietto Intero', price: 20, quantity: '{visitors}'}},
                                {{id: 61, name: 'Biglietto Ridotto', price: 10, quantity: 0}}
                            ],
                            additionalCosts: {{'service-0': {{id: 58, name: 'Diritti di Prevendita', price: 5, quantity: {visitors}}}}},
                            services: [{{id: 58, name: 'Diritti di Prevendita', price: 5, quantity: {visitors}}}]
                        }})
                    }}).then(r => console.log('keepalive', r.status)).catch(e => console.log('keepalive err', e));
                }}, 60000);
            }})()
        """)

        # Wait for Turnstile to be solved (token appears in the page)
        log("  Checking Turnstile status...")
        turnstile_ready = False
        for _ in range(30):  # up to 15s
            token = await tab.evaluate("""
                (() => {
                    // Check if Turnstile has generated a token
                    const inp = document.querySelector('[name="cf-turnstile-response"], input[name*="turnstile"]');
                    if (inp && inp.value && inp.value.length > 10) return inp.value.slice(0, 20) + '...';
                    // Also check window callback was called
                    if (window._turnstile_token && window._turnstile_token.length > 10) return 'window_token';
                    return null;
                })()
            """)
            if token:
                log(f"  ✅ Turnstile solved: {token}")
                turnstile_ready = True
                break
            await tab.sleep(0.5)
        if not turnstile_ready:
            log("  ⚠️  Turnstile token not detected — proceeding anyway (nodriver handles it)")

        reservation_error = {'msg': None}  # will be checked by polling page URL/content

        # Intercept XHR to capture reservation request body + response
        await tab.evaluate("""
            (() => {
                const origOpen = XMLHttpRequest.prototype.open;
                const origSend = XMLHttpRequest.prototype.send;
                XMLHttpRequest.prototype.open = function(method, url, ...args) {
                    this._url = url;
                    return origOpen.apply(this, [method, url, ...args]);
                };
                XMLHttpRequest.prototype.send = function(body) {
                    if (this._url && this._url.includes('/api/visit/reservation')) {
                        window._reservation_request = body ? body.slice(0, 1000) : null;
                    }
                    this.addEventListener('load', function() {
                        if (this._url && this._url.includes('/api/visit/reservation')) {
                            window._reservation_response = this.responseText.slice(0, 500);
                        }
                        if (this._url && this._url.includes('/api/visit/recap')) {
                            try {
                                const d = JSON.parse(this.responseText);
                                window._recap_id = d.recapId || d.id || null;
                                window._recap_visit_type = d.visitTypeId || null;
                            } catch(e) {}
                        }
                    });
                    return origSend.apply(this, [body]);
                };
            })()
        """)

        # [9] Click BUY — use data-cy='bookVisit' on checkout, or the submit button
        log("[9] Clicking BUY...")

        # Check form validity first — log any invalid fields
        invalid_fields = await tab.evaluate("""
            (() => {
                const invalid = Array.from(document.querySelectorAll('.ng-invalid[data-cy], .ng-invalid input'))
                    .map(el => el.getAttribute('data-cy') || el.id || el.name || el.placeholder)
                    .filter(Boolean);
                return invalid.slice(0, 10);
            })()
        """)
        if invalid_fields:
            log(f"  ⚠️  Invalid fields: {invalid_fields}")
        else:
            log("  ✅ All fields valid")
        # Take screenshot before clicking to debug if it fails
        try:
            await tab.save_screenshot('debug_before_buy.png')
        except Exception:
            pass

        clicked_buy = await tab.evaluate("""
            (() => {
                // Vatican checkout submit button
                const byDataCy = document.querySelector("[data-cy='buyVisit'], [data-cy='confirmVisit'], [data-cy='submitVisit']");
                if (byDataCy) { byDataCy.click(); return byDataCy.getAttribute('data-cy'); }
                // Fallback: submit button not disabled
                const submits = Array.from(document.querySelectorAll("button[type='submit']"))
                    .filter(b => !b.disabled);
                if (submits.length > 0) { submits[submits.length-1].click(); return 'submit-btn'; }
                // Last resort: any button with buy/confirm text
                const byText = Array.from(document.querySelectorAll('button'))
                    .find(b => /acquista|conferma|procedi|avanti/i.test(b.textContent) && !b.disabled);
                if (byText) { byText.click(); return byText.textContent.trim(); }
                return null;
            })()
        """)
        log(f"  BUY clicked: {clicked_buy}")

        # [10] Wait for epay redirect (up to 60s)
        log("[10] Waiting for epay redirect (up to 60s)...")
        epay_url = ''
        for i in range(120):
            await tab.sleep(0.5)
            try:
                cur = await tab.evaluate("window.location.href")
                if cur and 'epay' in cur:
                    epay_url = cur
                    log(f"  ✅ Redirected to epay: {epay_url[:80]}")
                    break
                # Check for Vatican error page
                if cur and ('error' in cur.lower() or 'errore' in cur.lower()):
                    log(f"  ❌ Vatican error page: {cur}")
                    try: await tab.save_screenshot('debug_vatican_error.png')
                    except: pass
                    break
                # Check for error message on page after 5s
                if i == 10:
                    err = await tab.evaluate("""
                        (() => {
                            if (window._reservation_response) return 'API: ' + window._reservation_response;
                            for (const sel of ['[class*="error"]','[role="alert"]','mat-snack-bar-container']) {
                                const e = document.querySelector(sel);
                                if (e && e.innerText.trim().length > 3) return e.innerText.trim().slice(0, 200);
                            }
                            return null;
                        })()
                    """)
                    if err: log(f"  ⚠️  Page message: {err}")
                    # Also log what was sent
                    req_body = await tab.evaluate("window._reservation_request || null")
                    recap_id = await tab.evaluate("window._recap_id || null")
                    if req_body: log(f"  📤 Reservation body: {req_body}")  # full body
                    if recap_id: log(f"  🔑 recapId from recap API: {recap_id}")
                    # Parse key fields
                    try:
                        import json as _j
                        if req_body:
                            rb = _j.loads(req_body)
                            log(f"  🔍 visitTypeId={rb.get('visitTypeId')} visitId={rb.get('visitId')} recapId={rb.get('recapId')} visitorNum={rb.get('visitorNum')}")
                            log(f"  👤 rep={rb.get('representativeUser')}")
                            log(f"  📋 gdpr={rb.get('gdpr')}")
                    except Exception:
                        pass
                # Check reservation API error
                if reservation_error['msg']:
                    log(f"  ❌ Reservation failed: {reservation_error['msg']}")
                    try: await tab.save_screenshot('debug_reservation_error.png')
                    except: pass
                    break
            except Exception:
                pass

        if not epay_url:
            log("  ❌ No epay redirect — check browser window")
            return {'epay_url': '', 'slot': slot}

        # [11] Fill epay payment form
        log("[11] Filling epay payment form...")
        await tab.sleep(3)  # let Datatrans SecureFields iframes load

        async def epay_fill(field_id, value):
            safe = str(value).replace('`', '\\`')
            await tab.evaluate(f"""
                (() => {{
                    const el = document.querySelector('#{field_id}');
                    if (!el) return;
                    el.focus();
                    el.value = `{safe}`;
                    el.dispatchEvent(new Event('input',  {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    el.blur();
                }})()
            """)

        # Fill name fields and email
        card_first, *card_rest = CARD['holder'].split(' ', 1)
        card_last = card_rest[0] if card_rest else card_first
        await epay_fill('name',        card_first)
        await epay_fill('surname',     card_last)
        await epay_fill('email',       PROFILE['email'])
        await epay_fill('repeatEmail', PROFILE['email'])
        await tab.sleep(0.3)
        log(f"  Name/email filled")

        # Fill card number via Datatrans SecureFields iframe (send_keys on Element)
        log("  Filling card number (Datatrans iframe)...")
        try:
            iframe_el = await tab.query_selector('iframe[name*="cardNumber"], iframe[id*="cardNumber"]')
            if iframe_el:
                await iframe_el.click()
                await tab.sleep(0.5)
                # Type digit by digit with small delay — Datatrans drops chars if too fast
                for ch in CARD['number']:
                    await iframe_el.send_keys(ch)
                    await tab.sleep(0.05)
                await tab.sleep(0.3)
                log(f"  Card number typed: {CARD['number'][:4]}...{CARD['number'][-4:]}")
            else:
                log("  Card number iframe not found")
        except Exception as e:
            log(f"  Card number failed: {e}")

        # Fill CVV iframe
        log("  Filling CVV (Datatrans iframe)...")
        try:
            cvv_el = await tab.query_selector('iframe[name*="cvv"], iframe[id*="cvv"]')
            if cvv_el:
                await cvv_el.click()
                await tab.sleep(0.5)
                for ch in CARD['cvv']:
                    await cvv_el.send_keys(ch)
                    await tab.sleep(0.05)
                await tab.sleep(0.3)
                # Press Tab to move focus out of the iframe back to the main page
                await cvv_el.send_keys('\t')
                await tab.sleep(0.3)
                log("  CVV typed")
            else:
                log("  CVV iframe not found")
        except Exception as e:
            log(f"  CVV failed: {e}")

        # Expiry month — click the month dropdown, pick the right item
        exp_month, exp_year = CARD['expiry'].split('/')
        exp_month = exp_month.strip().zfill(2)   # "12"
        exp_year  = '20' + exp_year.strip() if len(exp_year.strip()) == 2 else exp_year.strip()  # "2028"

        log(f"  Setting expiry {exp_month}/{exp_year}...")
        # Click month dropdown
        await tab.evaluate("""
            (() => {
                const dropdowns = document.querySelectorAll('app-dropdown');
                if (dropdowns[0]) dropdowns[0].querySelector('.select__box--selectedValue').click();
            })()
        """)
        await tab.sleep(0.4)
        await tab.evaluate(f"""
            (() => {{
                const items = Array.from(document.querySelectorAll('.select__list--item span'));
                const mo = items.find(el => el.textContent.trim() === '{exp_month}');
                if (mo) mo.click();
            }})()
        """)
        await tab.sleep(0.3)

        # Click year dropdown
        await tab.evaluate("""
            (() => {
                const dropdowns = document.querySelectorAll('app-dropdown');
                if (dropdowns[1]) dropdowns[1].querySelector('.select__box--selectedValue').click();
            })()
        """)
        await tab.sleep(0.4)
        await tab.evaluate(f"""
            (() => {{
                const items = Array.from(document.querySelectorAll('.select__list--item span'));
                const yr = items.find(el => el.textContent.trim() === '{exp_year}');
                if (yr) yr.click();
            }})()
        """)
        await tab.sleep(0.3)
        log(f"  Expiry set: {exp_month}/{exp_year}")

        # Tick the agreement checkbox
        await tab.evaluate("""
            (() => {
                const cb = document.querySelector('#mat-checkbox-1-input');
                if (cb && !cb.checked) cb.click();
            })()
        """)
        await tab.sleep(0.3)
        log("  Agreement checkbox ticked")

        card_filled = 1
        log(f"  Card: {CARD['number'][:4]}...{CARD['number'][-4:]} | {CARD['expiry']} | {CARD['holder']}")

        # [12] Click PAY (only if AUTO_PAY is True)
        if AUTO_PAY:
            log("[12] Clicking PAY (Paga) button on epay...")
            await tab.sleep(1)  # let form settle after filling
            # First click somewhere neutral to blur the CVV iframe focus
            await tab.evaluate("""
                (() => {
                    document.body.click();
                    document.activeElement?.blur();
                })()
            """)
            await tab.sleep(0.5)
            clicked_pay = await tab.evaluate("""
                (() => {
                    // Exact selector from the epay page HTML
                    const byId = document.querySelector("button#form-submit[type='submit'].btn-submit");
                    if (byId && !byId.disabled) { byId.scrollIntoView(); byId.focus(); byId.click(); return 'form-submit#id'; }
                    // Fallback: any submit button with Paga text
                    const byText = Array.from(document.querySelectorAll("button[type='submit']"))
                        .find(b => b.textContent.includes('Paga') && !b.disabled);
                    if (byText) { byText.scrollIntoView(); byText.focus(); byText.click(); return 'paga-text'; }
                    // Last resort: last visible non-disabled submit
                    const all = Array.from(document.querySelectorAll("button[type='submit']"))
                        .filter(b => !b.disabled && b.offsetParent !== null);
                    if (all.length) { all[all.length-1].scrollIntoView(); all[all.length-1].click(); return 'last-submit'; }
                    return null;
                })()
            """)
            log(f"  PAY clicked: {clicked_pay}")
            # Wait for 3DS/confirmation — bank notification may take up to 60s
            log("  Waiting for 3DS/confirmation (up to 60s)...")
            confirm_url = ''
            for _ in range(120):
                await tab.sleep(0.5)
                try:
                    cur = await tab.evaluate("window.location.href")
                    if not cur or cur == epay_url:
                        continue
                    # Failed payment
                    if 'feedback/fail' in cur or 'error' in cur:
                        log(f"  ❌ Payment failed: {cur}")
                        log("  → Card was declined. Use a real card in CARD config.")
                        break
                    # Success
                    if any(x in cur for x in ('feedback/success', 'confirm', 'success',
                                               'thank', 'grazie', 'receipt', 'ok')):
                        confirm_url = cur
                        log(f"  ✅ Payment confirmed: {confirm_url}")
                        break
                    # 3DS challenge — URL changed but not to success/fail yet
                    if cur != epay_url:
                        log(f"  📱 Redirected to: {cur[:80]}")
                        log("  Waiting for 3DS approval on your phone...")
                        # Wait up to 2 min for 3DS
                        for _ in range(240):
                            await tab.sleep(0.5)
                            cur2 = await tab.evaluate("window.location.href")
                            if 'feedback/success' in (cur2 or '') or 'confirm' in (cur2 or ''):
                                confirm_url = cur2
                                log(f"  ✅ 3DS approved: {confirm_url}")
                                break
                            if 'feedback/fail' in (cur2 or '') or 'error' in (cur2 or ''):
                                log(f"  ❌ 3DS failed/declined: {cur2}")
                                break
                        break
                except Exception:
                    pass
            if not confirm_url:
                log("  ⏳ No confirmation — browser stays open 60s")
        else:
            log("[12] AUTO_PAY=False — card filled, browser stays open 60s for manual review")
            log(f"  ⚠️  Set AUTO_PAY=True in config to automate the final click")
            await tab.sleep(60)  # keep open so user can review / click manually

        # Grab JSESSIONID
        jsessionid = ''
        try:
            cookies = await tab.browser.cookies()
            jsessionid = next((c.get('value', '') for c in cookies
                               if c.get('name') == 'JSESSIONID'
                               and 'museivaticani' in c.get('domain', '')), '')
        except Exception:
            pass

        return {
            'epay_url': epay_url,
            'slot': slot,
            'jsessionid': jsessionid,
            'card_filled': card_filled,
        }

    except KeyboardInterrupt:
        log("⚠️ Interrupted by user (Ctrl+C)")
        try:
            await tab.save_screenshot('debug_interrupted.png')
            log("Saved debug_interrupted.png")
        except:
            pass
        return None
    except Exception as e:
        log(f"Browser error: {e}")
        import traceback; traceback.print_exc()
        try:
            await tab.save_screenshot('debug_error.png')
            log("Saved debug_error.png")
        except:
            pass
        return None
    finally:
        try:
            log("Cleaning up browser...")
            await tab.sleep(2)
            browser.stop()
        except Exception as e:
            log(f"Cleanup error (ignored): {e}")


# ── MAIN ─────────────────────────────────────────────────────────────────────

async def main(target_date, visitors):
    print("\n" + "="*60)
    print("  Vatican Full Reservation Test (nodriver)")
    print("="*60 + "\n")

    log("STEP 1: Finding available slot...")
    slot = find_slot(target_date, visitors)
    if not slot:
        log("No slot found.")
        return

    log(f"\nSTEP 2: Browser flow for {slot['date']} {slot['slot_time']} ({visitors}v)...")
    result = await run_in_browser(slot)

    print("\n" + "="*60)
    if result and result.get('epay_url'):
        print("  ✅ SUCCESS")
        print(f"  Date:  {slot['date']} {slot['slot_time']}")
        print(f"  Card:  {CARD['number'][:4]}...{CARD['number'][-4:]} filled={'yes' if result.get('card_filled') else 'check browser'}")
        print(f"\n  💳 PAYMENT LINK:\n  {result['epay_url']}")
        if not AUTO_PAY:
            print(f"\n  ℹ️  Set AUTO_PAY=True to automate the final PAY click")
    else:
        print("  ❌ FAILED — see logs above")
        if result:
            print("  (Browser may still be open — check the window)")
    print("="*60 + "\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--date',     default=None, help='DD/MM/YYYY')
    parser.add_argument('--visitors', type=int, default=2)
    parser.add_argument('--autopay',  action='store_true', help='Auto-click PAY (use real card!)')
    args = parser.parse_args()
    if args.autopay:
        AUTO_PAY = True
    asyncio.run(main(args.date, args.visitors))
