#!/usr/bin/env python3
"""
BOOKER USING EXISTING CHROME — connects to always-running Chrome via CDP.
This Chrome has been running for hours with cookies, sessions, real browsing.
No new Chrome launched — uses the warm profile that Cloudflare knows.
"""
import asyncio, json, time, random, sys, os, requests, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

VATICAN = "https://tickets.museivaticani.va"
CDP_HOST = "127.0.0.1"
CDP_PORT = 9222  # Chrome debug port
PROXY_USER = os.getenv("OXYLABS_USERNAME", "")
PROXY_PASS = os.getenv("OXYLABS_PASSWORD", "")
PROXY_HOST = os.getenv("OXYLABS_HOST", "isp.oxylabs.io")
PROXY_PORTS = [8001,8002,8003,8004,8005,8006,8007,8008,8009,8010,8011,8012,8013]

def log(msg): print(f"[{datetime.now():%H:%M:%S}] {msg}")

def find_slot(date_str, visitors=2):
    s = requests.Session()
    port = random.choice(PROXY_PORTS)
    s.proxies = {"http": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{port}", "https": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{port}"}
    s.headers.update({"Accept":"application/json","X-Requested-With":"XMLHttpRequest",
        "User-Agent":"Mozilla/5.0 Chrome/136.0.0.0 Safari/537.36","Referer":f"{VATICAN}/","Origin":VATICAN})
    try: s.get(f"{VATICAN}/home", timeout=8)
    except: pass
    r = s.get(f"{VATICAN}/api/search/resultPerTag", params=dict(lang="it",visitorNum=str(visitors),visitDate=date_str,area="1",who="",page="0",tag="MV-Biglietti"), timeout=8)
    if r.status_code!=200: return None
    visits = r.json().get("visits",[])
    EX = ['pellegrinaggi','lunch','pranzo','gruppi','specola','palazzo','didattiche']
    v = next((x for x in visits if "musei vaticani" in x.get("name","").lower() and "ingresso" in x.get("name","").lower() and not any(e in x.get("name","").lower() for e in EX) and x.get("availability")=="AVAILABLE"), None)
    if not v: return None
    tid = str(v["id"])
    r2 = s.get(f"{VATICAN}/api/visit/timeavail", params=dict(lang="it",visitLang="",visitTypeId=tid,visitorNum=str(visitors),visitDate=date_str), timeout=8)
    if r2.status_code!=200: return None
    slots = [x for x in r2.json().get("timetable",[]) if x.get("availability")=="AVAILABLE"]
    if not slots: return None
    log(f"Found: {date_str} {slots[0]['time']}")
    return dict(date=date_str, slot_id=str(slots[0]['id']), slot_time=slots[0]['time'], ticket_id=tid, visitors=visitors)

async def book_existing_chrome(slot):
    """Drive the EXISTING Chrome via CDP WebSocket — no new browser launched."""
    import websockets

    v=slot['visitors']; date=slot['date']; stime=slot['slot_time']
    rome=ZoneInfo('Europe/Rome'); d,m,y=date.split('/')
    ts = int(datetime(int(y),int(m),int(d),0,0,0,tzinfo=rome).timestamp()*1000)
    url = f"{VATICAN}/home/fromtag/{v}/{ts}/MV-Biglietti/1"

    log(f"Booking via EXISTING Chrome: {date} {stime} ({v}v)")

    # Connect to existing Chrome debug port
    resp = urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}/json", timeout=5)
    tabs = json.loads(resp.read())
    tab = next((t for t in tabs if t.get("type")=="page"), None)
    if not tab:
        log("No page tab found!")
        return {"success":False,"error":"no tab"}

    ws_url = tab["webSocketDebuggerUrl"]
    ws = await websockets.connect(ws_url, max_size=2**24)

    async def cdp(method, params=None):
        cid = int(time.time()*1000) % 100000
        await ws.send(json.dumps({"id":cid,"method":method,"params":params or {}}))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("id")==cid: return msg.get("result",{})

    async def eval_js(js):
        r = await cdp("Runtime.evaluate", {"expression":js, "returnByValue":True, "awaitPromise":False})
        return r.get("result",{}).get("value")

    try:
        # Enable Runtime
        await cdp("Runtime.enable")
        await cdp("Page.enable")

        # Navigate
        log(f"  Navigating to Vatican...")
        await cdp("Page.navigate", {"url": url})
        await asyncio.sleep(4)

        # Wait for tickets
        for _ in range(30):
            count = await eval_js("document.querySelectorAll(\"[data-cy^='bookTicket_']\").length")
            if count and int(count)>0: break
            await asyncio.sleep(0.5)
        log(f"  Tickets: {count}")

        # Click Vatican ticket
        tid_dom = await eval_js("""(()=>{var cards=Array.from(document.querySelectorAll('[id^="ticket_"]'));
            for(var c of cards){if(c.innerText.toLowerCase().includes('musei vaticani')){
            var btn=c.querySelector('[data-cy^="bookTicket_"]');if(btn)return btn.getAttribute('data-cy').replace('bookTicket_','');}}
            return null;})()""")
        if tid_dom:
            await eval_js(f"document.querySelector('[data-cy=\"bookTicket_{tid_dom}\"]')?.click()")
            log(f"  Ticket clicked: {tid_dom}")
        await asyncio.sleep(3)

        # Quantity
        await eval_js("document.querySelector(\"[data-cy='ticketQuantity']\")?.click()")
        await asyncio.sleep(1)
        await eval_js("""(()=>{var items=Array.from(document.querySelectorAll("[data-cy='ticketQuantitySection']"));
            if(items.length>=2)items[1].click();})()""")
        await asyncio.sleep(2)

        # Time slot
        target_h = int(stime.split(':')[0])
        if target_h >= 14:
            await eval_js("""(()=>{var tabs=Array.from(document.querySelectorAll('.tab,[role=\"tab\"]'))
                .filter(function(el){return el.offsetParent});var a=tabs.find(function(t){return /pomeriggio/i.test(t.innerText)});
                if(a)a.click()})()""")
            await asyncio.sleep(0.5)

        time_idx = await eval_js(f"""(function(){{
            var cells=document.querySelectorAll("[data-cy='time']");
            for(var i=0;i<cells.length;i++){{var c=cells[i];if(!c.offsetParent)continue;
            var t=c.innerText.trim();if(t.indexOf('ESAURITI')>-1||t.indexOf('SOLD')>-1)continue;
            if(t.indexOf('{stime}')>-1)return i;}}
            for(var i=0;i<cells.length;i++){{var c=cells[i];if(!c.offsetParent)continue;
            var t=c.innerText.trim();if(!(t.indexOf('ESAURITI')>-1||t.indexOf('SOLD')>-1))return i;}}
            return -1;}})()""")
        if time_idx>=0:
            await eval_js(f"(function(){{var c=document.querySelectorAll(\"[data-cy='time']\")[{time_idx}];if(c){{c.scrollIntoView({{behavior:'smooth',block:'center'}});c.click();}}}})()")
        await asyncio.sleep(2)

        # PROCEDI
        await eval_js("document.querySelector(\"[data-cy='bookVisit']\")?.click()")
        await asyncio.sleep(6)

        cur = str(await eval_js("window.location.href"))
        log(f"  URL: {cur[:80]}")
        if 'checkout' not in cur:
            return {"success":False,"error":"not checkout"}

        # Fill form (fast execCommand)
        fields = {
            "[data-cy='managerSurname']":"Rossi","[data-cy='managerName']":"Mario",
            "[data-cy='managerEmail']":"mario@test.it","[data-cy='managerConfirmEmail']":"mario@test.it",
            "[data-cy='managerPhone']":"3401234567","[data-cy='managerCity']":"Roma",
        }
        for sel, val in fields.items():
            await eval_js(f"""(function(){{var el=document.querySelector('{sel}');if(!el)return;el.focus();el.select();
                document.execCommand('selectAll',false,null);document.execCommand('insertText',false,'{val}');
                el.dispatchEvent(new Event('input',{{bubbles:true}}));el.dispatchEvent(new Event('change',{{bubbles:true}}));}})()""")
            await asyncio.sleep(0.1)

        await eval_js("document.querySelector(\"[data-cy='managerSex']\")?.click()"); await asyncio.sleep(0.2)
        await eval_js("document.querySelector(\"[data-cy='managerSexSection']\")?.click()"); await asyncio.sleep(0.2)
        await eval_js("document.querySelector(\"[data-cy='managerCountry']\")?.click()"); await asyncio.sleep(0.2)
        await eval_js("""(()=>{var s=document.querySelector('#searchInput_country');if(s){s.value='Italia';s.dispatchEvent(new Event('input',{bubbles:true}));}})()"""); await asyncio.sleep(0.3)
        await eval_js("""(()=>{var items=Array.from(document.querySelectorAll("[data-cy='managerCountrySection']"));for(var i=0;i<items.length;i++){if(/^ital/i.test(items[i].innerText.trim())){items[i].click();return;}}})()"""); await asyncio.sleep(0.2)
        await eval_js("document.querySelector(\"[data-cy='managerLanguage']\")?.click()"); await asyncio.sleep(0.2)
        await eval_js("document.querySelector(\"[data-cy='managerLanguageSection']\")?.click()"); await asyncio.sleep(0.2)

        # Participants
        await eval_js("""(()=>{var el=document.querySelector('#participantElement_0 div.tw-flex-grow > div');if(el)el.click();})()"""); await asyncio.sleep(0.3)
        await eval_js("""(function(){var el=document.querySelector('#participantSurname_0');if(!el)return;el.focus();el.select();document.execCommand('selectAll',false,null);document.execCommand('insertText',false,'Rossi');el.dispatchEvent(new Event('input',{bubbles:true}));})()"""); await asyncio.sleep(0.1)
        await eval_js("""(function(){var el=document.querySelector('#participantName_0');if(!el)return;el.focus();el.select();document.execCommand('selectAll',false,null);document.execCommand('insertText',false,'Mario');el.dispatchEvent(new Event('input',{bubbles:true}));})()"""); await asyncio.sleep(0.1)

        # Participant 1
        await eval_js("""(()=>{var el=document.querySelector('#participantElement_1 div.tw-flex-grow > div > div.tw-flex');if(el)el.click();else{var el2=document.querySelector('#participantElement_1 div.tw-flex-grow > div');if(el2)el2.click();}})()"""); await asyncio.sleep(0.3)
        await eval_js("""(function(){var el=document.querySelector('#participantSurname_1');if(!el)return;el.focus();el.select();document.execCommand('selectAll',false,null);document.execCommand('insertText',false,'Bianchi');el.dispatchEvent(new Event('input',{bubbles:true}));})()"""); await asyncio.sleep(0.1)
        await eval_js("""(function(){var el=document.querySelector('#participantName_1');if(!el)return;el.focus();el.select();document.execCommand('selectAll',false,null);document.execCommand('insertText',false,'Sofia');el.dispatchEvent(new Event('input',{bubbles:true}));})()""")

        log("  Form filled ✅")

        # GDPR checkbox
        await eval_js("document.querySelector('#mat-mdc-checkbox-0-input')?.click()||document.querySelector('#mat-mdc-checkbox-1-input')?.click()")
        await asyncio.sleep(1.5)
        await eval_js("document.querySelector(\"[data-cy='purchase-rules-close-btn']\")?.click()")
        await asyncio.sleep(1)

        # Reduced ticket checkbox
        await eval_js("""(()=>{var cbs=Array.from(document.querySelectorAll('mat-checkbox'));for(var i=0;i<cbs.length;i++){var t=cbs[i].innerText||'';if(t.indexOf('ridotto')>-1||t.indexOf('ragazzi')>-1){var inp=cbs[i].querySelector('input[type=\"checkbox\"]');if(inp&&!inp.checked)cbs[i].click();}}})()""")
        await asyncio.sleep(1)

        # Wait for Turnstile token (the EXISTING Chrome might auto-solve better)
        log("  Waiting for Turnstile...")
        for i in range(120):
            token = await eval_js("""(()=>{var i=document.querySelector('input[name=\"cf-turnstile-response\"]');return i&&i.value&&i.value.length>10?i.value.substring(0,30):null;})()""")
            if token: log(f"  ✅ Token in {i*0.5:.0f}s: {token}"); break
            if i%20==0: log(f"  ...{i*0.5:.0f}s")
            await asyncio.sleep(0.5)

        # ACQUISTA
        await eval_js("document.querySelector(\"[data-cy='buyButton']\")?.click()")
        log("  ACQUISTA clicked")
        await asyncio.sleep(3)

        # Wait for epay
        for _ in range(80):
            cur = str(await eval_js("window.location.href"))
            if 'epay.catholica.va' in cur:
                log(f"🎉 {cur[:120]}")
                return {"success":True,"epay_url":cur,"slot":slot}
            await asyncio.sleep(0.5)

        return {"success":False,"error":"no epay","slot":slot}

    except Exception as e:
        log(f"Error: {e}")
        import traceback; traceback.print_exc()
        return {"success":False,"error":str(e)}
    finally:
        try: await ws.close()
        except: pass


async def main():
    import argparse; p=argparse.ArgumentParser()
    p.add_argument('--date',default=None); p.add_argument('--visitors',type=int,default=2)
    args=p.parse_args()

    from datetime import date
    slot = find_slot(args.date or (date.today()+timedelta(days=60)).strftime('%d/%m/%Y'), args.visitors)
    if not slot: log("No slots"); return
    r = await book_existing_chrome(slot)
    print(json.dumps({"success":r.get("success"),"epay":r.get("epay_url","")[:150]}))

if __name__=='__main__':
    asyncio.run(main())
