"""
Explore Vatican's Angular app routing to understand the checkout flow.
Navigate step by step and log every URL + page state.
"""
import os, sys, django, asyncio, json
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from datetime import datetime, timedelta

BASE = 'https://tickets.museivaticani.va'
VISITORS = 1

async def explore():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox','--disable-blink-features=AutomationControlled','--disable-dev-shm-usage']
        )
        ctx = await browser.new_context(
            locale='it-IT', timezone_id='Europe/Rome',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 900},
        )
        await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        page = await ctx.new_page()

        # Log all navigation
        page.on('framenavigated', lambda f: print(f"  → NAV: {f.url}") if f == page.main_frame else None)

        # ── Step 1: Load home ─────────────────────────────────────────────────
        print("[1] Loading home page...")
        await page.goto(f'{BASE}/home', wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(2000)
        print(f"  URL: {page.url}")
        await page.screenshot(path='/tmp/step1_home.png')

        # Find the date/visit entry point
        print("\n  Looking for entry points...")
        # Vatican uses a calendar or date picker
        links = await page.query_selector_all('a, button')
        for el in links[:30]:
            try:
                text = (await el.inner_text()).strip()
                href = await el.get_attribute('href') or ''
                if text and len(text) < 50:
                    print(f"    '{text}' href='{href[:60]}'")
            except Exception:
                pass

        # ── Step 2: Navigate to visit selection ───────────────────────────────
        # Vatican URL pattern: /home/visit/{visitors}/{timestamp}/1/
        from zoneinfo import ZoneInfo
        rome = ZoneInfo('Europe/Rome')
        # Find first available date
        H_XHR = {
            'Accept': 'application/json, text/plain, */*',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': f'{BASE}/',
        }
        found_date = None
        found_tid = None
        found_slot = None

        for days in range(1, 120):
            d = (datetime.now() + timedelta(days=days)).strftime('%d/%m/%Y')
            r = await page.request.get(f'{BASE}/api/search/resultPerTag',
                params={'lang':'it','visitorNum':str(VISITORS),'visitDate':d,
                        'area':'1','who':'','page':'0','tag':'MV-Biglietti'},
                headers=H_XHR)
            if r.status != 200: continue
            data = await r.json()
            ticket = next((v for v in data.get('visits',[])
                           if 'musei vaticani' in v.get('name','').lower()
                           and 'ingresso' in v.get('name','').lower()
                           and v.get('availability') in ('AVAILABLE','LOW_AVAILABILITY')), None)
            if not ticket: continue
            tid = ticket['id']
            r2 = await page.request.get(f'{BASE}/api/visit/timeavail',
                params={'lang':'it','visitLang':'','visitTypeId':str(tid),
                        'visitorNum':str(VISITORS),'visitDate':d},
                headers=H_XHR)
            if r2.status != 200: continue
            d2 = await r2.json()
            slots = [sl for sl in d2.get('timetable',[])
                     if sl.get('availability') not in ('SOLD_OUT','NOT_ALLOWED')]
            if slots:
                found_date = d
                found_tid = tid
                found_slot = slots[0]
                break
            await asyncio.sleep(0.05)

        if not found_date:
            print("No slots found"); await browser.close(); return

        slot_id = str(found_slot['id'])
        slot_time = found_slot['time']
        print(f"\n[2] Found slot: {found_date} {slot_time} (id={slot_id})")

        # Build the Vatican visit URL
        dt_parts = found_date.split('/')
        dt_rome = datetime(int(dt_parts[2]), int(dt_parts[1]), int(dt_parts[0]), 0, 0, 0, tzinfo=rome)
        ts = int(dt_rome.timestamp() * 1000)
        visit_url = f'{BASE}/home/visit/{VISITORS}/{ts}/1/'
        print(f"  Visit URL: {visit_url}")

        await page.goto(visit_url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(3000)
        print(f"  URL after nav: {page.url}")
        await page.screenshot(path='/tmp/step2_visit.png')

        # Look for the ticket/slot on this page
        content = await page.content()
        has_slot_time = slot_time in content
        print(f"  Has slot time {slot_time}: {has_slot_time}")

        # Find clickable elements
        print("\n  Page elements:")
        for sel in ['button', '.slot', '.time-slot', '[class*="slot"]', '[class*="time"]']:
            els = await page.query_selector_all(sel)
            if els:
                print(f"    {sel}: {len(els)} elements")
                for el in els[:3]:
                    try:
                        text = (await el.inner_text()).strip()[:40]
                        cls = await el.get_attribute('class') or ''
                        print(f"      '{text}' class='{cls[:40]}'")
                    except Exception:
                        pass

        # ── Step 3: Try clicking the slot ─────────────────────────────────────
        print(f"\n[3] Looking for {slot_time} slot to click...")
        # Try various selectors for the time slot
        slot_clicked = False
        for sel in [
            f'button:has-text("{slot_time}")',
            f'[data-time="{slot_time}"]',
            f'span:has-text("{slot_time}")',
            f'div:has-text("{slot_time}")',
        ]:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    print(f"  Clicking: {sel}")
                    await el.click()
                    await page.wait_for_timeout(2000)
                    slot_clicked = True
                    print(f"  URL after click: {page.url}")
                    break
            except Exception as e:
                pass

        if not slot_clicked:
            print(f"  Could not find slot button — checking all visible text...")
            # Get all text content to understand page structure
            texts = await page.evaluate("""
                () => Array.from(document.querySelectorAll('button, .slot, [role="button"]'))
                    .filter(el => el.offsetParent !== null)
                    .map(el => ({text: el.innerText.trim().substring(0,40), class: el.className.substring(0,40)}))
                    .slice(0, 20)
            """)
            for t in texts:
                print(f"    '{t['text']}' class='{t['class']}'")

        await page.screenshot(path='/tmp/step3_slot.png')
        print(f"\n  Screenshots saved: /tmp/step1_home.png, /tmp/step2_visit.png, /tmp/step3_slot.png")
        print(f"  URL: {page.url}")

        await browser.close()

asyncio.run(explore())
