#!/usr/bin/env python3
"""Playwright-based auto-booker — proper iframe/checkbox handling."""
import asyncio, sys, os, time, json, random, requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

VATICAN = "https://tickets.museivaticani.va"
PROXY_USER = os.getenv("OXYLABS_USERNAME", "")
PROXY_PASS = os.getenv("OXYLABS_PASSWORD", "")
PROXY_HOST = os.getenv("OXYLABS_HOST", "isp.oxylabs.io")
PROXY_PORTS = [8001,8002,8003,8004,8005,8006,8007,8008,8009,8010,8011,8012,8013]
H = {"Accept":"application/json","X-Requested-With":"XMLHttpRequest","User-Agent":"Mozilla/5.0 Chrome/136.0.0.0 Safari/537.36","Referer":f"{VATICAN}/","Origin":VATICAN}

def log(msg): print(f"[{datetime.now():%H:%M:%S}] {msg}")
def get_proxy():
    port = random.choice(PROXY_PORTS)
    return f"{PROXY_HOST}:{port}"

def find_slot(date_str, visitors=2):
    host = get_proxy()
    s = requests.Session()
    proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{host}"
    s.proxies = {"http": proxy_url, "https": proxy_url}
    s.headers.update(H)
    try: s.get(f"{VATICAN}/home", timeout=10)
    except: pass
    r = s.get(f"{VATICAN}/api/search/resultPerTag", params=dict(lang="it",visitorNum=str(visitors),visitDate=date_str,area="1",who="",page="0",tag="MV-Biglietti"), timeout=10)
    if r.status_code!=200: return None
    visits = r.json().get("visits",[])
    EX = ['pellegrinaggi','lunch','pranzo','gruppi','specola','palazzo','didattiche']
    v = next((x for x in visits if "musei vaticani" in x.get("name","").lower() and "ingresso" in x.get("name","").lower() and not any(e in x.get("name","").lower() for e in EX) and x.get("availability")=="AVAILABLE"), None)
    if not v: return None
    tid = str(v["id"])
    r2 = s.get(f"{VATICAN}/api/visit/timeavail", params=dict(lang="it",visitLang="",visitTypeId=tid,visitorNum=str(visitors),visitDate=date_str), timeout=10)
    if r2.status_code!=200: return None
    slots = [x for x in r2.json().get("timetable",[]) if x.get("availability")=="AVAILABLE"]
    if not slots: return None
    log(f"Found: {date_str} {slots[0]['time']}")
    return dict(date=date_str, slot_id=str(slots[0]['id']), slot_time=slots[0]['time'], ticket_id=tid, visitors=visitors)

async def book(slot):
    port = random.choice(PROXY_PORTS)
    proxy = {"server": f"http://{PROXY_HOST}:{port}", "username": PROXY_USER, "password": PROXY_PASS}
    log(f"  Proxy: {PROXY_HOST}:{port}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, proxy=proxy, args=['--no-sandbox','--disable-dev-shm-usage','--window-size=1005,572'])
        page = await browser.new_page(viewport={"width":1005,"height":572})

        v=slot['visitors']; date=slot['date']; stime=slot['slot_time']; tid=slot['ticket_id']
        rome=ZoneInfo('Europe/Rome'); d,m,y=date.split('/')
        ts = int(datetime(int(y),int(m),int(d),0,0,0,tzinfo=rome).timestamp()*1000)
        url = f"{VATICAN}/home/fromtag/{v}/{ts}/MV-Biglietti/1"

        log(f"Booking: {date} {stime} ({v}v)")

        try:
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_selector("[data-cy^='bookTicket_']", timeout=15000)
            await asyncio.sleep(2)

            # Click Vatican ticket
            cards = await page.query_selector_all('[id^="ticket_"]')
            for card in cards:
                text = (await card.inner_text()).lower()
                if 'musei vaticani' in text and ('ingresso' in text or 'biglietti' in text):
                    btn = await card.query_selector('[data-cy^="bookTicket_"]')
                    if btn: await btn.click(); break
            await asyncio.sleep(2)

            # Quantity
            await page.click("[data-cy='ticketQuantity']")
            await asyncio.sleep(0.5)
            opts = await page.query_selector_all("[data-cy='ticketQuantitySection']")
            if len(opts)>=2: await opts[1].click()
            await asyncio.sleep(1)

            # Time slot
            cells = await page.query_selector_all("[data-cy='time']")
            for cell in cells:
                txt = (await cell.inner_text()).strip()
                if 'ESAURITI' in txt or 'SOLD' in txt: continue
                if stime in txt: await cell.click(); break
            await asyncio.sleep(1.5)

            # PROCEDI
            await page.click("[data-cy='bookVisit']")
            await page.wait_for_url("**/checkout", timeout=20000)
            log("  On checkout")

            # Fill form quickly
            fields = {
                "[data-cy='managerSurname']":"Rossi","[data-cy='managerName']":"Mario",
                "[data-cy='managerEmail']":"mario@test.it","[data-cy='managerConfirmEmail']":"mario@test.it",
                "[data-cy='managerPhone']":"3401234567","[data-cy='managerCity']":"Roma",
            }
            for sel, val in fields.items():
                await page.fill(sel, val)
            await page.click("[data-cy='managerSex']"); await asyncio.sleep(0.2)
            await page.click("[data-cy='managerSexSection']"); await asyncio.sleep(0.2)
            await page.click("[data-cy='managerCountry']"); await asyncio.sleep(0.2)
            await page.fill("#searchInput_country", "Italia"); await asyncio.sleep(0.3)
            await page.click("[data-cy='managerCountrySection']"); await asyncio.sleep(0.2)
            await page.click("[data-cy='managerLanguage']"); await asyncio.sleep(0.2)
            await page.click("[data-cy='managerLanguageSection']"); await asyncio.sleep(0.2)
            # Participants
            await page.fill("#participantSurname_0", "Rossi")
            await page.fill("#participantName_0", "Mario")
            await page.fill("#participantSurname_1", "Bianchi")
            await page.fill("#participantName_1", "Sofia")
            log("  Form filled")

            # GDPR checkbox — try multiple known IDs
            for cbid in ["#mat-mdc-checkbox-0-input","#mat-mdc-checkbox-1-input","#mat-mdc-checkbox-2-input",
                         "input[id^='mat-mdc-checkbox'][type='checkbox']"]:
                try:
                    await page.click(cbid, timeout=3000)
                    log(f"  Checkbox: {cbid}")
                    break
                except: continue
            await asyncio.sleep(1.5)
            try: await page.click("[data-cy='purchase-rules-close-btn']", timeout=3000)
            except: pass
            await asyncio.sleep(1)

            # === PLAYWRIGHT TURNSTILE: find iframe and click checkbox ===
            log("  Turnstile: looking for iframe...")
            ts_frame = None
            for i in range(30):
                frames = page.frames
                for f in frames:
                    if 'challenges.cloudflare.com' in (f.url or ''):
                        ts_frame = f
                        break
                if ts_frame: break
                await asyncio.sleep(1)

            if ts_frame:
                log(f"  Iframe found: {ts_frame.url[:80]}")
                # Cross-origin iframe — can't use locator, use JS to get box + mouse.click
                box = await page.evaluate("""()=>{
                    var f=document.querySelector('iframe[src*="challenges.cloudflare"]');
                    if(!f) return null;
                    var r=f.getBoundingClientRect();
                    return {x:r.x,y:r.y,w:r.width,h:r.height};
                }""")
                if box:
                    log(f"  Iframe at {box['x']:.0f},{box['y']:.0f} ({box['w']:.0f}x{box['h']:.0f})")
                    # Click checkbox (left side of iframe, ~25px from left, ~33px from top)
                    for round_num in range(5):
                        for ox, oy in [(25,33),(22,30),(28,35),(20,32),(25,28),(23,35),(27,30)]:
                            await page.mouse.click(box['x']+ox, box['y']+oy)
                            await asyncio.sleep(0.1)
                        token = await page.evaluate("""()=>{var i=document.querySelector('input[name="cf-turnstile-response"]');return i&&i.value&&i.value.length>10;}""")
                        if token: log(f"  ✅ Solved round {round_num+1}!"); break
                        await asyncio.sleep(0.3)
                    else:
                        log("  Waiting for auto-solve...")
                        for _ in range(30):
                            token = await page.evaluate("""()=>{var i=document.querySelector('input[name="cf-turnstile-response"]');return i&&i.value&&i.value.length>10;}""")
                            if token: log("  ✅ Solved!"); break
                            await asyncio.sleep(0.5)
            else:
                log("  No Turnstile iframe")
                await asyncio.sleep(5)

            # ACQUISTA
            await page.click("[data-cy='buyButton']")
            log("  ACQUISTA clicked")
            await asyncio.sleep(3)

            # Wait for epay
            for _ in range(60):
                url = page.url
                if 'epay.catholica.va' in url:
                    log(f"🎉 {url}")
                    return {'success':True,'epay_url':url,'slot':slot}
                await asyncio.sleep(0.5)

            return {'success':False,'slot':slot,'error':'no epay'}

        except Exception as e:
            log(f"Error: {e}")
            import traceback; traceback.print_exc()
            return {'success':False,'error':str(e)}
        finally:
            await browser.close()

async def main():
    import argparse; p=argparse.ArgumentParser()
    p.add_argument('--date',default=None); p.add_argument('--visitors',type=int,default=2)
    args=p.parse_args()
    slot = find_slot(args.date or (datetime.now()+timedelta(days=30)).strftime('%d/%m/%Y'), args.visitors)
    if not slot: log("No slots"); return
    r = await book(slot)
    print(json.dumps({'success':r.get('success'),'epay':r.get('epay_url','')[:150]}))

if __name__=='__main__': asyncio.run(main())
