"""Debug: find and click POMERIGGIO tab to reveal afternoon slots"""
import os, sys, django, asyncio
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import BuyerProfile, Agency
from datetime import datetime
from zoneinfo import ZoneInfo

BASE = 'https://tickets.museivaticani.va'
DATE = '05/05/2026'
SLOT_TIME = '16:30'
VISITORS = 1

agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()

async def debug():
    from playwright.async_api import async_playwright

    rome = ZoneInfo('Europe/Rome')
    day, month, year = DATE.split('/')
    dt = datetime(int(year), int(month), int(day), 0, 0, 0, tzinfo=rome)
    ts = int(dt.timestamp() * 1000)
    entry_url = f'{BASE}/home/fromtag/{VISITORS}/{ts}/MV-Biglietti/1'
    H_XHR = {'Accept':'application/json','X-Requested-With':'XMLHttpRequest','Referer':f'{BASE}/'}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
        ctx = await browser.new_context(
            locale='it-IT', timezone_id='Europe/Rome',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            viewport={'width': 828, 'height': 915},
        )
        await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        page = await ctx.new_page()

        await page.goto(entry_url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(2000)

        r = await page.request.get(f'{BASE}/api/search/resultPerTag',
            params={'lang':'it','visitorNum':str(VISITORS),'visitDate':DATE,'area':'1','who':'','page':'0','tag':'MV-Biglietti'},
            headers=H_XHR)
        visits = (await r.json()).get('visits', [])
        ticket = next((v for v in visits if 'musei vaticani' in v.get('name','').lower() and 'ingresso' in v.get('name','').lower()), None)
        if not ticket: print("No ticket"); await browser.close(); return
        tid = str(ticket['id'])

        # Full flow: bookTicket → quantity → check tabs
        await page.click(f"[data-cy='bookTicket_{tid}']")
        await page.wait_for_timeout(1500)
        qty = await page.query_selector("[data-cy='ticketQuantity']")
        if qty: await qty.click(); await page.wait_for_timeout(300)
        qty_sec = await page.query_selector("[data-cy='ticketQuantitySection']")
        if qty_sec: await qty_sec.click(); await page.wait_for_timeout(500)

        # Find all tabs in the time table
        tabs = await page.evaluate("""
            () => Array.from(document.querySelectorAll('.tab, .timeTabContainer .tab, div.tab'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({
                    text: el.innerText.trim(),
                    cls: el.className,
                    selected: el.className.includes('selected')
                }))
        """)
        print(f"Tabs found: {tabs}")

        # Click POMERIGGIO tab
        clicked = await page.evaluate("""
            () => {
                // Find tab with POMERIGGIO text
                const tabs = Array.from(document.querySelectorAll('.tab, div.tab, .timeTabContainer div'))
                    .filter(el => el.offsetParent !== null);
                for (const tab of tabs) {
                    const text = tab.innerText.trim().toUpperCase();
                    if (text.includes('POMERIGGIO') || text.includes('AFTERNOON') || text.includes('PM')) {
                        tab.click();
                        return `clicked: ${tab.innerText.trim()}`;
                    }
                }
                // Try clicking 2nd tab
                const allTabs = Array.from(document.querySelectorAll('.tab'))
                    .filter(el => el.offsetParent !== null);
                if (allTabs.length >= 2) {
                    allTabs[1].click();
                    return `clicked 2nd tab: ${allTabs[1].innerText.trim()}`;
                }
                return 'no tab found';
            }
        """)
        print(f"Tab click result: {clicked}")
        await page.wait_for_timeout(1500)

        # Check times after tab click
        times = await page.evaluate("""
            () => Array.from(document.querySelectorAll("[data-cy='time'] div.muvaCalendarNumber, [data-cy='time'] div.muvaCalendarDaySoldOut"))
                .map(el => ({text: el.innerText.trim(), cls: el.className, parent: el.parentElement.className}))
                .filter(t => /^\\d{2}:\\d{2}$/.test(t.text))
        """)
        print(f"\nTimes after tab click ({len(times)}):")
        for t in times:
            marker = " ← TARGET" if t['text'] == SLOT_TIME else ""
            print(f"  {t['text']} | cls={t['cls'][:20]} | parent={t['parent'][:30]}{marker}")

        # Get full tab container HTML for analysis
        tab_html = await page.evaluate("""
            () => {
                const c = document.querySelector('.timeTabContainer, .showGTMobile');
                return c ? c.innerHTML.substring(0, 800) : 'not found';
            }
        """)
        print(f"\nTab container HTML:\n{tab_html[:600]}")

        await page.screenshot(path='/tmp/afternoon_tabs.png')
        print(f"\nScreenshot: /tmp/afternoon_tabs.png")
        await browser.close()

asyncio.run(debug())
