"""Debug: screenshot after each step to see what's happening"""
import os, sys, django, asyncio, json
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import BuyerProfile, Agency
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE = 'https://tickets.museivaticani.va'
VISITORS = 1

agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
profile = BuyerProfile.objects.filter(agency=agency).first()

async def debug():
    from playwright.async_api import async_playwright

    rome = ZoneInfo('Europe/Rome')
    # Use April 15 which we know has slots
    date = '15/04/2026'
    day, month, year = date.split('/')
    dt = datetime(int(year), int(month), int(day), 0, 0, 0, tzinfo=rome)
    ts = int(dt.timestamp() * 1000)
    entry_url = f'{BASE}/home/fromtag/{VISITORS}/{ts}/MV-Biglietti/1'

    H_XHR = {'Accept':'application/json, text/plain, */*','X-Requested-With':'XMLHttpRequest','Referer':f'{BASE}/'}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
        ctx = await browser.new_context(
            locale='it-IT', timezone_id='Europe/Rome',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            viewport={'width': 828, 'height': 915},
        )
        await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        page = await ctx.new_page()

        # Log all navigations
        page.on('framenavigated', lambda f: print(f"  NAV→ {f.url[:80]}") if f == page.main_frame else None)

        print(f"[1] Loading {entry_url}")
        await page.goto(entry_url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path='/tmp/debug_1_loaded.png')
        print(f"  URL: {page.url}")

        # Get ticket_id
        r = await page.request.get(f'{BASE}/api/search/resultPerTag',
            params={'lang':'it','visitorNum':str(VISITORS),'visitDate':date,'area':'1','who':'','page':'0','tag':'MV-Biglietti'},
            headers=H_XHR)
        visits = (await r.json()).get('visits', [])
        ticket = next((v for v in visits if 'musei vaticani' in v.get('name','').lower() and 'ingresso' in v.get('name','').lower()), None)
        tid = str(ticket['id']) if ticket else None
        print(f"  tid={tid}")

        print(f"\n[2] Clicking bookTicket_{tid}")
        await page.click(f"[data-cy='bookTicket_{tid}']")
        await page.wait_for_timeout(2000)
        await page.screenshot(path='/tmp/debug_2_after_book.png')
        print(f"  URL: {page.url}")

        # Show what's on page now
        times = await page.evaluate("""
            () => Array.from(document.querySelectorAll("[data-cy='time'] div.muvaCalendarNumber"))
                .filter(el => el.offsetParent !== null)
                .map(el => el.innerText.trim())
        """)
        print(f"  Times visible: {times}")

        print(f"\n[2.5] Clicking ticketQuantity (required even for 1 visitor)")
        try:
            qty = await page.query_selector("[data-cy='ticketQuantity']")
            if qty:
                await qty.click()
                await page.wait_for_timeout(500)
                print(f"  Clicked ticketQuantity")
            qty_sec = await page.query_selector("[data-cy='ticketQuantitySection']")
            if qty_sec:
                await qty_sec.click()
                await page.wait_for_timeout(500)
                print(f"  Clicked ticketQuantitySection")
        except Exception as e:
            print(f"  Quantity: {e}")

        print(f"\n[3] Clicking time 11:00")
        clicked = await page.evaluate("""
            () => {
                const els = Array.from(document.querySelectorAll("[data-cy='time'] div.muvaCalendarNumber"))
                    .filter(el => el.offsetParent !== null && el.innerText.trim() === '11:00');
                if (els.length > 0) { els[0].click(); return true; }
                return false;
            }
        """)
        print(f"  Clicked: {clicked}")
        await page.wait_for_timeout(2000)
        await page.screenshot(path='/tmp/debug_3_after_time.png')

        # Show all visible buttons now
        btns = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button, div[class*="book"], [data-cy*="book"]'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({text: el.innerText.trim().substring(0,40), cy: el.getAttribute('data-cy'), cls: el.className.substring(0,40)}))
                .filter(b => b.text.length > 0)
        """)
        print(f"\n  Visible buttons after time select:")
        for b in btns:
            print(f"    '{b['text']}' data-cy={b['cy']} class={b['cls'][:30]}")

        print(f"\n[4] Clicking PROCEDI / bookVisit")
        # Try the exact selector from recording
        for sel in [
            "div.bookVisitContainer",
            "[data-cy='bookVisit']",
            "div.bookVisitContainer font",
            "button:has-text('PROCEDI')",
            "button:has-text('PROCEED')",
        ]:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    text = await el.inner_text()
                    print(f"  Found: '{text.strip()[:30]}' via {sel}")
                    await el.click()
                    await page.wait_for_timeout(5000)
                    print(f"  URL after click: {page.url}")
                    await page.screenshot(path='/tmp/debug_4_after_proceed.png')
                    break
            except Exception as e:
                print(f"  {sel}: {e}")

        # Check if checkout form appeared
        manager_form = await page.query_selector("[data-cy='managerSurname']")
        print(f"\n  managerSurname visible: {manager_form is not None}")
        if manager_form:
            print(f"  ✅ CHECKOUT FORM APPEARED!")
        else:
            # Show what's on page
            content = await page.content()
            print(f"  Page has 'checkout': {'checkout' in content.lower()}")
            print(f"  Page has 'manager': {'manager' in content.lower()}")
            print(f"  Page has 'surname': {'surname' in content.lower()}")

        await page.screenshot(path='/tmp/debug_5_final.png')
        print(f"\nScreenshots: /tmp/debug_*.png")
        await browser.close()

asyncio.run(debug())
