"""
Full Playwright flow — everything in ONE browser session:
search → timeavail → recap → checkout → Turnstile (native) → epay URL

No 2captcha needed. The browser solves Turnstile itself.
"""
import os, sys, django, asyncio
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.models import BuyerProfile, Agency
from datetime import datetime, timedelta

BASE = 'https://tickets.museivaticani.va'
VISITORS = 3
ADULTS = 2
KIDS = 1

agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
profile = BuyerProfile.objects.filter(agency=agency).first()
print(f"Profile: {profile.first_name} {profile.last_name} | {profile.email}")

async def run():
    from playwright.async_api import async_playwright
    import json, time

    H_XHR = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
        'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': f'{BASE}/',
    }
    HC = {k: v for k, v in H_XHR.items() if k != 'X-Requested-With'}
    HC['Referer'] = f'{BASE}/home/checkout'
    HC['Content-Type'] = 'application/json'

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled',
                  '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            locale='it-IT', timezone_id='Europe/Rome',
 NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 900},
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)
        page = await context.new_page()

        # ── Step 1: Search API in browser context ─────────────────────────────
        print("\n[1] Search API (in browser context)...")
        found = None
        for days in range(1, 120):
            d = (datetime.now() + timedelta(days=days)).strftime('%d/%m/%Y')
            resp = await page.request.get(f'{BASE}/api/search/resultPerTag', params={
                'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': d,
                'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
            }, headers=H_XHR)
            if resp.status != 200: continue
            data = await resp.json()
            ticket = next((v for v in data.get('visits', [])
                           if 'musei vaticani' in v.get('name','').lower()
                           and 'ingresso' in v.get('name','').lower()
                           and v.get('availability') in ('AVAILABLE','LOW_AVAILABILITY')), None)
            if not ticket: continue
            tid = ticket['id']
            r2 = await page.request.get(f'{BASE}/api/visit/timeavail', params={
                'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
ITORS), 'visitDate': d,
            }, headers=H_XHR)
            if r2.status != 200: continue
            d2 = await r2.json()
            slots = [sl for sl in d2.get('timetable', [])
                     if sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')]
            if slots:
                found = {'date': d, 'tid': tid, 'slot': slots[0]}
                break
            await asyncio.sleep(0.05)

        if not found:
            print("No available slots"); await browser.close(); return None

      date, tid, slot = found['date'], found['tid'], found['slot']
        slot_id, slot_time = str(slot['id']), slot['time']
        print(f"  Found: {date} {slot_time} (id={slot_id})")

        # ── Step 2: Recap in browser context ──────────────────────────────────
        print(f"\n[2] Recap (in browser context)...")
        recap_body = {
            "visitId": slot_id, "visitTypeId": int(tid),
            "visitorNum": VISITORS, "lang": "it",
            "tickets": [
                {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(ADULTS)},
                {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": str(KIDS)},
            ],
            "additionalCosts": {"service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": VISITORS}},
            "services": [{"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": VISITORS}],
        }
        rr = await page.request.post(f'{BASE}/api/visit/recap',
            data=json.dumps(recap_body), headers=HC)
        if rr.status != 200:
            print(f"  Recap failed: {rr.status}"); await browser.close(); return None
        rd = await rr.json()
        recap_id = rd.get('recapId','')
        total = rd.get('total', 0)
        print(f"  ✅ Recap: {recap_id} | €{total}")
        print(f"  Slot locked in browser session")

        # ── Step 3: Navigate to checkout ──────────────────────────────────────
        print(f"\n[3] Navigating to checkout page...")
        epay_url = None
        reservation_data = None

        async def on_response(response):
            nonlocal epay_url, reservation_data
            if '/api/visit/reservation' in response.url:
                try:
                    data = await response.json()
                    print(f"\n  🎯 Reservation: HTTP {response.status}")
                    if response.status == 200:
                        reservation_data = data
                        epay = data.get('epay', {})
                        epay_url = epay.get('url','')
print(f"  reference: {data.get('referenceOrder')}")
                        print(f"  epay.url: {epay_url}")
                        print(f"  mac_avvio: {epay.get('mac_avvio','')[:20]}...")
                    else:
                        print(f"  Failed: {data}")
                except Exception as e:
                    print(f"  Response parse error: {e}")

        page.on('response', on_response)

        await page.goto(f'{BASE}/home/checkout', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)

        url_now = page.url
        title = await page.title()
        print(f"  URL: {url_now}")
        print(f"  Title: {title}")

        if '/home/checkout' not in url_now:
            print(f"  ⚠️  Redirected away from checkout — Vatican may require page navigation")
            # Try navigating via the Vatican UI instead
            print(f"  Trying direct navigation via Vatican UI...")
            await page.goto(f'{BASE}/home', wait_until='
            await page.wait_for_timeout(2000)
            # Try to click through to checkout
            await page.goto(f'{BASE}/home/checkout', wait_until='domcontentloaded', timeout=20000)
            await page.wait_for_timeout(2000)
            url_now = page.url
            print(f"  URL after retry: {url_now}")

        # Check page content
        content = await page.content()
        on_checkout = '/home/checkout' in url_now
        has_turnstile = 'lower()
        print(f"  On checkout: {on_checkout} | Has Turnstile: {has_turnstile}")

        if not on_checkout:
            print(f"\n  Vatican redirected to home — session cart not preserved")
            print(f"  The recap session cookie alone is not enough")
            print(f"  Vatican likely needs the full Angular app state (not just JSESSIONID)")
            await page.screenshot(path='/tmp/pw_checkout.png')
            print(f"  Screenshot: /tmp/pw_checkout.png")
            await browser.close()
            return None

        # ── Step 4: Fill form ─────────────────────────────────────────────────
        print(f"\n[4] Filling form...")
        fields = [
            ('[name="name"]', profile.first_name),
            ('[name="surname"]', profile.last_name),
            ('[name="email"]', profile.email),
            ('[name="confirmEmail"]', profile.email),
            ('[name="telephoneNumber"]', profile.phone),
        ]
        filled = 0
        for sel, val in fields:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.fill(str(val))
                    filled += 1
            except Exception:
                pass
        print(f"  Filled {filled} fields")

        # GDPR checkboxes
        try:
            cbs = await page.query_selector_all('input[type="checkbox"]')
            for cb in cbs:
                if not await cb.is_checked():
                    await cb.check()
        except Exception:
            pass

        # ── Step 5: Wait for Turnstile ────────────────────────────────────────
        print(f"\n[5] Waiting for Turnstile (up to 90s)...")
        for i in range(90):
            await asyncio.sleep(1)
            try:
                token_val = await page.evaluate(
                    "() => { const i = document.querySelector('input[name=\"cf-turnstile-response\"]'); return i ? i.value : ''; }"
                )
                if token_val and len(token_val) > 100:
                    print(f✅ Turnstile solved! prefix={token_val[:4]} len={len(token_val)}")
                    break
                if i % 15 == 0 and i > 0:
                    print(f"  ... {i}s")
            except Exception:
                pass
        else:
            print(f"  ⚠️  Turnstile timeout — submitting anyway")

        # ── Step 6: Submit ────────────────────────────────────────────────────
        print(f"\n[6] Submitting...")
        for sel in ['button[type="submit"]', 'button:has-text("Procedi")',
                    'button:has-text("Conferma")', '.btn-primary']:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    print(f"  Clicking: {sel}")
                    await btn.click()
                    break
            except Exception:
                pass

        await page.wait_for_timeout(15000)

        if not epay_url:
            final_url = page.url
            print(f"  Final URL: {final_url}")
            await page.screehot(path='/tmp/pw_final.png')
            print(f"  Screenshot: /tmp/pw_final.png")

        await browser.close()
        return epay_url, reservation_data

result = asyncio.run(run())

print(f"\n{'='*60}")
if result and result[0]:
    epay_url, res_data = result
    print(f"✅ OPEN THIS TO PAY:")
    print(f"\n  {epay_url}\n")
    if res_data:
        epay = res_data.get('epay', {})
        print(f"Reference: {res_data.get('referenceOrder')}")
        print(f"mac_avvio: {epay.get('mac_avvio','')}")
else:
    print(f"❌ No epay URL — Vatican requires full browser session for checkout")
    print(f"   The recap API call must happen in the same browser that does checkout")
    print(f"   Solution: do search+recap+checkout all in one Playwright session (this script)")
print(f"{'='*60}")
