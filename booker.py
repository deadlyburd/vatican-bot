#!/usr/bin/env python3
"""Vatican Auto-Booker v5 — time selection via Angular native click."""
import asyncio, sys, os, time, json, logging, warnings, requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")
VATICAN = "https://tickets.museivaticani.va"
PROFILE = "/root/vatican_booking_profile"
BUYER = dict(first_name="Mario", last_name="Rossi", email="mario.rossi@example.com",
             phone="3401234567", city="Roma", birth_year="1990", birth_month="GEN", birth_day="15")
H = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest",
     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36",
     "Referer": f"{VATICAN}/", "Origin": VATICAN}
EXCLUDED = ['pellegrinaggi','lunch','pranzo','gruppi','specola','palazzo','didattiche']

def log(msg): print(f"[{datetime.now():%H:%M:%S}] {msg}")
def unwrap(val):
    if isinstance(val, list):
        if len(val)>0 and isinstance(val[0], list) and len(val[0])==2 and isinstance(val[0][0], str):
            return {k: unwrap(v) for k,v in val}
        return [unwrap(v) for v in val]
    if isinstance(val, dict): return val.get('value', {k:unwrap(v) for k,v in val.items()})
    return val
def u(tab, js): return unwrap(tab.evaluate(js))

async def click(tab, sel):
    el = await tab.query_selector(sel)
    if el: await el.scroll_into_view(); await asyncio.sleep(0.2); await el.click(); return True
    return False

async def fill(tab, sel, value):
    el = await tab.query_selector(sel)
    if not el: return False
    await el.click(); await asyncio.sleep(0.15)
    await el.send_keys('\x01'); await asyncio.sleep(0.05)
    for ch in str(value): await el.send_keys(ch); await asyncio.sleep(0.02)
    await el.send_keys('\t'); await asyncio.sleep(0.1)
    return True

def find_slot(date_str=None, visitors=2):
    s = requests.Session(); s.headers.update(H)
    try: s.get(f"{VATICAN}/home", timeout=8)
    except: pass
    dates = [date_str] if date_str else [
        (datetime.now()+timedelta(days=i)).strftime("%d/%m/%Y")
        for i in range(1,60) if (datetime.now()+timedelta(days=i)).weekday()!=6]
    for d in dates:
        try:
            r = s.get(f"{VATICAN}/api/search/resultPerTag", params=dict(
                lang="it", visitorNum=str(visitors), visitDate=d, area="1", who="", page="0", tag="MV-Biglietti"), timeout=8)
            if r.status_code!=200: continue
            visits = r.json().get("visits",[])
            ticket = next((v for v in visits if "musei vaticani" in v.get("name","").lower()
                          and "ingresso" in v.get("name","").lower()
                          and not any(x in v.get("name","").lower() for x in EXCLUDED)
                          and v.get("availability")=="AVAILABLE"), None)
            if not ticket: continue
            tid = str(ticket["id"])
            r2 = s.get(f"{VATICAN}/api/visit/timeavail", params=dict(
                lang="it", visitLang="", visitTypeId=tid, visitorNum=str(visitors), visitDate=d), timeout=8)
            if r2.status_code!=200: continue
            slots = [sl for sl in r2.json().get("timetable",[]) if sl.get("availability")=="AVAILABLE"]
            if not slots: continue
            best = slots[0]
            log(f"Found: {d} {best['time']} (id={best['id']})")
            return dict(date=d, slot_id=str(best['id']), slot_time=best['time'], ticket_id=tid, visitors=visitors)
        except: pass
        time.sleep(0.3)
    return None

async def run_booking(slot):
    import nodriver as uc
    v=slot['visitors']; date=slot['date']; stime=slot['slot_time']; tid=slot['ticket_id']
    rome=ZoneInfo('Europe/Rome'); d,m,y=date.split('/')
    ts = int(datetime(int(y),int(m),int(d),0,0,0,tzinfo=rome).timestamp()*1000)
    url = f"{VATICAN}/home/fromtag/{v}/{ts}/MV-Biglietti/1"
    log(f"Chrome -> {date} {stime} ({v}v)")
    for lf in ['lockfile','SingletonLock','SingletonCookie']:
        try: os.remove(os.path.join(PROFILE, lf))
        except: pass
    browser = await uc.start(user_data_dir=PROFILE, headless=False, lang="it-IT", no_sandbox=True)
    tab = browser.main_tab
    try:
        # [1] Navigate
        await tab.get(url)
        for _ in range(60):
            count = await u(tab, """document.querySelectorAll("[data-cy^='bookTicket_']").length""")
            if count and int(count)>0: break
            no = await u(tab, """document.body?.innerText?.includes("Nessuna visita")||false""")
            if no: log("  reloading..."); await tab.sleep(1); await tab.get(url)
            await tab.sleep(0.5)
        log(f"  {count} tickets")
        # [2] Click Vatican ticket
        await u(tab, """(()=>{var cards=Array.from(document.querySelectorAll('[id^="ticket_"]'));
            for(var i=0;i<cards.length;i++){var c=cards[i];var t=c.innerText.toLowerCase();
            if(t.indexOf('musei vaticani')>-1&&(t.indexOf('ingresso')>-1||t.indexOf('biglietti')>-1)){
            var btn=c.querySelector('[data-cy^="bookTicket_"]');if(btn){btn.click();return;}}}})()""")
        await tab.sleep(3)
        # [3] Quantity
        log("[3] Quantity")
        await click(tab, "[data-cy='ticketQuantity']"); await tab.sleep(1)
        await u(tab, """(()=>{var items=Array.from(document.querySelectorAll("[data-cy='ticketQuantitySection']"));
            for(var i=0;i<items.length;i++){if(items[i].innerText.trim().indexOf('"""+str(v)+"""')===0)
            {items[i].click();return;}}if(items.length>="""+str(v)+""")items["""+str(v-1)+"""].click();})()""")
        await tab.sleep(2)
        # [4] Time slot — try clicking the number div inside the cell
        log(f"[4] Time: {stime}")
        ct = await u(tab, """(()=>{var cells=Array.from(document.querySelectorAll("[data-cy='time']"));
            for(var i=0;i<cells.length;i++){var c=cells[i];var txt=c.innerText.trim();
            if(txt.indexOf('ESAURITI')>-1||txt.indexOf('SOLD')>-1)continue;
            if(txt.indexOf('"""+stime+"""')>-1){c.scrollIntoView({behavior:'smooth',block:'center'});
            var num=c.querySelector('.muvaCalendarNumber');if(num){num.click();return 'num:'+txt.split('\\n')[0];}
            c.click();return 'cell:'+txt.split('\\n')[0];}}
            for(var i=0;i<cells.length;i++){var c=cells[i];var txt=c.innerText.trim();
            if(!(txt.indexOf('ESAURITI')>-1||txt.indexOf('SOLD')>-1)){c.scrollIntoView({behavior:'smooth',block:'center'});
            var num=c.querySelector('.muvaCalendarNumber');if(num){num.click();return 'first-num:'+txt.split('\\n')[0];}
            c.click();return 'first-cell:'+txt.split('\\n')[0];}}return null;})()""")
        log(f"  Time: {ct}")
        await tab.sleep(2)
        # [5] PROCEDI
        log("[5] PROCEDI")
        await click(tab, "[data-cy='bookVisit']"); await tab.sleep(5)
        cur = str(await u(tab, 'window.location.href'))
        if 'recap' in cur.lower():
            log("  Recap -> PROCEDI again"); await click(tab, "[data-cy='bookVisit']"); await tab.sleep(5)
        # [6] Checkout
        log("[6] Checkout...")
        for _ in range(60):
            el = await u(tab, """document.querySelector("[data-cy='managerSurname']")?.tagName""")
            if el: break
            await tab.sleep(0.5)
        cur = str(await u(tab, 'window.location.href'))
        log(f"  URL: {cur[:100]}")
        if 'checkout' not in cur.lower(): return {'success':False,'error':'checkout not reached'}
        # [7] Fill form
        log("[7] Filling...")
        await fill(tab, "[data-cy='managerSurname']", BUYER['last_name'])
        await fill(tab, "[data-cy='managerName']", BUYER['first_name'])
        await fill(tab, "[data-cy='managerEmail']", BUYER['email'])
        await fill(tab, "[data-cy='managerConfirmEmail']", BUYER['email'])
        await fill(tab, "[data-cy='managerPhone']", BUYER['phone'])
        await fill(tab, "[data-cy='managerCity']", BUYER['city'])
        await click(tab, "[data-cy='managerSex']"); await tab.sleep(0.3)
        await click(tab, "[data-cy='managerSexSection']"); await tab.sleep(0.3)
        await click(tab, "[data-cy='managerCountry']"); await tab.sleep(0.3)
        await u(tab, """(()=>{var s=document.querySelector('#searchInput_country');
            if(s){s.value='Ital';s.dispatchEvent(new Event('input',{bubbles:true}));}})()""")
        await tab.sleep(0.4)
        await u(tab, """(()=>{var items=Array.from(document.querySelectorAll("[data-cy='managerCountrySection']"));
            for(var i=0;i<items.length;i++){if(/^ital/i.test(items[i].innerText.trim())){items[i].click();return;}}})()""")
        await tab.sleep(0.3)
        bd = BUYER['birth_day'].zfill(2)+"/01/"+BUYER['birth_year']
        await u(tab, """(()=>{var inp=document.querySelector("[data-cy='dateCalendar']");if(!inp)return;
            inp.removeAttribute('readonly');inp.focus();inp.value='"""+bd+"""';
            inp.dispatchEvent(new Event('input',{bubbles:true}));
            inp.dispatchEvent(new Event('change',{bubbles:true}));
            inp.setAttribute('readonly','true');})()"""); await tab.sleep(0.3)
        await click(tab, "[data-cy='managerLanguage']"); await tab.sleep(0.3)
        await click(tab, "[data-cy='managerLanguageSection']"); await tab.sleep(0.3)
        for i in range(v):
            if i>0: await u(tab, """(()=>{var el=document.querySelector('#participantElement_"""+str(i)+""" div.tw-flex-grow > div');if(el)el.click();})()"""); await tab.sleep(0.5)
            await fill(tab, "#participantSurname_"+str(i), BUYER['last_name'])
            await fill(tab, "#participantName_"+str(i), BUYER['first_name'])
        log("  GDPR...")
        await u(tab, """(()=>{var cbs=Array.from(document.querySelectorAll('mat-checkbox'));
            for(var i=0;i<cbs.length;i++){var l=cbs[i].innerText||'';
            if(l.indexOf('Norme')>-1||l.indexOf('Accetto le')>-1){var inp=cbs[i].querySelector('input');
            if(inp&&!inp.checked)cbs[i].click();}}})()"""); await tab.sleep(1.5)
        await u(tab, """(()=>{var close=document.querySelector("[data-cy='purchase-rules-close-btn']");
            if(!close)close=Array.from(document.querySelectorAll('button')).find(function(b){return /chiudi|close/i.test(b.textContent)});
            if(close)close.click();})()"""); await tab.sleep(1)
        await u(tab, """(()=>{var cbs=Array.from(document.querySelectorAll('mat-checkbox'));
            for(var i=0;i<cbs.length;i++){var l=cbs[i].innerText||'';
            if(l.indexOf('offerte')>-1||l.indexOf('ricevere')>-1){var inp=cbs[i].querySelector('input');
            if(inp&&!inp.checked)cbs[i].click();}}})()"""); await tab.sleep(1)
        log("  Form done — waiting Turnstile")
        # [8] Keepalive
        await u(tab, """(()=>{window._kp=setInterval(function(){fetch('/api/visit/recap',{method:'POST',
            headers:{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'},
            credentials:'include',body:JSON.stringify({visitId:'"""+slot['slot_id']+"""',
            visitTypeId:parseInt('"""+tid+"""'),visitorNum:"""+str(v)+""",lang:'it',
            tickets:[{id:60,name:'Biglietto Intero',price:20,quantity:'"""+str(v)+"""'},
            {id:61,name:'Biglietto Ridotto',price:10,quantity:0}],
            additionalCosts:{'service-0':{id:58,name:'Diritti di Prevendita',price:5,quantity:"""+str(v)+"""}},
            services:[{id:58,name:'Diritti di Prevendita',price:5,quantity:"""+str(v)+"""}]})}).catch(function(e){console.log('kp',e)});},60000);})()""")
        await tab.sleep(5)
        # [9] BUY
        log("[9] BUY...")
        await click(tab, "[data-cy='buyButton']")
        await u(tab, """(()=>{var btns=Array.from(document.querySelectorAll('button'));
            for(var i=0;i<btns.length;i++){var b=btns[i];
            if((/acquista|buy|conferma/i).test(b.textContent)&&!b.disabled){b.click();return;}}})()""")
        await tab.sleep(3)
        # [10] epay
        log("[10] epay...")
        for i in range(120):
            await tab.sleep(0.5)
            try:
                cur = str(await u(tab, 'window.location.href'))
                if 'epay' in cur: log(f"EPay: {cur[:80]}"); return {'success':True,'epay_url':cur,'slot':slot}
                if 'error' in cur.lower(): log(f"Error page: {cur[:100]}"); break
                if i==10:
                    err = await u(tab, """(()=>{for(var s=0;s<3;s++){var e=document.querySelector(
                        ['[class*="error"]','[role="alert"]','mat-snack-bar-container'][s]);
                        if(e&&e.innerText.trim().length>3)return e.innerText.trim().slice(0,200);}return null;})()""")
                    if err: log(f"  Msg: {err}")
                    log(f"  URL: {cur[:100]}")
            except: pass
        return {'success':False,'error':'no epay','slot':slot}
    except Exception as e:
        log(f"Error: {e}"); import traceback; traceback.print_exc()
        return {'success':False,'error':str(e),'slot':slot}
    finally:
        try: await tab.sleep(2); browser.stop()
        except: pass

async def main():
    import argparse; p=argparse.ArgumentParser()
    p.add_argument('--date',default=None); p.add_argument('--visitors',type=int,default=2)
    p.add_argument('--loop',action='store_true'); args=p.parse_args()
    if args.loop:
        log("CRM mode");
        while True:
            slot = find_slot(None, args.visitors)
            if slot: log(f"Slot: {slot['date']} {slot['slot_time']}"); r=await run_booking(slot); log(str(r)[:200])
            else: log("No slots")
            await asyncio.sleep(60)
    else:
        slot = find_slot(args.date, args.visitors)
        if not slot: log("No slots."); return
        r = await run_booking(slot); print(json.dumps({'success':r.get('success'),'epay':r.get('epay_url','')[:80]}))

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO); asyncio.run(main())
