"""
Vatican Playwright Checkout
============================
Exact flow from Playwright recordings (4/9/2026).
Uses data-cy selectors — no 2captcha needed, browser solves Turnstile natively.

Two confirmed flows:
  Morning flow (recording 1):
    fromtag URL → bookTicket_{id} → ticketQuantity → ticketQuantitySection
    → time slot → PROCEDI → fill form → GDPR → Turnstile → BUY

  Afternoon flow (recording 2):
    fromtag URL → click time section nav → click time slot
    → quantity dropdown → ticketQuantitySection → PROCEDI
    → GDPR → Turnstile → BUY

Key selectors:
  [data-cy='bookTicket_{id}']          — book button per ticket
  [data-cy='ticketQuantity']           — quantity + button
  [data-cy='ticketQuantitySection']    — quantity dropdown item
  [data-cy='time'] div.muvaCalendarNumber  — available time slot
  [data-cy='time'] div.muvaCalendarDaySoldOut — sold-out slot (still clickable)
  div.bookVisitContainer / [data-cy='bookVisit'] — PROCEED button
  [data-cy='managerSurname'] etc       — form fields
  #participantSurname_0 / #participantName_0 — participant fields
  #mat-mdc-checkbox-1-input            — GDPR checkbox 1 (opens dialog)
  [data-cy='purchase-rules-close-btn'] — close GDPR dialog
  #mat-mdc-checkbox-4-input            — GDPR checkbox 2
  div.captchaContainer                 — Turnstile container
  [data-cy='buyButton'] / #buyButton   — BUY button
"""
import logging
import asyncio
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
BASE = 'https://tickets.museivaticani.va'


async def checkout_full_ui(
    date: str,       # DD/MM/YYYY
    slot_time: str,  # HH:MM preferred
    visitors: int,
    profile,         # BuyerProfile
    timeout_s: int = 180,
) -> dict:
    from playwright.async_api import async_playwright

    rome = ZoneInfo('Europe/Rome')
    day, month, year = date.split('/')
    dt = datetime(int(year), int(month), int(day), 0, 0, 0, tzinfo=rome)
    ts = int(dt.timestamp() * 1000)
    entry_url = f'{BASE}/home/fromtag/{visitors}/{ts}/MV-Biglietti/1'

    H_XHR = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'it-IT,it;q=0.9',
        'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': f'{BASE}/',
    }

    result = {
        'success': False, 'error': None,
        'epay_url': None, 'reference': None,
        'epay_params': None, 'total': None,
        'siv_transaction_id': None, 'upp_redirect_mac': None,
    }

    async with async_playwright() as p:
        # Try headless first; if Turnstile doesn't solve, relaunch headful
        for attempt, headless in enumerate([True, False]):
            mode = 'headless' if headless else 'headful'
            logger.info(f"🌐 Playwright attempt {attempt+1}/2 ({mode})")
            attempt_result = await _run_checkout_attempt(
                p, entry_url, date, slot_time, visitors, profile,
                H_XHR, headless=headless, timeout_s=timeout_s, result=result
            )
            if attempt_result.get('success') or attempt_result.get('turnstile_solved'):
                return attempt_result
            if attempt == 0:
                logger.warning(f"  Headless Turnstile failed — relaunching as headful browser")
            result = attempt_result

    return result


async def _run_checkout_attempt(p, entry_url, date, slot_time, visitors, profile,
                                 H_XHR, headless, timeout_s, result):
    """Single checkout attempt — headless or headful."""
    user_data_dir = '/tmp/pw_vatican_profile'
    launch_args = [
        '--no-sandbox',
        '--disable-blink-features=AutomationControlled',
        '--disable-dev-shm-usage',
        '--window-size=828,915',
    ]
    if headless:
        launch_args.append('--disable-gpu')
    else:
        # Start virtual display for headful mode in Docker
        import subprocess, os as _os
        try:
            subprocess.Popen(['Xvfb', ':99', '-screen', '0', '1280x1024x24'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            import time as _time; _time.sleep(1)
        except Exception:
            pass
        _os.environ['DISPLAY'] = ':99'
        launch_args.append('--display=:99')

    try:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            args=launch_args,
            locale='it-IT',
            timezone_id='Europe/Rome',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            viewport={'width': 828, 'height': 915},
            extra_http_headers={'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7'},
        )
    except Exception as e:
        result['error'] = f"Browser launch failed: {e}"
        return result

    await ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}, app: {}};
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['it-IT','it','en-US','en']});
    """)
    page = await ctx.new_page()

    # Capture reservation response
    async def on_response(response):
            if '/api/visit/reservation' in response.url:
                try:
                    data = await response.json()
                    logger.info(f"  Reservation HTTP {response.status}")
                    if response.status == 200:
                        epay = data.get('epay', {})
                        result['success'] = True
                        result['epay_url'] = epay.get('url', '')
                        result['reference'] = data.get('referenceOrder', '')
                        result['total'] = data.get('total')
                        result['epay_params'] = {
                            'mac_avvio': epay.get('mac_avvio', ''),
                            'idnegozio': epay.get('idnegozio', 'SIV001'),
                            'valuta': epay.get('valuta', '978'),
                            'tcontab': epay.get('tcontab', 'D'),
                            'tautor': epay.get('tautor', 'I'),
                            'urlMs': epay.get('urlMs', ''),
                            'urldone': epay.get('urldone', ''),
                            'urlback': epay.get('urlback', ''),
                            'referenceOrder': data.get('referenceOrder', ''),
                        }
                        logger.info(f"  ✅ ref={result['reference']}")
                    else:
                        result['error'] = f"Reservation {response.status}: {data}"
                except Exception as e:
                    logger.warning(f"  Response parse: {e}")

    # Capture epay navigation
    async def on_request(request):
            url = request.url
            if 'epay.catholica.va/pay/public/init/' in url:
                import re
                m = re.search(r'/pay/public/init/([^/]+)/([^/;]+)/', url)
                if m:
                    result['siv_transaction_id'] = m.group(1)
                    result['upp_redirect_mac'] = m.group(2)
                    if not result['epay_url']:
                        result['epay_url'] = f'https://epay.catholica.va/pay/public/init/{m.group(1)}/{m.group(2)}/it'
                    result['success'] = True
                    logger.info(f"  🎯 Epay: siv={m.group(1)[:20]} mac={m.group(2)[:10]}")

    page.on('response', on_response)
    page.on('request', on_request)

    try:
            # ── 1. Navigate ───────────────────────────────────────────────────
            logger.info(f"[1] {entry_url}")
            await page.goto(entry_url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(2000)

            # ── 2. Get ticket_id ──────────────────────────────────────────────
            r = await page.request.get(f'{BASE}/api/search/resultPerTag',
                params={'lang':'it','visitorNum':str(visitors),'visitDate':date,
                        'area':'1','who':'','page':'0','tag':'MV-Biglietti'},
                headers=H_XHR)
            if r.status != 200:
                result['error'] = f"Search {r.status}"; await ctx.close(); return result

            visits = (await r.json()).get('visits', [])
            ticket = next((v for v in visits
                           if 'musei vaticani' in v.get('name','').lower()
                           and 'ingresso' in v.get('name','').lower()
                           and v.get('availability') in ('AVAILABLE','LOW_AVAILABILITY')), None)
            if not ticket:
                result['error'] = 'No standard entry available'; await ctx.close(); return result

            tid = str(ticket['id'])
            logger.info(f"  ticket_id={tid}")

            # ── 3. Click bookTicket (expands the ticket card) ─────────────────
            logger.info(f"[3] Clicking bookTicket_{tid}...")
            try:
                await page.wait_for_selector(f"[data-cy='bookTicket_{tid}']", timeout=8000)
                await page.click(f"[data-cy='bookTicket_{tid}']")
                await page.wait_for_timeout(2000)
                logger.info(f"  ✅ bookTicket clicked")
            except Exception as e:
                logger.warning(f"  bookTicket not found ({e}) — card may already be expanded")

            # ── 4. Set quantity (MUST be before time selection) ───────────────
            # From recordings: ticketQuantity + ticketQuantitySection enables PROCEDI
            logger.info(f"[4] Setting quantity ({visitors})...")
            try:
                qty = await page.query_selector("[data-cy='ticketQuantity']")
                if qty: await qty.click(); await page.wait_for_timeout(400)
                qty_sec = await page.query_selector("[data-cy='ticketQuantitySection']")
                if qty_sec: await qty_sec.click(); await page.wait_for_timeout(400); logger.info(f"  ✅ Quantity set")
                for _ in range(visitors - 1):
                    q2 = await page.query_selector("[data-cy='ticketQuantity']")
                    if q2: await q2.click(); await page.wait_for_timeout(300)
                    q2s = await page.query_selector("[data-cy='ticketQuantitySection']")
                    if q2s: await q2s.click(); await page.wait_for_timeout(300)
            except Exception as e:
                logger.debug(f"  Quantity: {e}")

            # ── 5. Navigate to correct time section ───────────────────────────
            # Vatican shows MATTINA (morning) and POMERIGGIO (afternoon) tabs
            logger.info(f"[5] Navigating to time section for {slot_time}...")
            target_mins = int(slot_time.split(':')[0]) * 60 + int(slot_time.split(':')[1])

            # Check initial times (morning tab is selected by default)
            all_times_initial = await page.evaluate("""
                () => Array.from(document.querySelectorAll(
                    "[data-cy='time'] div.muvaCalendarNumber, [data-cy='time'] div.muvaCalendarDaySoldOut"
                )).map(el => el.innerText.trim()).filter(t => /^\\d{2}:\\d{2}$/.test(t))
            """)
            logger.info(f"  Initial times (MATTINA): {all_times_initial}")

            if slot_time not in all_times_initial and target_mins >= 14 * 60:
                # Click POMERIGGIO tab to reveal afternoon slots
                logger.info(f"  Clicking POMERIGGIO tab...")
                clicked = await page.evaluate("""
                    () => {
                        const tabs = Array.from(document.querySelectorAll('.tab'))
                            .filter(el => el.offsetParent !== null);
                        for (const tab of tabs) {
                            if (tab.innerText.trim().toUpperCase().includes('POMERIGGIO')) {
                                tab.click();
                                return 'POMERIGGIO';
                            }
                        }
                        // Fallback: click 2nd tab
                        if (tabs.length >= 2) { tabs[1].click(); return '2nd tab'; }
                        return false;
                    }
                """)
                logger.info(f"  Tab click: {clicked}")
                await page.wait_for_timeout(1000)

            # ── 6. Click the target time slot ─────────────────────────────────
            logger.info(f"[5] Clicking time slot...")
            all_times = await page.evaluate("""
                () => Array.from(document.querySelectorAll(
                    "[data-cy='time'] div.muvaCalendarNumber, [data-cy='time'] div.muvaCalendarDaySoldOut"
                )).map(el => el.innerText.trim()).filter(t => /^\\d{2}:\\d{2}$/.test(t))
            """)
            logger.info(f"  Times: {all_times}")

            if all_times:
                exact = slot_time if slot_time in all_times else None
                best = exact or min(all_times, key=lambda t: abs(
                    int(t.split(':')[0]) * 60 + int(t.split(':')[1]) - target_mins
                ))
                logger.info(f"  Clicking: {best}")
                clicked = await page.evaluate(f"""
                    () => {{
                        const els = Array.from(document.querySelectorAll(
                            "[data-cy='time'] div.muvaCalendarNumber, [data-cy='time'] div.muvaCalendarDaySoldOut"
                        )).filter(el => el.innerText.trim() === '{best}');
                        if (els.length > 0) {{
                            els[0].scrollIntoView({{behavior:'instant',block:'center'}});
                            els[0].click();
                            return true;
                        }}
                        return false;
                    }}
                """)
                if clicked:
                    logger.info(f"  ✅ Time clicked: {best}")
                    await page.wait_for_timeout(1500)
            else:
                logger.warning(f"  No time slots found")

            # ── 7. Click PROCEED ──────────────────────────────────────────────
            logger.info(f"[7] Clicking PROCEED...")
            await page.wait_for_timeout(500)

            proceed_clicked = False
            for sel in [
                "[data-cy='bookVisit']",
                "button[data-cy='bookVisit']",
                "div.bookVisitContainer button",
                "button:has-text('PROCEDI')",
                "button:has-text('PROCEED')",
                "div.bookVisitContainer",
            ]:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        text = await el.inner_text()
                        logger.info(f"  Clicking: '{text.strip()[:20]}'")
                        await el.click()
                        proceed_clicked = True
                        await page.wait_for_timeout(4000)
                        break
                except Exception:
                    pass

            if not proceed_clicked:
                logger.warning(f"  PROCEED not found")

            # Wait for checkout form
            logger.info(f"  Waiting for checkout form... URL={page.url}")
            try:
                await page.wait_for_selector("[data-cy='managerSurname']", timeout=15000)
                logger.info(f"  ✅ Checkout form visible")
            except Exception:
                logger.warning(f"  Checkout form not found — URL={page.url}")

            # ── 8. Fill manager form ──────────────────────────────────────────
            logger.info(f"[8] Filling form...")
            await page.wait_for_timeout(1000)

            async def fill(sel, val):
                try:
                    el = await page.wait_for_selector(sel, timeout=3000)
                    if el:
                        await el.triple_click()
                        await el.fill(str(val))
                        return True
                except Exception:
                    return False

            await fill("[data-cy='managerSurname']", profile.last_name)
            await fill("[data-cy='managerName']", profile.first_name)
            await fill("[data-cy='managerCity']", profile.city or 'ROMA')
            await fill("[data-cy='managerEmail']", profile.email)
            await fill("[data-cy='managerConfirmEmail']", profile.email)
            await fill("[data-cy='managerPhone']", profile.phone)

            # Gender dropdown
            try:
                await page.click("[data-cy='managerSex']")
                await page.wait_for_timeout(400)
                opt = await page.query_selector("[data-cy='managerSexSection']")
                if opt: await opt.click(); await page.wait_for_timeout(300)
            except Exception: pass

            # Country dropdown
            try:
                await page.click("[data-cy='managerCountry']")
                await page.wait_for_timeout(400)
                opt = await page.query_selector("[data-cy='managerCountrySection']")
                if opt: await opt.click(); await page.wait_for_timeout(300)
            except Exception: pass

            # Birth date
            try:
                if profile.birth_date:
                    bd = profile.birth_date
                    toggle = await page.query_selector(
                        "[data-cy='managerBirthDate'] mat-datepicker-toggle button, "
                        "[data-cy='managerBirthDate'] button"
                    )
                    if toggle:
                        await toggle.click()
                        await page.wait_for_timeout(800)
                        year_btn = await page.query_selector(f"span.mat-calendar-body-cell-content:has-text('{bd.year}')")
                        if year_btn:
                            await year_btn.click(); await page.wait_for_timeout(500)
                        month_abbr = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'][bd.month-1]
                        month_btn = await page.query_selector(f"span.mat-calendar-body-cell-content:has-text('{month_abbr}')")
                        if month_btn:
                            await month_btn.click(); await page.wait_for_timeout(500)
                        day_btn = await page.query_selector(f"span.mat-calendar-body-cell-content:has-text('{bd.day}')")
                        if day_btn:
                            await day_btn.click(); await page.wait_for_timeout(500)
            except Exception as e:
                logger.debug(f"  Birthdate: {e}")

            # Language dropdown
            try:
                await page.click("[data-cy='managerLanguage']")
                await page.wait_for_timeout(400)
                opt = await page.query_selector("[data-cy='managerLanguageSection']")
                if opt: await opt.click(); await page.wait_for_timeout(300)
            except Exception: pass

            logger.info(f"  Manager form filled")

            # ── 9. Fill participants ──────────────────────────────────────────
            import json as _json
            participant_names = []
            if getattr(profile, 'participants_json', None):
                try:
                    participant_names = _json.loads(profile.participants_json)
                except Exception:
                    pass

            for i in range(visitors):
                first = participant_names[i].get('first_name', profile.first_name) if i < len(participant_names) else profile.first_name
                last = participant_names[i].get('last_name', profile.last_name) if i < len(participant_names) else profile.last_name
                await fill(f"#participantSurname_{i}", last)
                await fill(f"#participantName_{i}", first)

            # ── 10. GDPR checkboxes ───────────────────────────────────────────
            logger.info(f"[10] GDPR...")
            try:
                cb1 = await page.query_selector("#mat-mdc-checkbox-1-input")
                if cb1 and not await cb1.is_checked():
                    await cb1.click()
                    await page.wait_for_timeout(800)
                    # Close dialog
                    close = await page.query_selector(
                        "[data-cy='purchase-rules-close-btn'] mat-icon, "
                        "[data-cy='purchase-rules-close-btn']"
                    )
                    if close:
                        await close.click(); await page.wait_for_timeout(400)
            except Exception as e:
                logger.debug(f"  GDPR cb1: {e}")

            try:
                cb4 = await page.query_selector("#mat-mdc-checkbox-4-input")
                if cb4 and not await cb4.is_checked():
                    await cb4.click(); await page.wait_for_timeout(300)
            except Exception: pass

            # ── 11. Wait for Turnstile ────────────────────────────────────────
            logger.info(f"[11] Waiting for Turnstile ({timeout_s}s)...")
            try:
                captcha = await page.query_selector("div.captchaContainer, iframe[src*='turnstile']")
                if captcha:
                    await captcha.scroll_into_view_if_needed()
                    await captcha.click()
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            # Headless: only wait 60s, then bail so we can retry headful
            wait_time = 60 if headless else timeout_s
            turnstile_solved = False
            for i in range(wait_time):
                await asyncio.sleep(1)
                try:
                    val = await page.evaluate(
                        "()=>{const i=document.querySelector('input[name=\"cf-turnstile-response\"]');"
                        "return i?i.value:'';}"
                    )
                    if val and len(val) > 100:
                        logger.info(f"  ✅ Turnstile solved! prefix={val[:4]} len={len(val)}")
                        turnstile_solved = True
                        break
                    if i % 20 == 0 and i > 0:
                        logger.info(f"  ... {i}s | URL={page.url}")
                except Exception:
                    pass
            else:
                if headless:
                    logger.warning(f"  Headless Turnstile timeout — retrying with headful browser")
                    result['turnstile_solved'] = False
                    await ctx.close()
                    return result
                logger.warning(f"  Turnstile timeout — submitting anyway")

            # ── 12. Click BUY ─────────────────────────────────────────────────
            logger.info(f"[12] Clicking BUY...")
            for sel in [
                "[data-cy='buyButton']",
                "#buyButton",
                "button:has-text('BUY')",
                "button:has-text('ACQUISTA')",
                "button[type='submit']",
            ]:
                try:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        text = await btn.inner_text()
                        logger.info(f"  Clicking: '{text.strip()[:20]}'")
                        await btn.click()
                        break
                except Exception:
                    pass

            # Wait for epay navigation
            logger.info(f"[13] Waiting for epay...")
            try:
                await page.wait_for_url('**/epay.catholica.va/**', timeout=30000)
                if not result['epay_url']:
                    result['epay_url'] = page.url
                    result['success'] = True
                logger.info(f"  ✅ Navigated to epay")
            except Exception:
                for _ in range(15):
                    await asyncio.sleep(1)
                    if result['success'] or result['siv_transaction_id']:
                        break

            if not result['success'] and not result['error']:
                result['error'] = f'No epay. URL={page.url}'

    except Exception as e:
            logger.error(f"Checkout error: {e}")
            result['error'] = str(e)
    finally:
            try:
                await page.screenshot(path='/tmp/pw_checkout_final.png')
            except Exception:
                pass
            await ctx.close()

    result['turnstile_solved'] = result.get('success', False)
    return result


def checkout_ui_sync(date: str, slot_time: str, visitors: int,
                     profile, timeout_s: int = 180) -> dict:
    return asyncio.run(checkout_full_ui(date, slot_time, visitors, profile, timeout_s))
