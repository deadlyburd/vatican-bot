"""
Vatican Playwright Checkout — Headful Browser
==============================================
Exact replication of Recording 09/04/2026 at 16:40:14
Run this LOCALLY (not in Docker) so you can see the browser.

Usage:
  pip install playwright
  playwright install chromium
  python test_pw_headful.py

The script will:
1. Open a real Chrome window
2. Navigate to Vatican tickets
3. Select ticket + time slot
4. Fill checkout form with profile data
5. Wait for you to solve Turnstile (or auto-solve if it works)
6. Click BUY and capture the epay URL
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# ── CONFIG — edit these ───────────────────────────────────────────────────────
DATE = '25/04/2026'       # DD/MM/YYYY — pick an available date
ADULTS = 2
KIDS = 1
VISITORS = ADULTS + KIDS
SLOT_TIME = '09:00'       # preferred time (will pick closest available)

# Profile data (replace with real data)
PROFILE = {
    'first_name': 'Aniile',
    'last_name': 'Skear',
    'email': 'your-email@example.com',
    'phone': 'your-phone-number',
    'city': 'ROMA',
    'country': 'Afghanistan',   # first option in dropdown
    'gender': 'M',
    'birth_date': {'year': 1987, 'month': 'JUN', 'day': 9},
    'language': 'en',
}

# Participant names (one per visitor)
PARTICIPANTS = [
    {'first_name': 'Aniile', 'last_name': 'Skear'},
]
# ─────────────────────────────────────────────────────────────────────────────

BASE = 'https://tickets.museivaticani.va'


async def run():
    from playwright.async_api import async_playwright

    rome = ZoneInfo('Europe/Rome')
    day, month, year = DATE.split('/')
    dt = datetime(int(year), int(month), int(day), 0, 0, 0, tzinfo=rome)
    ts = int(dt.timestamp() * 1000)

    # From recording: /home/visit/{visitors}/{timestamp}/1
    entry_url = f'{BASE}/home/visit/{VISITORS}/{ts}/1'

    print(f"Opening: {entry_url}")
    print(f"Date: {DATE} | Time: {SLOT_TIME} | Visitors: {VISITORS}")
    print(f"Profile: {PROFILE['first_name']} {PROFILE['last_name']}")
    print()

    async with async_playwright() as p:
        # HEADFUL — visible browser window
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=300,   # slow down actions so you can see what's happening
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--start-maximized',
            ]
        )
        ctx = await browser.new_context(
            locale='it-IT',
            timezone_id='Europe/Rome',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            viewport={'width': 1173, 'height': 911},  # exact from recording
            no_viewport=False,
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            "window.chrome={runtime:{}};"
        )
        page = await ctx.new_page()

        # Capture reservation response
        epay_result = {}

        async def on_response(response):
            if '/api/visit/reservation' in response.url:
                try:
                    data = await response.json()
                    print(f"\n{'='*50}")
                    print(f"RESERVATION HTTP {response.status}")
                    if response.status == 200:
                        epay = data.get('epay', {})
                        epay_result['url'] = epay.get('url', '')
                        epay_result['reference'] = data.get('referenceOrder', '')
                        epay_result['mac'] = epay.get('mac_avvio', '')
                        epay_result['total'] = data.get('total')
                        epay_result['full'] = data
                        print(f"✅ SUCCESS!")
                        print(f"Reference: {epay_result['reference']}")
                        print(f"Total: €{epay_result['total']}")
                        print(f"Epay URL: {epay_result['url']}")
                    else:
                        print(f"❌ Failed: {data}")
                    print('='*50)
                except Exception as e:
                    print(f"Response parse error: {e}")

        async def on_request(request):
            if 'epay.catholica.va/pay/public/init/' in request.url:
                import re
                m = re.search(r'/pay/public/init/([^/]+)/([^/;]+)/', request.url)
                if m:
                    epay_result['siv'] = m.group(1)
                    epay_result['mac_redirect'] = m.group(2)
                    epay_result['epay_init_url'] = request.url
                    print(f"\n🎯 Epay init: {request.url[:80]}")

        page.on('response', on_response)
        page.on('request', on_request)

        # ── Step 1: Navigate ──────────────────────────────────────────────────
        print(f"[1] Navigating...")
        await page.goto(entry_url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(2000)
        print(f"  URL: {page.url}")

        # ── Step 2: Get ticket_id from API ────────────────────────────────────
        print(f"[2] Getting ticket_id...")
        H_XHR = {
            'Accept': 'application/json, text/plain, */*',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': f'{BASE}/',
        }
        r = await page.request.get(f'{BASE}/api/search/resultPerTag',
            params={'lang':'it','visitorNum':str(VISITORS),'visitDate':DATE,
                    'area':'1','who':'','page':'0','tag':'MV-Biglietti'},
            headers=H_XHR)

        if r.status != 200:
            print(f"  Search API failed: {r.status}")
            input("Press Enter to close...")
            await browser.close()
            return

        visits = (await r.json()).get('visits', [])
        ticket = next((v for v in visits
                       if 'musei vaticani' in v.get('name','').lower()
                       and 'ingresso' in v.get('name','').lower()
                       and v.get('availability') in ('AVAILABLE','LOW_AVAILABILITY')), None)

        if not ticket:
            print(f"  No standard entry available for {DATE}")
            print(f"  Available tickets: {[v.get('name') for v in visits[:5]]}")
            input("Press Enter to close...")
            await browser.close()
            return

        tid = str(ticket['id'])
        print(f"  ticket_id={tid} | {ticket['name']} | {ticket['availability']}")

        # ── Step 3: Click ticket image (from recording step 3) ────────────────
        print(f"[3] Clicking ticket card...")
        try:
            # From recording: click ticket image to expand
            img_sel = f"#ticket_{tid} div.muvaTicketMainDivImage > img"
            img = await page.query_selector(img_sel)
            if img:
                await img.click()
                await page.wait_for_timeout(1000)
                print(f"  Clicked ticket image")
        except Exception as e:
            print(f"  Image click: {e}")

        # ── Step 4: Click PRENOTA / bookTicket ───────────────────────────────
        print(f"[4] Clicking bookTicket_{tid}...")
        try:
            await page.wait_for_selector(f"[data-cy='bookTicket_{tid}']", timeout=8000)
            await page.click(f"[data-cy='bookTicket_{tid}']")
            await page.wait_for_timeout(1500)
            print(f"  ✅ Clicked")
        except Exception as e:
            print(f"  bookTicket not found: {e}")

        # ── Step 5: Set quantity (Adults + Kids) ──────────────────────────────
        print(f"[5] Setting quantity (Adults: {ADULTS}, Kids: {KIDS})...")
        try:
            # Row 0: Biglietto Intero (Adults)
            # Row 1: Biglietto Ridotto (Children)
            
            # 1. Expand dropdown if needed
            qty_buttons = await page.query_selector_all("[data-cy='ticketQuantity']")
            if qty_buttons:
                # Adults: Click ADULTS-1 times (since 1 is usually default or we start from 1)
                # Actually, in the Vatican UI, clicking the '+' usually happens after opening the section.
                # However, the recording shows clicking 'ticketQuantity' then 'ticketQuantitySection'.
                
                # ADULTS
                print(f"  Selecting {ADULTS} Adults...")
                for i in range(ADULTS - (1 if ADULTS > 0 else 0)): # If ADULTS=1, do nothing else. If 2, click once.
                     # Click the first row's '+' or quantity section
                     sections = await page.query_selector_all("[data-cy='ticketQuantitySection']")
                     if len(sections) > 0:
                         await sections[0].click()
                         await page.wait_for_timeout(500)

                # KIDS
                if KIDS > 0:
                    print(f"  Selecting {KIDS} Kids...")
                    # First, we need to ensure the Ridotto row is visible or the quantity button is clicked
                    # Sometimes you need to click 'ticketQuantity' for the second row too
                    if len(qty_buttons) > 1:
                        # Click the second row's quantity dropdown/button
                        await qty_buttons[1].click()
                        await page.wait_for_timeout(500)
                        
                        for i in range(KIDS):
                            sections = await page.query_selector_all("[data-cy='ticketQuantitySection']")
                            if len(sections) > 1:
                                await sections[1].click()
                                await page.wait_for_timeout(500)
            
            print(f"  ✅ Quantities set")
        except Exception as e:
            print(f"  Quantity error: {e}")

        # ── Step 6: Select time slot ──────────────────────────────────────────
        print(f"[6] Selecting time {SLOT_TIME}...")
        await page.wait_for_timeout(1000)

        target_mins = int(SLOT_TIME.split(':')[0]) * 60 + int(SLOT_TIME.split(':')[1])

        # Get all times (including hidden ones in afternoon section)
        all_times = await page.evaluate("""
            () => Array.from(document.querySelectorAll(
                "[data-cy='time'] div.muvaCalendarNumber, [data-cy='time'] div.muvaCalendarDaySoldOut"
            )).map(el => el.innerText.trim()).filter(t => /^\\d{2}:\\d{2}$/.test(t))
        """)
        print(f"  Available times: {all_times}")

        if SLOT_TIME not in all_times and target_mins >= 14 * 60:
            # Click afternoon section
            print(f"  Clicking afternoon section...")
            await page.evaluate("""
                () => {
                    const sections = Array.from(document.querySelectorAll('div.showGTMobile > div > div'))
                        .filter(el => el.offsetParent !== null);
                    if (sections.length >= 2) sections[1].click();
                }
            """)
            await page.wait_for_timeout(1500)
            all_times = await page.evaluate("""
                () => Array.from(document.querySelectorAll(
                    "[data-cy='time'] div.muvaCalendarNumber, [data-cy='time'] div.muvaCalendarDaySoldOut"
                )).map(el => el.innerText.trim()).filter(t => /^\\d{2}:\\d{2}$/.test(t))
            """)
            print(f"  Times after section click: {all_times}")

        if all_times:
            exact = SLOT_TIME if SLOT_TIME in all_times else None
            best = exact or min(all_times, key=lambda t: abs(
                int(t.split(':')[0]) * 60 + int(t.split(':')[1]) - target_mins
            ))
            print(f"  Clicking: {best}")
            # From recording: xpath //*[@data-cy="time"]/div[1] — first muvaCalendarNumber
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
                print(f"  ✅ Time selected: {best}")
                await page.wait_for_timeout(1500)

        # ── Step 7: Click PROCEDI ─────────────────────────────────────────────
        print(f"[7] Clicking PROCEDI...")
        await page.wait_for_timeout(500)
        try:
            # From recording: [data-cy='bookVisit']
            await page.click("[data-cy='bookVisit']")
            await page.wait_for_timeout(4000)
            print(f"  ✅ Clicked | URL: {page.url}")
        except Exception as e:
            print(f"  bookVisit: {e}")

        # Wait for checkout form
        print(f"  Waiting for checkout form...")
        try:
            await page.wait_for_selector("[data-cy='managerSurname']", timeout=15000)
            print(f"  ✅ Checkout form visible | URL: {page.url}")
        except Exception as e:
            print(f"  Form not found: {e} | URL: {page.url}")

        # ── Step 8: GDPR checkboxes FIRST (from recording order) ─────────────
        print(f"[8] GDPR checkboxes...")
        await page.wait_for_timeout(1000)

        # From recording: checkbox first, then form fill
        try:
            # Find first GDPR checkbox (aria label contains "Norme Generali")
            cb1 = await page.query_selector(
                "input[aria-label*='Norme'], #mat-mdc-checkbox-1-input, "
                "input[type='checkbox']:first-of-type"
            )
            if not cb1:
                # Try by aria label
                cb1 = await page.query_selector("input[type='checkbox']")
            if cb1 and not await cb1.is_checked():
                await cb1.click()
                await page.wait_for_timeout(800)
                # Close dialog
                close = await page.query_selector(
                    "[data-cy='purchase-rules-close-btn'] mat-icon, "
                    "div.cdk-overlay-container mat-icon"
                )
                if close:
                    await close.click()
                    await page.wait_for_timeout(500)
                    print(f"  Closed GDPR dialog")
        except Exception as e:
            print(f"  GDPR cb1: {e}")

        # Second checkbox
        try:
            cbs = await page.query_selector_all("input[type='checkbox']")
            for cb in cbs[1:]:  # skip first (already checked)
                if not await cb.is_checked():
                    await cb.click()
                    await page.wait_for_timeout(300)
        except Exception as e:
            print(f"  GDPR cb2: {e}")

        # ── Step 9: Fill manager form ─────────────────────────────────────────
        print(f"[9] Filling form...")
        await page.wait_for_timeout(500)

        async def fill(sel, val):
            try:
                el = await page.wait_for_selector(sel, timeout=3000)
                if el:
                    await el.triple_click()
                    await el.fill(str(val))
                    return True
            except Exception:
                return False

        # From recording: click container div first, then fill fields
        try:
            container = await page.query_selector("app-manager-form > div > div > div:nth-of-type(1) > div")
            if container:
                await container.click()
                await page.wait_for_timeout(300)
        except Exception:
            pass

        await fill("[data-cy='managerSurname']", PROFILE['last_name'])
        await fill("[data-cy='managerName']", PROFILE['first_name'])

        # Gender dropdown
        try:
            await page.click("[data-cy='managerSex']")
            await page.wait_for_timeout(400)
            sex_opt = await page.query_selector("[data-cy='managerSexSection']")
            if sex_opt:
                await sex_opt.click()
                await page.wait_for_timeout(300)
        except Exception as e:
            print(f"  Gender: {e}")

        # Country dropdown
        try:
            await page.click("[data-cy='managerCountry']")
            await page.wait_for_timeout(400)
            # From recording: clicks Afghanistan (first option)
            country_opt = await page.query_selector("[data-cy='managerCountrySection']")
            if country_opt:
                await country_opt.click()
                await page.wait_for_timeout(300)
        except Exception as e:
            print(f"  Country: {e}")

        # Click div 5 (between country and city in recording)
        try:
            div5 = await page.query_selector("div.muvaManagerContainer div:nth-of-type(5) > div")
            if div5:
                await div5.click()
                await page.wait_for_timeout(200)
        except Exception:
            pass

        await fill("[data-cy='managerCity']", PROFILE['city'])

        # Birth date — from recording: click dateCalendar, pick year/month/day
        try:
            date_input = await page.query_selector("[data-cy='dateCalendar']")
            if date_input:
                await date_input.click()
                await page.wait_for_timeout(800)
                bd = PROFILE['birth_date']
                # Pick year
                year_btn = await page.query_selector(f"span.mat-calendar-body-cell-content:has-text('{bd['year']}')")
                if year_btn:
                    await year_btn.click()
                    await page.wait_for_timeout(500)
                # Pick month
                month_btn = await page.query_selector(f"span.mat-calendar-body-cell-content:has-text('{bd['month']}')")
                if month_btn:
                    await month_btn.click()
                    await page.wait_for_timeout(500)
                # Pick day
                day_btn = await page.query_selector(f"span.mat-calendar-body-cell-content:has-text('{bd['day']}')")
                if day_btn:
                    await day_btn.click()
                    await page.wait_for_timeout(500)
                print(f"  Birth date set: {bd['year']}/{bd['month']}/{bd['day']}")
        except Exception as e:
            print(f"  Birth date: {e}")

        # Click div 7 (between birthdate and email in recording)
        try:
            div7 = await page.query_selector("div.muvaManagerContainer div > div:nth-of-type(7)")
            if div7:
                await div7.click()
                await page.wait_for_timeout(200)
        except Exception:
            pass

        await fill("[data-cy='managerEmail']", PROFILE['email'])
        await fill("[data-cy='managerConfirmEmail']", PROFILE['email'])
        await fill("[data-cy='managerPhone']", PROFILE['phone'])

        print(f"  Manager form filled")

        # ── Step 10: Fill participants ────────────────────────────────────────
        print(f"[10] Filling participants...")
        for i, p in enumerate(PARTICIPANTS[:VISITORS]):
            await fill(f"#participantSurname_{i}", p['last_name'])
            await fill(f"#participantName_{i}", p['first_name'])
        print(f"  Participants filled")

        # ── Step 11: Wait for Turnstile ───────────────────────────────────────
        print(f"\n[11] Waiting for Turnstile...")
        print(f"  The browser will try to auto-solve Turnstile.")
        print(f"  If it doesn't solve in 60s, you may need to click the checkbox manually.")

        for i in range(120):
            await asyncio.sleep(1)
            try:
                val = await page.evaluate(
                    "()=>{const i=document.querySelector('input[name=\"cf-turnstile-response\"]');"
                    "return i?i.value:'';}"
                )
                if val and len(val) > 100:
                    print(f"  ✅ Turnstile solved! prefix={val[:4]} len={len(val)}")
                    break
                if i == 30:
                    print(f"  30s elapsed — if Turnstile is visible, click it manually")
                if i % 20 == 0 and i > 0:
                    print(f"  ... {i}s waiting")
            except Exception:
                pass
        else:
            print(f"  Turnstile timeout — submitting anyway")

        # ── Step 12: Click BUY ────────────────────────────────────────────────
        print(f"\n[12] Clicking BUY...")
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
                    print(f"  Clicking: '{text.strip()[:20]}'")
                    await btn.click()
                    break
            except Exception:
                pass

        # Wait for epay navigation
        print(f"\n[13] Waiting for epay...")
        try:
            await page.wait_for_url('**/epay.catholica.va/**', timeout=30000)
            print(f"  ✅ Navigated to epay: {page.url[:80]}")
        except Exception:
            for _ in range(15):
                await asyncio.sleep(1)
                if epay_result.get('reference') or epay_result.get('siv'):
                    break

        # ── Result ────────────────────────────────────────────────────────────
        print(f"\n{'='*60}")
        if epay_result.get('reference') or epay_result.get('siv'):
            print(f"✅ SUCCESS!")
            if epay_result.get('reference'):
                print(f"Reference: {epay_result['reference']}")
                print(f"Total: €{epay_result.get('total')}")
                print(f"Epay URL: {epay_result.get('url')}")
                print(f"mac_avvio: {epay_result.get('mac','')[:20]}...")
            if epay_result.get('siv'):
                print(f"SIV: {epay_result['siv']}")
                print(f"Epay init: {epay_result.get('epay_init_url','')[:80]}")
        else:
            print(f"❌ No epay result captured")
            print(f"Final URL: {page.url}")
        print('='*60)

        # Save result
        with open('/tmp/epay_result.json', 'w') as f:
            json.dump(epay_result, f, indent=2)
        print(f"\nResult saved to /tmp/epay_result.json")

        input("\nPress Enter to close browser...")
        await browser.close()

    return epay_result


if __name__ == '__main__':
    asyncio.run(run())
