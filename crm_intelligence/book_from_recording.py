#!/usr/bin/env python3
"""
Auto-booker based on Chrome DevTools recording (formfilling.json).
Flow: navigate→ticket→quantity→time→PROCEDI→form→checkbox→ACQUISTA→epay.
NO recap API. Uses the exact selectors from the successful recording.
"""
import asyncio, sys, os, time, json, warnings, requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")
VATICAN = "https://tickets.museivaticani.va"
PROFILE = os.path.expanduser("~/.vatican_chrome_profile")
# Oxylabs residential proxies (Italian IPs — bypasses Cloudflare)
OXYLABS_USER = os.getenv("OXYLABS_USERNAME", "")
OXYLABS_PASS = os.getenv("OXYLABS_PASSWORD", "")
OXYLABS_HOST = os.getenv("OXYLABS_HOST", "isp.oxylabs.io")
OXYLABS_PORTS = [8001,8002,8003,8004,8005,8006,8007,8008,8009,8010,8011,8012,8013]
import random
def get_proxy():
    port = random.choice(OXYLABS_PORTS)
    return f"http://{OXYLABS_USER}:{OXYLABS_PASS}@{OXYLABS_HOST}:{port}"

H = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest",
     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36",
     "Referer": f"{VATICAN}/", "Origin": VATICAN}

def log(msg): print(f"[{datetime.now():%H:%M:%S}] {msg}")

# Buyer data (from recording)
BUYER = dict(
    surname="skear", name="abiilesh", email="your-email@example.com",
    phone="your-phone-number", city="roma"
)

def find_slot(date_str, visitors=2):
    proxy = get_proxy()
    s = requests.Session()
    s.proxies = {"http": proxy, "https": proxy}
    s.headers.update(H)
    try: s.get(f"{VATICAN}/home", timeout=8)
    except: pass
    EXCLUDED = ['pellegrinaggi','lunch','pranzo','gruppi','specola','palazzo','didattiche']
    r = s.get(f"{VATICAN}/api/search/resultPerTag", params=dict(
        lang="it", visitorNum=str(visitors), visitDate=date_str, area="1", who="", page="0", tag="MV-Biglietti"), timeout=8)
    if r.status_code!=200: return None
    visits = r.json().get("visits",[])
    ticket = next((v for v in visits if "musei vaticani" in v.get("name","").lower()
                  and "ingresso" in v.get("name","").lower()
                  and not any(x in v.get("name","").lower() for x in EXCLUDED)
                  and v.get("availability")=="AVAILABLE"), None)
    if not ticket: return None
    tid = str(ticket["id"])
    r2 = s.get(f"{VATICAN}/api/visit/timeavail", params=dict(
        lang="it", visitLang="", visitTypeId=tid, visitorNum=str(visitors), visitDate=date_str), timeout=8)
    if r2.status_code!=200: return None
    slots = [sl for sl in r2.json().get("timetable",[]) if sl.get("availability")=="AVAILABLE"]
    if not slots: return None
    best = slots[0]
    log(f"Found: {date_str} {best['time']} (id={best['id']})")
    return dict(date=date_str, slot_id=str(best['id']), slot_time=best['time'], ticket_id=tid, visitors=visitors)

async def book(slot):
    import nodriver as uc
    v=slot['visitors']; date=slot['date']; stime=slot['slot_time']; tid=slot['ticket_id']
    rome=ZoneInfo('Europe/Rome'); d,m,y=date.split('/')
    ts = int(datetime(int(y),int(m),int(d),0,0,0,tzinfo=rome).timestamp()*1000)
    url = f"{VATICAN}/home/fromtag/{v}/{ts}/MV-Biglietti/1"

    log(f"Booking: {date} {stime} ({v}v)")
    for lf in ['lockfile','SingletonLock','SingletonCookie']:
        try: os.remove(os.path.join(PROFILE, lf))
        except: pass

    proxy = get_proxy()
    log(f"  Proxy: {proxy.split('@')[1] if '@' in proxy else proxy}")

    browser = await uc.start(
        user_data_dir=PROFILE,
        headless=False,
        lang="it-IT",
        no_sandbox=True,
        window_size=(1005, 572),
        browser_args=[
            f'--proxy-server={proxy}',
            '--disable-features=AutomationControlled',
            '--disable-blink-features=AutomationControlled',
            '--disable-infobars',
            '--disable-breakpad',
            '--disable-dev-shm-usage',
            '--disable-session-crashed-bubble',
            '--disable-search-engine-choice-screen',
        ],
    )
    tab = browser.main_tab

    # Note: touch emulation disabled - mouse clicks work better
    # Cloudflare treats touch events from desktop as suspicious

    try:
        # ── NAVIGATE ──────────────────────────────────────────
        await tab.get(url)
        await tab.sleep(4)
        # Wait for tickets
        for _ in range(30):
            count = await tab.evaluate("""document.querySelectorAll("[data-cy^='bookTicket_']").length""")
            if count and int(count)>0: break
            await tab.sleep(0.5)
        log(f"  Tickets: {count}")

        # ── CLICK VATICAN TICKET ──────────────────────────────
        tid_from_dom = await tab.evaluate("""(()=>{var cards=Array.from(document.querySelectorAll('[id^="ticket_"]'));
            for(var c of cards){if(c.innerText.toLowerCase().includes('musei vaticani')){
            var btn=c.querySelector('[data-cy^="bookTicket_"]');if(btn)return btn.getAttribute('data-cy').replace('bookTicket_','');}}
            return null;})()""")
        # Unwrap nodriver type annotation
        if isinstance(tid_from_dom, list) and len(tid_from_dom) > 0:
            tid_from_dom = tid_from_dom[0][1].get('value') if isinstance(tid_from_dom[0], list) and len(tid_from_dom[0]) > 1 else None
        log(f"  Ticket ID: {tid_from_dom}")
        if tid_from_dom:
            ticket_btn = await tab.query_selector('[data-cy="bookTicket_' + str(tid_from_dom) + '"]')
            if ticket_btn: await ticket_btn.click()
        await tab.sleep(3)

        # ── QUANTITY (nodriver clicks) ────────────────────────
        qty = await tab.query_selector("[data-cy='ticketQuantity']")
        if qty: await qty.click()
        await tab.sleep(1)
        opts = await tab.query_selector_all("[data-cy='ticketQuantitySection']")
        if len(opts) >= 2: await opts[1].click()
        await tab.sleep(2)

        # ── TIME SLOT: switch tab if needed, find visible cell, nodriver click ─
        log(f"  Time: {stime}")
        target_hour = int(stime.split(':')[0]) if ':' in stime else 0
        # Switch to afternoon tab if needed
        if target_hour >= 14:
            await tab.evaluate("""(()=>{
                var tabs=Array.from(document.querySelectorAll('.tab, [role="tab"], button[class*="tab"]'))
                    .filter(function(el){return el.offsetParent!==null});
                var a=tabs.find(function(t){return /pomeriggio/i.test(t.innerText)});
                if(a)a.click();else if(tabs.length>=2)tabs[1].click();
            })()""")
            await tab.sleep(1)

        # Find index among VISIBLE non-sold-out cells
        time_idx = await tab.evaluate(f"""(function(){{
            var cells=document.querySelectorAll("[data-cy='time']");
            for(var i=0;i<cells.length;i++){{
                var c=cells[i];if(c.offsetParent===null)continue;
                var t=c.innerText.trim();
                if(t.indexOf('ESAURITI')>-1||t.indexOf('SOLD')>-1)continue;
                if(t.indexOf('{stime}')>-1)return i;
            }}
            for(var i=0;i<cells.length;i++){{
                var c=cells[i];if(c.offsetParent===null)continue;
                var t=c.innerText.trim();
                if(!(t.indexOf('ESAURITI')>-1||t.indexOf('SOLD')>-1))return i;
            }}
            return -1;
        }})()""")
        if isinstance(time_idx, list):
            time_idx = time_idx[0][1].get('value') if time_idx and len(time_idx)>0 and len(time_idx[0])>1 else -1

        log(f"  Target idx={time_idx}")
        if time_idx >= 0:
            cells = await tab.query_selector_all("[data-cy='time']")
            if time_idx < len(cells):
                await cells[time_idx].scroll_into_view()
                await tab.sleep(0.3)
                await cells[time_idx].click()
        await tab.sleep(2)

        # ── PROCEDI (nodriver click) ──────────────────────────
        procedi = await tab.query_selector("[data-cy='bookVisit']")
        if procedi: await procedi.click()
        await tab.sleep(6)

        # Check URL
        cur = await tab.evaluate("window.location.href")
        log(f"  URL: {cur}")
        if 'checkout' not in str(cur):
            log("ERROR: Not on checkout!"); return {'success':False}

        # ── MOVE MOUSE LIKE A HUMAN ──────────────────────────
        # Do some random mouse movements before filling to look human
        await tab.evaluate("""(()=>{
            var evts=[];
            var x=300+Math.random()*400, y=200+Math.random()*300;
            for(var i=0;i<5;i++){
                x+=Math.random()*200-100; y+=Math.random()*150-75;
                var el=document.elementFromPoint(x,y);
                if(el)el.dispatchEvent(new MouseEvent('mousemove',{bubbles:true,clientX:x,clientY:y}));
            }
        })()""")
        await tab.sleep(0.5)

        # ── FILL FORM FIRST (triggers Turnstile widget to render) ──
        log("Filling form...")

        # Helper: fill input via focus + execCommand
        async def fill_input(sel, val):
            js = """(()=>{var el=document.querySelector(\"""" + sel + """\");
                if(!el)return;el.focus();el.select();
                document.execCommand('selectAll',false,null);
                document.execCommand('insertText',false,\"""" + str(val) + """\");
                el.dispatchEvent(new Event('input',{bubbles:true}));
                el.dispatchEvent(new Event('change',{bubbles:true}));
                el.dispatchEvent(new Event('blur',{bubbles:true}));})()"""
            await tab.evaluate(js)
            await tab.sleep(0.15)

        await fill_input("[data-cy='managerSurname']", BUYER['surname'])
        await fill_input("[data-cy='managerName']", BUYER['name'])

        # Gender: click to open, click first option
        await tab.evaluate("""document.querySelector("[data-cy='managerSex']")?.click()""")
        await tab.sleep(0.3)
        await tab.evaluate("""document.querySelector("[data-cy='managerSexSection']")?.click()""")
        await tab.sleep(0.3)

        # Country: click to open, search Italia, select it
        await tab.evaluate("""document.querySelector("[data-cy='managerCountry']")?.click()""")
        await tab.sleep(0.3)
        await tab.evaluate("""(()=>{
            var s=document.querySelector('#searchInput_country');
            if(s){s.value='Italia';s.dispatchEvent(new Event('input',{bubbles:true}));}
        })()""")
        await tab.sleep(0.4)
        await tab.evaluate("""(()=>{
            var items=Array.from(document.querySelectorAll("[data-cy='managerCountrySection']"));
            for(var i=0;i<items.length;i++){
                if(/^ital/i.test(items[i].innerText.trim())){items[i].click();return;}
            }
            // fallback: click span in first
            var span=document.querySelector("[data-cy='managerCountrySection'] span");
            if(span)span.click();
        })()""")
        await tab.sleep(0.3)

        await fill_input("[data-cy='managerCity']", BUYER['city'])

        # Birth date - click calendar, select year/month/day
        await tab.evaluate("""document.querySelector("[data-cy='dateCalendar']")?.click()""")
        await tab.sleep(1)
        # Year: click 5th row, 1st cell (2001 in recording)
        await tab.evaluate("""(()=>{var cell=document.querySelector('tr:nth-of-type(5) > td:nth-of-type(1) span.mat-calendar-body-cell-content');
            if(cell)cell.click();})()""")
        await tab.sleep(0.5)
        # Month: click 3rd row, 1st cell (MAY in recording)
        await tab.evaluate("""(()=>{var cell=document.querySelector('tr:nth-of-type(3) > td:nth-of-type(1) span.mat-calendar-body-cell-content');
            if(cell)cell.click();})()""")
        await tab.sleep(0.5)
        # Day: click 5th row, 2nd cell (21 in recording)
        await tab.evaluate("""(()=>{var cell=document.querySelector('tr:nth-of-type(5) > td:nth-of-type(2) span.mat-calendar-body-cell-content');
            if(cell)cell.click();})()""")
        await tab.sleep(0.5)

        await fill_input("[data-cy='managerEmail']", BUYER['email'])
        await fill_input("[data-cy='managerConfirmEmail']", BUYER['email'])
        await fill_input("[data-cy='managerPhone']", BUYER['phone'])

        # Language
        await tab.evaluate("""document.querySelector("[data-cy='managerLanguage']")?.click()""")
        await tab.sleep(0.3)
        await tab.evaluate("""document.querySelector("[data-cy='managerLanguageSection']")?.click()""")
        await tab.sleep(0.3)

        # Participants - fill BOTH (from recording)
        # Participant 0
        await fill_input("#participantSurname_0", "sekar")
        await fill_input("#participantName_0", "abiilesh")

        # Participant 1 - expand first, then fill
        await tab.evaluate("""(()=>{var el=document.querySelector('#participantElement_1 div.tw-flex-grow > div > div.tw-flex');
            if(el)el.click();else{var el2=document.querySelector('#participantElement_1 div.tw-flex-grow > div');
            if(el2)el2.click();}})()""")
        await tab.sleep(0.5)
        await fill_input("#participantSurname_1", "sekar")
        await fill_input("#participantName_1", "abiilesh")

        # Click outside to blur (from recording: clicks muvaParticipantContainer)
        await tab.evaluate("""(()=>{var el=document.querySelector('div.muvaParticipantContainer');
            if(el)el.click();})()""")
        await tab.sleep(0.5)

        log("  Form filled ✅")

        # ── GDPR CHECKBOX ─────────────────────────────────────
        cb = await tab.query_selector('#mat-mdc-checkbox-0-input')
        if not cb: cb = await tab.query_selector('#mat-mdc-checkbox-1-input')
        if not cb: cb = await tab.query_selector('input[id^="mat-mdc-checkbox"][type="checkbox"]')
        if cb: await cb.click()
        await asyncio.sleep(1.5)
        close = await tab.query_selector("[data-cy='purchase-rules-close-btn']")
        if close: await close.click()
        await asyncio.sleep(1)

        # ── TURNSTILE: wait for widget, scroll, click checkbox LAST ──
        log("Turnstile: waiting for widget to load...")

        # Wait for captchaElement to appear (Turnstile takes a few seconds)
        ts_ready = False
        for i in range(30):
            ce = await tab.query_selector('.captchaElement')
            if ce:
                # Check if it has content (iframe rendered inside)
                has_iframe = await tab.evaluate("""(()=>{
                    var el = document.querySelector('.captchaElement');
                    return el && el.children.length > 0;
                })()""")
                if has_iframe:
                    log(f"  Widget loaded after {i}s")
                    ts_ready = True
                    break
            await asyncio.sleep(1)

        # Wait for auto-solve — proxy + real browser fingerprint should trigger it
        log("  Waiting for Turnstile auto-solve (up to 60s)...")
        await tab.evaluate("""(()=>{var el=document.querySelector('.captchaElement');if(el)el.scrollIntoView({behavior:'instant',block:'center'});})()""")
        await asyncio.sleep(2)

        for i in range(120):
            try:
                token = await tab.evaluate("""(()=>{var i=document.querySelector('input[name=\"cf-turnstile-response\"]');return i&&i.value&&i.value.length>10?i.value.substring(0,30):null;})()""")
                if token: log(f"  ✅ Auto-solved in {i*0.5:.0f}s!"); break
            except Exception:
                log(f"  Connection dropped at {i*0.5:.0f}s — may have redirected!")
                break
            await asyncio.sleep(0.5)
        else:
            log("  Timeout — trying ACQUISTA anyway")

        # Wait for token
        log("  Waiting for token...")
        for i in range(60):
            t = await tab.evaluate("""(()=>{var i=document.querySelector('input[name="cf-turnstile-response"]');return i&&i.value&&i.value.length>10?i.value.substring(0,30):null;})()""")
            if t: log(f"  ✅ Token: {t}"); break
            await asyncio.sleep(0.5)
        else:
            log("  ⚠️  No token")

        # ── ACQUISTA ───────────────────────────────────────────
        log("ACQUISTA...")
        await tab.sleep(1)  # let Turnstile register
        buy = await tab.query_selector("[data-cy='buyButton']")
        if buy:
            await buy.scroll_into_view()
            await tab.sleep(0.3)
            await buy.click()
            log("  ✅ ACQUISTA clicked!")
        await tab.sleep(3)

        # ── WAIT FOR EPAY (handle connection drops on redirect) ──
        log("Waiting for epay...")
        epay_url = None
        for i in range(120):
            await tab.sleep(0.5)
            try:
                cur = str(await tab.evaluate("window.location.href"))
            except Exception:
                # Connection may drop on redirect — check if we got to epay
                await tab.sleep(2)
                try:
                    # Try to reconnect and check URL
                    cur = str(await tab.evaluate("window.location.href"))
                except Exception:
                    log("  Connection lost — epay may have loaded (check VNC)")
                    return {'success': True, 'epay_url': 'epay (check browser)', 'slot': slot}

            if 'epay.catholica.va' in cur:
                epay_url = cur
                log(f"🎉 EPAY captured! Length: {len(cur)} chars")
                log(f"   Full URL: {cur}")
                break
            if '/payment' in cur or '/confirm' in cur:
                epay_url = cur
                log(f"Payment page: {cur[:100]}")
                break
            if 'error' in cur.lower():
                log(f"Error page: {cur[:100]}")
                break
            if i == 10:
                log(f"  URL: {cur[:100]}")

        if epay_url:
            return {'success': True, 'epay_url': epay_url, 'slot': slot}
        # Final check - get current URL one more time
        try:
            final = str(await tab.evaluate("window.location.href"))
            if 'epay' in final:
                return {'success': True, 'epay_url': final, 'slot': slot}
        except: pass
        return {'success': False, 'slot': slot, 'error': 'no epay'}

    except Exception as e:
        log(f"Error: {e}"); import traceback; traceback.print_exc()
        return {'success': False, 'error': str(e)}
    finally:
        try: await tab.sleep(2); browser.stop()
        except: pass

async def main():
    import argparse; p=argparse.ArgumentParser()
    p.add_argument('--date', default=None); p.add_argument('--visitors', type=int, default=2)
    args=p.parse_args()

    slot = find_slot(args.date or (datetime.now()+timedelta(days=60)).strftime('%d/%m/%Y'), args.visitors)
    if not slot: log("No slots found"); return
    r = await book(slot)
    print(json.dumps({'success': r.get('success'), 'epay': r.get('epay_url','')[:100]}))

if __name__=='__main__': asyncio.run(main())
