"""
Full Playwright flow — recap + checkout in ONE browser session.
Uses page.request for API calls so cookies are shared with the browser.
"""
import os, sys, django, asyncio, json
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import BuyerProfile, Agency
from datetime import datetime, timedelta

BASE = 'https://tickets.museivaticani.va'
VISITORS = 1

agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
profile = BuyerProfile.objects.filter(agency=agency).first()
print(f"Profile: {profile.first_name} {profile.last_name}")

async def run():
    from playwright.async_api import async_playwright

    H = {'Accept': 'application/json, text/plain, */*',
         'Accept-Language': 'it-IT,it;q=0.9',
         'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors',
         'sec-fetch-site': 'same-origin', 'Origin': BASE}
    H_XHR = {**H, 'X-Requested-With': 'XMLHttpRequest', 'Referer': f'{BASE}/'}
    HC = {**H, 'Referer': f'{BASE}/home/checkout', 'Content-Type': 'application/json'}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled', '--disable-dev-shm-usage']
        )
        ctx = await browser.new_context(
            locale='it-IT', timezone_id='Europe/Rome',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 900},
        )
        await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});window.chrome={runtime:{}};")
        page = await ctx.new_page()

        # ── 1. Search via page.request (shares browser cookies) ───────────────
        print("\n[1] Search API via browser context...")
        found = None
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
                found = {'date':d,'tid':tid,'slot':slots[0]}
                break
            await asyncio.sleep(0.05)

        if not found:
            print("No slots"); await browser.close(); return None

        date, tid, slot = found['date'], found['tid'], found['slot']
        slot_id, slot_time = str(slot['id']), slot['time']
        print(f"  Found: {date} {slot_time} (id={slot_id})")

        # ── 2. Recap via page.request ─────────────────────────────────────────
        print(f"\n[2] Recap via browser context...")
        recap_body = {
            "visitId": slot_id, "visitTypeId": int(tid), "visitorNum": VISITORS, "lang": "it",
            "tickets": [
                {"id":60,"name":"Biglietto Intero","price":20,"quantity":str(VISITORS)},
                {"id":61,"name":"Biglietto Ridotto","price":10,"quantity":0},
            ],
            "additionalCosts": {"service-0":{"id":58,"name":"Diritti di Prevendita","price":5,"quantity":VISITORS}},
            "services": [{"id":58,"name":"Diritti di Prevendita","price":5,"quantity":VISITORS}],
        }
        rr = await page.request.post(f'{BASE}/api/visit/recap',
            data=json.dumps(recap_body), headers=HC)
        if rr.status != 200:
            print(f"  Recap failed: {rr.status}"); await browser.close(); return None
        rd = await rr.json()
        recap_id = rd.get('recapId','')
        total = rd.get('total',0)
        print(f"  ✅ recapId={recap_id} €{total}")

        # Check cookies in browser context
        cookies = await ctx.cookies()
        jsid = next((c['value'] for c in cookies if c['name']=='JSESSIONID'), '')
        print(f"  Browser JSESSIONID: {jsid[:25]}...")

        # ── 3. Navigate to checkout ───────────────────────────────────────────
        print(f"\n[3] Navigating to /home/checkout...")
        epay_url = None
        res_data = None

        async def on_resp(response):
            nonlocal epay_url, res_data
            if '/api/visit/reservation' in response.url:
                try:
                    data = await response.json()
                    print(f"\n  🎯 Reservation HTTP {response.status}")
                    if response.status == 200:
                        res_data = data
                        epay_url = data.get('epay',{}).get('url','')
                        print(f"  ref={data.get('referenceOrder')} epay={epay_url[:60]}")
                    else:
                        print(f"  Failed: {data}")
                except Exception as e:
                    print(f"  Parse error: {e}")

        page.on('response', on_resp)

        await page.goto(f'{BASE}/home/checkout', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)

        url_now = page.url
        print(f"  URL: {url_now}")

        if '/home/checkout' not in url_now:
            print(f"\n  ⚠️  Redirected to {url_now}")
            print(f"  Vatican Angular app requires UI navigation, not direct URL")
            print(f"\n  Trying to navigate through the UI...")

            # Go to home first, then try to reach checkout via Angular routing
            await page.goto(f'{BASE}/home', wait_until='networkidle', timeout=20000)
            await page.wait_for_timeout(2000)

            # Try clicking through the booking flow
            # Vatican's Angular app may need the user to go through the flow
            # Let's check what's on the home page
            content = await page.content()
            print(f"  Home page loaded, checking for booking entry...")

            # Look for any link/button to start booking
            btns = await page.query_selector_all('a[href*="visit"], button:has-text("Biglietti"), a:has-text("Acquista")')
            print(f"  Found {len(btns)} booking-related elements")
            for btn in btns[:3]:
                try:
                    text = await btn.inner_text()
                    href = await btn.get_attribute('href')
                    print(f"    '{text.strip()[:30]}' href={href}")
                except Exception:
                    pass

            await page.screenshot(path='/tmp/pw_home.png')
            print(f"  Screenshot: /tmp/pw_home.png")
            await browser.close()
            return None

        # ── 4. Fill form ──────────────────────────────────────────────────────
        print(f"\n[4] Filling form...")
        content = await page.content()
        print(f"  Has Turnstile: {'turnstile' in content.lower()}")
        print(f"  Has form fields: {'name' in content.lower()}")

        for sel, val in [
            ('[name="name"]', profile.first_name),
            ('[name="surname"]', profile.last_name),
            ('[name="email"]', profile.email),
            ('[name="confirmEmail"]', profile.email),
            ('[name="telephoneNumber"]', profile.phone),
        ]:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.fill(str(val))
            except Exception:
                pass

        try:
            for cb in await page.query_selector_all('input[type="checkbox"]'):
                if not await cb.is_checked():
                    await cb.check()
        except Exception:
            pass

        # ── 5. Wait for Turnstile ─────────────────────────────────────────────
        print(f"\n[5] Waiting for Turnstile (90s)...")
        for i in range(90):
            await asyncio.sleep(1)
            try:
                val = await page.evaluate(
                    "()=>{const i=document.querySelector('input[name=\"cf-turnstile-response\"]');return i?i.value:'';}"
                )
                if val and len(val) > 100:
                    print(f"  ✅ Turnstile solved! prefix={val[:4]} len={len(val)}")
                    break
                if i % 20 == 0 and i > 0:
                    print(f"  ... {i}s")
            except Exception:
                pass
        else:
            print(f"  ⚠️  Timeout")

        # ── 6. Submit ─────────────────────────────────────────────────────────
        print(f"\n[6] Submitting...")
        for sel in ['button[type="submit"]','button:has-text("Procedi")','button:has-text("Conferma")']:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    print(f"  Clicking {sel}")
                    await btn.click()
                    break
            except Exception:
                pass

        await page.wait_for_timeout(15000)
        await page.screenshot(path='/tmp/pw_result.png')
        print(f"  Screenshot: /tmp/pw_result.png")

        await browser.close()
        return epay_url, res_data

result = asyncio.run(run())

print(f"\n{'='*60}")
if result and result[0]:
    print(f"✅ OPEN TO PAY: {result[0]}")
else:
    print(f"❌ No epay URL")
    print(f"Vatican requires the full Angular UI flow for checkout.")
    print(f"The recap API alone doesn't set the Angular app state.")
print(f"{'='*60}")
