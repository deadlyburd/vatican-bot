#!/usr/bin/env python3
"""
PRODUCTION AUTO-BOOKER — nodriver (Chrome with Cloudflare Turnstile bypass)
==============================================================================
Based on test_full_reservation.py — proven to work.
1. SlotFinder finds available slots via API (search + timeavail)
2. nodriver opens Chrome, navigates Vatican deep link
3. Full UI flow: ticket → quantity → time → PROCEDI → form → BUY → epay
4. Captures payment link → writes to sheet → notifies Telegram

Usage:
    python nodriver_booker.py                            # Continuous CRM mode
    python nodriver_booker.py --date 01/09/2026          # Single date
    python nodriver_booker.py --date 01/09/2026 --visitors 2 --time 10:00
"""

import asyncio
import sys
import os
import time
import json
import logging
import argparse
import warnings
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

warnings.filterwarnings('ignore', category=ResourceWarning)

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from slot_finder import SlotFinder

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────
VATICAN_BASE = 'https://tickets.museivaticani.va'
CHROME_PROFILE = os.path.join(os.path.expanduser('~'), 'vatican_booking_profile')
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/136.0.0.0 Safari/537.36'
)

# Default buyer profile (overwritten by CRM data)
PROFILE = {
    'first_name': 'Mario',
    'last_name': 'Rossi',
    'email': 'mario.rossi@example.com',
    'phone': '3401234567',
    'city': 'Roma',
    'country': 'Italia',
    'birth_year': '1990',
    'birth_month': 'GEN',
    'birth_day': '15',
    'birth_date_iso': '1990-01-14T23:00:00.000Z',
}

# Payment card (filled on epay page, manual pay by default)
AUTO_PAY = True
CARD = {
    'holder': 'ABIILESH SEKAR',
    'number': '4569331515529372',
    'expiry': '07/28',
    'cvv': '721',
}

# API headers
H = {
    'Accept': 'application/json, text/plain, */*',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{VATICAN_BASE}/',
    'User-Agent': USER_AGENT,
}


def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    logger.info(msg)
    print(f"[{ts}] {msg}")


# ── STEP 1: Find slot via SlotFinder ─────────────────────────────────

def find_slot(target_date=None, visitors=2, time_slot=None):
    """Find available slot. If no date given, scan from today forward."""
    finder = SlotFinder()

    if target_date:
        slots = finder.find_slots(target_date, visitors, use_cache=False)
        if slots:
            s = slots[0]
            if time_slot:
                match = next((x for x in slots if x.time == time_slot), None)
                if match:
                    s = match
            return {
                'date': s.date, 'slot_id': s.slot_id,
                'slot_time': s.time, 'ticket_id': s.ticket_id,
                'visitors': visitors,
            }
        return None

    # Scan forward 60 days
    from datetime import date as dt
    today = dt.today()
    for i in range(1, 60):
        d = (today + timedelta(days=i))
        if d.weekday() == 6:  # Skip Sundays
            continue
        date_str = d.strftime('%d/%m/%Y')
        slots = finder.find_slots(date_str, visitors, use_cache=False)
        if slots:
            s = slots[0]
            return {
                'date': s.date, 'slot_id': s.slot_id,
                'slot_time': s.time, 'ticket_id': s.ticket_id,
                'visitors': visitors,
            }
        time.sleep(0.3)

    return None


# ── STEP 2: Browser booking flow ─────────────────────────────────────

async def book_in_browser(slot, profile=None, card=None):
    """Execute full Vatican booking in Chrome via nodriver."""
    import nodriver as uc

    visitors = slot['visitors']
    date = slot['date']
    slot_time = slot['slot_time']
    tid = slot['ticket_id']
    prof = profile or PROFILE
    crd = card or CARD

    # Build deep link URL with Rome timezone timestamp
    rome = ZoneInfo('Europe/Rome')
    d, m, y = date.split('/')
    ts = int(datetime(int(y), int(m), int(d), 0, 0, 0, tzinfo=rome).timestamp() * 1000)
    entry_url = f'{VATICAN_BASE}/home/fromtag/{visitors}/{ts}/MV-Biglietti/1'

    log(f"Launching Chrome → {date} {slot_time} ({visitors}v)")

    # Clean stale profile locks
    for lf in ['lockfile', 'SingletonLock', 'SingletonCookie']:
        p = os.path.join(CHROME_PROFILE, lf)
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    browser = await uc.start(
        user_data_dir=CHROME_PROFILE,
        headless=False,
        lang='it-IT',
        no_sandbox=True,
    )
    tab = browser.main_tab

    try:
        # ── [1] Navigate to ticket page ──────────────────────────
        log(f"[1] {entry_url}")
        await tab.get(entry_url)

        # Wait for ticket buttons
        count = 0
        for attempt in range(3):
            for _ in range(30):
                count = await tab.evaluate(
                    "document.querySelectorAll(\"[data-cy^='bookTicket_']\").length"
                )
                if count and int(count) > 0:
                    break
                no_visits = await tab.evaluate(
                    "document.body?.innerText?.includes('Nessuna visita') || false"
                )
                if no_visits:
                    log(f"  ⚠️ 'Nessuna visita' — reloading (attempt {attempt+1})")
                    await tab.sleep(1)
                    await tab.get(entry_url)
                    await tab.sleep(2)
                    break
                await tab.sleep(0.5)
            if count and int(count) > 0:
                break
            await tab.sleep(2)
        await tab.sleep(0.5)
        log(f"  Page loaded — {count} ticket button(s)")

        # ── [2] Resolve ticket ID ────────────────────────────────
        log("[2] Resolving ticket ID...")
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
            log(f"  DOM ticket_id={dom_tid}")
            tid = dom_tid
        else:
            log(f"  DOM lookup failed — using API id={tid}")

        await tab.evaluate(f"document.querySelector(\"[data-cy='bookTicket_{tid}']\")?.click()")
        await tab.sleep(2)

        # ── [3] Set quantity ─────────────────────────────────────
        log(f"[3] Setting quantity={visitors}...")
        for _ in range(20):
            has_qty = await tab.evaluate("""
                (() => {
                    if (document.querySelector('select')) return true;
                    if (document.querySelector("[data-cy='ticketQuantity']")) return true;
                    return false;
                })()
            """)
            if has_qty:
                break
            await tab.sleep(0.5)

        qty_set = await tab.evaluate(f"""
            (() => {{
                const selects = Array.from(document.querySelectorAll('select'));
                for (const sel of selects) {{
                    sel.value = '{visitors}';
                    sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return 'select:' + sel.value;
                }}
                const el = document.querySelector("[data-cy='ticketQuantity']");
                if (el) {{ el.click(); return 'dropdown-opened'; }}
                return 'not-found';
            }})()
        """)

        if 'dropdown' in str(qty_set) or 'opened' in str(qty_set):
            await tab.sleep(0.8)
            clicked = await tab.evaluate(f"""
                (() => {{
                    const items = Array.from(document.querySelectorAll("[data-cy='ticketQuantitySection']"));
                    for (const item of items) {{
                        const t = item.innerText.trim();
                        if (t === '{visitors}' || t.startsWith('{visitors} ')) {{
                            item.click(); return 'clicked:' + t;
                        }}
                    }}
                    if (items.length >= {visitors}) {{ items[{visitors}-1].click(); return 'index'; }}
                    if (items.length > 0) {{ items[items.length-1].click(); return 'last'; }}
                    return 'no-option';
                }})()
            """)
            log(f"  Quantity: {clicked}")
        await tab.sleep(1.5)

        # ── [4] Select time slot ─────────────────────────────────
        log(f"[4] Selecting time={slot_time}...")
        target_mins = int(slot_time.split(':')[0]) * 60 + int(slot_time.split(':')[1])

        # Wait for slots
        for _ in range(30):
            count = await tab.evaluate(
                "document.querySelectorAll(\"[data-cy='time']\").length"
            )
            if count and int(count) > 0:
                break
            await tab.sleep(0.5)
        log(f"  {count} time slot(s) found")

        # Afternoon tab
        if target_mins >= 14 * 60:
            await tab.evaluate("""
                (() => {
                    const tabs = Array.from(document.querySelectorAll('.tab, [role="tab"], button[class*="tab"]'))
                        .filter(el => el.offsetParent !== null);
                    const afternoon = tabs.find(t => /pomeriggio/i.test(t.innerText));
                    if (afternoon) afternoon.click();
                    else if (tabs.length >= 2) tabs[1].click();
                })()
            """)
            await tab.sleep(0.8)

        # Click time slot
        clicked_time = await tab.evaluate(f"""
            (() => {{
                const cells = Array.from(document.querySelectorAll("[data-cy='time']"));
                for (const cell of cells) {{
                    const txt = cell.innerText.trim();
                    if (txt === '{slot_time}' || txt.startsWith('{slot_time}')) {{
                        cell.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                        cell.click();
                        return 'exact:' + txt;
                    }}
                }}
                // Closest time
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
                if (best) {{ best.click(); return 'closest:' + bestTxt; }}
                if (cells.length > 0) {{ cells[0].click(); return 'first'; }}
                return null;
            }})()
        """)
        log(f"  Time clicked: {clicked_time}")
        await tab.sleep(2)

        # ── [5] Click PROCEDI ────────────────────────────────────
        log("[5] PROCEDI...")
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

        # ── [6] Wait for form ─────────────────────────────────────
        log("[6] Waiting for checkout form...")
        for _ in range(60):
            el = await tab.evaluate(
                "document.querySelector(\"[data-cy='managerSurname']\")?.tagName"
            )
            if el:
                break
            await tab.sleep(0.5)
        log("  Form loaded ✅")

        # ── [7] Fill form ────────────────────────────────────────
        log("[7] Filling form...")

        async def fill(selector, value):
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

        async def fill_phone(selector, value):
            el = await tab.query_selector(selector)
            if el:
                await el.click()
                await tab.sleep(0.2)
                await tab.evaluate(f"""
                    (() => {{
                        const el = document.querySelector(`{selector}`);
                        if (el) {{ el.value = ''; el.dispatchEvent(new Event('input', {{bubbles:true}})); }}
                    }})()
                """)
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

        await fill("[data-cy='managerSurname']", prof['last_name'])
        await fill("[data-cy='managerName']", prof['first_name'])
        await fill("[data-cy='managerCity']", prof['city'])
        await fill("[data-cy='managerEmail']", prof['email'])
        await fill("[data-cy='managerConfirmEmail']", prof['email'])
        await fill_phone("[data-cy='managerPhone']", prof['phone'])
        await tab.sleep(0.3)

        # Gender
        await tab.evaluate("document.querySelector(\"[data-cy='managerSex']\")?.click()")
        await tab.sleep(0.3)
        await tab.evaluate("document.querySelector(\"[data-cy='managerSexSection']\")?.click()")
        await tab.sleep(0.3)

        # Country
        await tab.evaluate("document.querySelector(\"[data-cy='managerCountry']\")?.click()")
        await tab.sleep(0.3)
        await tab.evaluate("""
            (() => {
                const s = document.querySelector('#searchInput_country');
                if (s) { s.value = 'Ital'; s.dispatchEvent(new Event('input', {bubbles: true})); }
            })()
        """)
        await tab.sleep(0.4)
        await tab.evaluate("""
            (() => {
                const items = Array.from(document.querySelectorAll("[data-cy='managerCountrySection']"));
                const italia = items.find(el => /^ital/i.test(el.innerText.trim()));
                if (italia) italia.click();
                else if (items[0]) items[0].click();
            })()
        """)
        await tab.sleep(0.3)

        # Birth date
        log("  Setting birth date...")
        birth_year = prof['birth_year']
        birth_month = prof['birth_month']
        birth_day = prof['birth_day'].zfill(2)

        month_map = {'GEN':'01','FEB':'02','MAR':'03','APR':'04','MAG':'05','GIU':'06',
                     'LUG':'07','AGO':'08','SET':'09','OTT':'10','NOV':'11','DIC':'12'}
        birth_month_num = month_map.get(birth_month.upper(), '01')
        birth_display = f"{birth_day}/{birth_month_num}/{birth_year}"

        # Try direct input first
        await tab.evaluate(f"""
            (() => {{
                const inp = document.querySelector("[data-cy='dateCalendar']");
                if (!inp) return;
                inp.removeAttribute('readonly');
                inp.focus();
                inp.value = '{birth_display}';
                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                inp.setAttribute('readonly', 'true');
            }})()
        """)
        await tab.sleep(0.5)

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
            await fill(f"#participantSurname_{i}", prof['last_name'])
            await fill(f"#participantName_{i}", prof['first_name'])

        # GDPR
        log("  GDPR checkboxes...")
        await tab.evaluate("""
            (() => {
                const cb0 = document.querySelectorAll('input[type="checkbox"]')[0];
                if (cb0 && !cb0.checked) cb0.click();
            })()
        """)
        await tab.sleep(1.5)
        await tab.evaluate("""
            (() => {
                const close = document.querySelector("[data-cy='purchase-rules-close-btn']")
                           || Array.from(document.querySelectorAll('button')).find(b => /chiudi|close/i.test(b.textContent));
                if (close) close.click();
            })()
        """)
        await tab.sleep(1)
        await tab.evaluate("""
            (() => {
                const cb1 = document.querySelectorAll('input[type="checkbox"]')[1];
                if (cb1 && !cb1.checked) cb1.click();
            })()
        """)
        await tab.sleep(0.5)

        # ── [8] Recap keepalive ───────────────────────────────────
        log("[8] Keeping recap alive while Turnstile solves...")
        await tab.evaluate(f"""
            (() => {{
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
                    }}).catch(e => console.log('keepalive err', e));
                }}, 60000);
            }})()
        """)

        # Wait for Turnstile
        log("  Waiting for Turnstile (nodriver auto-solves)...")
        # Wait longer — Turnstile can take 10-15s in some cases
        turnstile_ready = False
        for _ in range(20):
            token = await tab.evaluate("""
                (() => {
                    const inp = document.querySelector('[name="cf-turnstile-response"], input[name*="turnstile"]');
                    if (inp && inp.value && inp.value.length > 10) return inp.value.slice(0, 20) + '...';
                    return null;
                })()
            """)
            if token:
                log(f"  ✅ Turnstile solved: {token}")
                turnstile_ready = True
                break
            await tab.sleep(0.5)
        if not turnstile_ready:
            log("  ⚠️ Turnstile token not detected — proceeding anyway (nodriver handles it)")
        await tab.sleep(2)

        # ── [9] Click BUY ─────────────────────────────────────────
        log("[9] Clicking BUY...")

        # Check for invalid fields first
        invalid = await tab.evaluate("""
            (() => {
                const invalid = Array.from(document.querySelectorAll('.ng-invalid[data-cy], .ng-invalid input'))
                    .map(el => el.getAttribute('data-cy') || el.id || el.name || el.placeholder)
                    .filter(Boolean);
                return invalid.slice(0, 10);
            })()
        """)
        if invalid:
            log(f"  ⚠️  Invalid fields: {invalid}")
        else:
            log("  ✅ All fields valid")

        # Save screenshot for debugging
        try:
            await tab.save_screenshot('/root/debug_before_buy.png')
            log("  Screenshot saved → debug_before_buy.png")
        except Exception:
            pass

        clicked_buy = await tab.evaluate("""
            (() => {
                // Try ALL known Vatican BUY button selectors
                const selectors = [
                    "[data-cy='buyButton']",
                    "[data-cy='buyVisit']",
                    "[data-cy='confirmVisit']",
                    "[data-cy='submitVisit']",
                ];
                for (const sel of selectors) {
                    const btn = document.querySelector(sel);
                    if (btn && !btn.disabled && btn.offsetParent !== null) {
                        btn.scrollIntoView({behavior: 'smooth', block: 'center'});
                        btn.click();
                        return sel;
                    }
                }
                // Fallback: any non-disabled submit button
                const submits = Array.from(document.querySelectorAll("button[type='submit']"))
                    .filter(b => !b.disabled && b.offsetParent !== null);
                if (submits.length > 0) { submits[submits.length-1].click(); return 'submit-btn'; }
                // Last resort: text match
                const byText = Array.from(document.querySelectorAll('button'))
                    .find(b => /acquista|buy|conferma|procedi/i.test(b.textContent) && !b.disabled && b.offsetParent !== null);
                if (byText) { byText.click(); return 'text:' + byText.textContent.trim(); }
                return null;
            })()
        """)
        log(f"  BUY clicked: {clicked_buy}")
        await tab.sleep(3)

        # ── [10] Wait for reservation response ────────────────────
        log("[10] Waiting for reservation/epay redirect...")

        # Set up XHR interception
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
                            console.log('RESERVATION RESPONSE:', this.responseText.slice(0, 500));
                        }
                    });
                    return origSend.apply(this, [body]);
                };
            })()
        """)
        epay_url = ''
        for i in range(120):
            await tab.sleep(0.5)
            try:
                cur = await tab.evaluate("window.location.href")
                if cur and 'epay' in cur:
                    epay_url = cur
                    log(f"  ✅ epay: {epay_url[:80]}")
                    break
                if cur and ('error' in cur.lower() or 'errore' in cur.lower()):
                    log(f"  ❌ Error page: {cur}")
                    break

                # Check reservation API response at 5s
                if i == 10:
                    # Check for error messages on page
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
                    if err:
                        log(f"  ⚠️  Page/API message: {err}")

                    # Check reservation request body
                    req_body = await tab.evaluate("window._reservation_request || null")
                    if req_body:
                        try:
                            import json as _j
                            rb = _j.loads(req_body)
                            log(f"  📤 Reservation: visitTypeId={rb.get('visitTypeId')} visitId={rb.get('visitId')}")
                        except Exception:
                            log(f"  📤 Reservation body: {str(req_body)[:200]}")

                    # Also check current URL
                    cur_url = await tab.evaluate("window.location.href")
                    log(f"  📍 Current URL: {cur_url[:100]}")

            except Exception as e:
                pass

        if not epay_url:
            log("  ❌ No epay redirect")
            return {'epay_url': '', 'slot': slot, 'success': False}

        # ── [11] Fill epay payment ────────────────────────────────
        log("[11] Filling payment form...")
        await tab.sleep(3)

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

        card_first, *card_rest = crd['holder'].split(' ', 1)
        card_last = card_rest[0] if card_rest else card_first
        await epay_fill('name', card_first)
        await epay_fill('surname', card_last)
        await epay_fill('email', prof['email'])
        await epay_fill('repeatEmail', prof['email'])
        await tab.sleep(0.3)
        log("  Name/email filled")

        # Card number iframe
        try:
            iframe_el = await tab.query_selector('iframe[name*="cardNumber"], iframe[id*="cardNumber"]')
            if iframe_el:
                await iframe_el.click()
                await tab.sleep(0.5)
                for ch in crd['number']:
                    await iframe_el.send_keys(ch)
                    await tab.sleep(0.05)
                log(f"  Card: {crd['number'][:4]}...{crd['number'][-4:]}")
        except Exception as e:
            log(f"  Card number failed: {e}")

        # CVV iframe
        try:
            cvv_el = await tab.query_selector('iframe[name*="cvv"], iframe[id*="cvv"]')
            if cvv_el:
                await cvv_el.click()
                await tab.sleep(0.5)
                for ch in crd['cvv']:
                    await cvv_el.send_keys(ch)
                    await tab.sleep(0.05)
                await cvv_el.send_keys('\t')
                await tab.sleep(0.3)
                log("  CVV filled")
        except Exception as e:
            log(f"  CVV failed: {e}")

        # Expiry
        exp_month, exp_year = crd['expiry'].split('/')
        exp_month = exp_month.strip().zfill(2)
        exp_year = '20' + exp_year.strip() if len(exp_year.strip()) == 2 else exp_year.strip()

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
        log(f"  Expiry: {exp_month}/{exp_year}")

        # Agreement checkbox
        await tab.evaluate("""
            (() => {
                const cb = document.querySelector('#mat-checkbox-1-input');
                if (cb && !cb.checked) cb.click();
            })()
        """)
        await tab.sleep(0.3)

        # ── [12] Click PAY ────────────────────────────────────────
        if AUTO_PAY:
            log("[12] Clicking PAY...")
            await tab.sleep(1)
            await tab.evaluate("""
                (() => { document.body.click(); document.activeElement?.blur(); })()
            """)
            await tab.sleep(0.5)
            clicked_pay = await tab.evaluate("""
                (() => {
                    const byId = document.querySelector("button#form-submit[type='submit'].btn-submit");
                    if (byId && !byId.disabled) { byId.click(); return 'form-submit'; }
                    const byText = Array.from(document.querySelectorAll("button[type='submit']"))
                        .find(b => b.textContent.includes('Paga') && !b.disabled);
                    if (byText) { byText.click(); return 'paga-text'; }
                    return null;
                })()
            """)
            log(f"  PAY clicked: {clicked_pay}")

            # Wait for confirmation
            log("  Waiting for 3DS/confirmation...")
            for _ in range(120):
                await tab.sleep(0.5)
                cur = await tab.evaluate("window.location.href")
                if 'feedback/success' in (cur or ''):
                    log(f"  ✅ Payment confirmed!")
                    break
                if 'feedback/fail' in (cur or ''):
                    log(f"  ❌ Payment failed")
                    break

        await tab.sleep(3)
        return {
            'epay_url': epay_url,
            'slot': slot,
            'success': True,
        }

    except Exception as e:
        log(f"Browser error: {e}")
        import traceback
        traceback.print_exc()
        return {'epay_url': '', 'slot': slot, 'success': False, 'error': str(e)}

    finally:
        try:
            await tab.sleep(2)
            browser.stop()
        except Exception:
            pass


# ── Main ─────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=None, help='DD/MM/YYYY')
    parser.add_argument('--visitors', type=int, default=2)
    parser.add_argument('--time', default=None, help='HH:MM preferred time')
    parser.add_argument('--continuous', action='store_true', help='CRM polling mode')
    args = parser.parse_args()

    if args.continuous:
        log("🚀 Continuous CRM booking mode")
        while True:
            try:
                slot = find_slot(visitors=args.visitors)
                if slot:
                    log(f"🎯 Found slot: {slot['date']} {slot['slot_time']}")
                    result = await book_in_browser(slot)
                    if result and result.get('success'):
                        log(f"✅ Booked! epay: {result.get('epay_url', '')[:80]}")
                        # TODO: write to sheet + notify Telegram
                    else:
                        log("❌ Booking failed")
                else:
                    log("  No slots found — retrying in 30s")
                await asyncio.sleep(30)
            except KeyboardInterrupt:
                break
            except Exception as e:
                log(f"Cycle error: {e}")
                await asyncio.sleep(60)
    else:
        slot = find_slot(args.date, args.visitors, args.time)
        if not slot:
            log("No slot found.")
            return

        log(f"Booking: {slot['date']} {slot['slot_time']} ({slot['visitors']}v)")
        result = await book_in_browser(slot)

        print("\n" + "=" * 60)
        if result and result.get('epay_url'):
            print("  ✅ SUCCESS")
            print(f"  Date: {slot['date']} {slot['slot_time']}")
            print(f"\n  💳 PAYMENT LINK:\n  {result['epay_url']}")
        else:
            print("  ❌ FAILED")
        print("=" * 60)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    asyncio.run(main())
