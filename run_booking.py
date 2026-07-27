#!/usr/bin/env python3
"""Run test_full_reservation.py adapted for Linux Docker."""
import asyncio, sys, os, time, json, requests, warnings
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")
VATICAN_BASE = "https://tickets.museivaticani.va"
CHROME_PATH = "/bin/google-chrome"
CHROME_PROFILE = "/root/vatican_test_profile"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36"
AUTO_PAY = False

PROFILE = {"first_name":"Mario","last_name":"Rossi","email":"mario.rossi@example.com","phone":"3401234567","city":"Roma","country":"Italia","birth_year":"1990","birth_month":"GEN","birth_day":"15","birth_date_iso":"1990-01-14T23:00:00.000Z"}
H = {"Accept":"application/json, text/plain, */*","X-Requested-With":"XMLHttpRequest","Referer":f"{VATICAN_BASE}/","User-Agent":USER_AGENT}

def log(msg): print(f"[{datetime.now().strftime(\"%H:%M:%S\")}] {msg}")

def find_slot(target_date, visitors):
    s = requests.Session()
    try: s.get(f"{VATICAN_BASE}/home", headers={"User-Agent":USER_AGENT}, timeout=8)
    except: pass
    dates = [target_date] if target_date else [(datetime.now()+timedelta(days=i)).strftime("%d/%m/%Y") for i in range(1,60) if (datetime.now()+timedelta(days=i)).weekday()!=6]
    EXCLUDED = ["pellegrinaggi","lunch","pranzo","gruppi","specola","palazzo","didattiche"]
    for date_str in dates:
        try:
            r = s.get(f"{VATICAN_BASE}/api/search/resultPerTag", params={"lang":"it","visitorNum":str(visitors),"visitDate":date_str,"area":"1","who":"","page":"0","tag":"MV-Biglietti"}, headers=H, timeout=8)
            if r.status_code!=200: continue
            visits = r.json().get("visits",[])
            ticket = next((v for v in visits if "musei vaticani" in v.get("name","").lower() and "ingresso" in v.get("name","").lower() and not any(x in v.get("name","").lower() for x in EXCLUDED) and v.get("availability")=="AVAILABLE"), None)
            if not ticket: continue
            tid = str(ticket["id"])
            r2 = s.get(f"{VATICAN_BASE}/api/visit/timeavail", params={"lang":"it","visitLang":"","visitTypeId":tid,"visitorNum":str(visitors),"visitDate":date_str}, headers=H, timeout=8)
            if r2.status_code!=200: continue
            slots = [sl for sl in r2.json().get("timetable",[]) if sl.get("availability")=="AVAILABLE"]
            if not slots: continue
            best = slots[0]
            print(f"\n  Found: {date_str} {best[\"time\"]} (slot_id={best[\"id\"]})")
            return {"date":date_str,"slot_id":str(best["id"]),"slot_time":best["time"],"ticket_id":tid,"visitors":visitors}
        except Exception as e: pass
        time.sleep(0.3)
    return None

async def run_in_browser(slot):
    import nodriver as uc
    visitors, date, slot_time, tid = slot["visitors"], slot["date"], slot["slot_time"], slot["ticket_id"]
    rome = ZoneInfo("Europe/Rome")
    d,m,y = date.split("/")
    ts = int(datetime(int(y),int(m),int(d),0,0,0,tzinfo=rome).timestamp()*1000)
    entry_url = f"{VATICAN_BASE}/home/fromtag/{visitors}/{ts}/MV-Biglietti/1"
    log("Launching Chrome...")
    for lf in ["lockfile","SingletonLock","SingletonCookie"]:
        try: os.remove(os.path.join(CHROME_PROFILE,lf))
        except: pass
    browser = await uc.start(user_data_dir=CHROME_PROFILE, headless=False, lang="it-IT", no_sandbox=True)
    tab = browser.main_tab
    try:
        log(f"[1] {entry_url}")
        await tab.get(entry_url)
        count = 0
        for attempt in range(3):
            for _ in range(30):
                count = await tab.evaluate("document.querySelectorAll(\"[data-cy^=bookTicket_]\").length")
                if count and int(count)>0: break
                no_visits = await tab.evaluate("document.body?.innerText?.includes(\"Nessuna visita\")||false")
                if no_visits:
                    log(f"  Nessuna visita - reloading")
                    await tab.sleep(1); await tab.get(entry_url); await tab.sleep(2); break
                await tab.sleep(0.5)
            if count and int(count)>0: break
            await tab.sleep(2)
        await tab.sleep(0.5)
        log(f"  Page loaded - {count} ticket buttons")
        
        log("[2] Finding PRENOTA...")
        dom_tid = None
        for _ in range(10):
            dom_tid = await tab.evaluate("""
                (()=>{const cards=Array.from(document.querySelectorAll("[id^=\\"ticket_\\"]"));for(const card of cards){const text=card.innerText.toLowerCase();if(text.includes("musei vaticani")&&(text.includes("ingresso")||text.includes("biglietti"))){const btn=card.querySelector("[data-cy^=\\"bookTicket_\\"]");if(btn)return btn.getAttribute("data-cy").replace("bookTicket_","");}}const allBtns=Array.from(document.querySelectorAll("[data-cy^=\\"bookTicket_\\"]"));for(const btn of allBtns){if(btn.innerText.trim()==="PRENOTA")return btn.getAttribute("data-cy").replace("bookTicket_","");}return null;})()
            """)
            if dom_tid: break
            await tab.sleep(0.5)
        if dom_tid:
            log(f"  DOM ticket_id={dom_tid}")
            tid = dom_tid
        await tab.evaluate(f"document.querySelector(\"[data-cy=bookTicket_{tid}]\")?.click()")
        await tab.sleep(2)
        
        log(f"[3] Setting quantity={visitors}...")
        for _ in range(20):
            has_qty = await tab.evaluate("!!document.querySelector(\"select,[data-cy=ticketQuantity]\")")
            if has_qty: break
            await tab.sleep(0.5)
        qty_set = await tab.evaluate(f"""
            (()=>{{const selects=Array.from(document.querySelectorAll("select"));for(const sel of selects){{sel.value="{visitors}";sel.dispatchEvent(new Event("change",{{bubbles:true}}));return "select:"+sel.value;}}const el=document.querySelector("[data-cy=ticketQuantity]");if(el){{el.click();return "dropdown-opened";}}return "not-found";}})()
        """)
        if "dropdown" in str(qty_set) or "opened" in str(qty_set):
            await tab.sleep(0.8)
            clicked = await tab.evaluate(f"""
                (()=>{{const items=Array.from(document.querySelectorAll("[data-cy=ticketQuantitySection]"));for(const item of items){{const t=item.innerText.trim();if(t==="{visitors}"||t.startsWith("{visitors} ")){{item.click();return "clicked:"+t;}}}}if(items.length>={visitors}){{items[{visitors}-1].click();return "index";}}if(items.length>0){{items[items.length-1].click();return "last";}}return "no-option";}})()
            """)
            log(f"  Quantity: {clicked}")
        await tab.sleep(1.5)
        
        log(f"[4] Selecting time={slot_time}...")
        target_mins = int(slot_time.split(":")[0])*60+int(slot_time.split(":")[1]) if slot_time else 0
        for _ in range(30):
            count = await tab.evaluate("document.querySelectorAll(\"[data-cy=time]\").length")
            if count and int(count)>0: break
            await tab.sleep(0.5)
        log(f"  {count} time slots found")
        if target_mins>=14*60:
            await tab.evaluate("""(()=>{const tabs=Array.from(document.querySelectorAll(".tab, [role=\\"tab\\"], button[class*=\\"tab\\"]")).filter(el=>el.offsetParent!==null);const afternoon=tabs.find(t=>/pomeriggio/i.test(t.innerText));if(afternoon)afternoon.click();else if(tabs.length>=2)tabs[1].click();})()""")
            await tab.sleep(0.8)
        clicked_time = await tab.evaluate(f"""
            (()=>{{const cells=Array.from(document.querySelectorAll("[data-cy=time]"));for(const cell of cells){{const txt=cell.innerText.trim();if(txt==="{slot_time}"||txt.startsWith("{slot_time}")){{cell.scrollIntoView({{behavior:"smooth",block:"center"}});cell.click();return "exact:"+txt;}}}}let best=null,bestTxt=null,bestDiff=9999;for(const cell of cells){{const txt=cell.innerText.trim().split("\\n")[0];const parts=txt.split(":");if(parts.length!==2)continue;const mins=parseInt(parts[0])*60+parseInt(parts[1]);const diff=Math.abs(mins-{target_mins});if(diff<bestDiff){{bestDiff=diff;best=cell;bestTxt=txt;}}}}if(best){{best.click();return "closest:"+bestTxt;}}if(cells.length>0){{cells[0].click();return "first";}}return null;}})()
        """)
        log(f"  Time: {clicked_time}")
        await tab.sleep(2)
        
        log("[5] PROCEDI...")
        for _ in range(10):
            if await tab.evaluate("!!document.querySelector(\"[data-cy=bookVisit]\")"): break
            await tab.sleep(0.5)
        await tab.evaluate("""(()=>{const btn=document.querySelector("[data-cy=bookVisit]")||Array.from(document.querySelectorAll("button")).find(b=>/PROCEDI/i.test(b.textContent));if(btn)btn.click();})()""")
        await tab.sleep(5)
        
        log("[6] Waiting for form...")
        for _ in range(60):
            if await tab.evaluate("document.querySelector(\"[data-cy=managerSurname]\")?.tagName"): break
            await tab.sleep(0.5)
        log("  Form loaded")
        
        log("[7] Filling form...")
        async def fill(sel, val):
            await tab.evaluate(f"""(()=>{{const el=document.querySelector("{sel}");if(!el)return;el.focus();el.value="";el.value="{str(val)}";el.dispatchEvent(new Event("input",{{bubbles:true}}));el.dispatchEvent(new Event("change",{{bubbles:true}}));el.dispatchEvent(new Event("blur",{{bubbles:true}}));}})()""")
        async def fill_phone(sel, val):
            el = await tab.query_selector(sel)
            if el:
                await el.click(); await tab.sleep(0.2)
                await tab.evaluate(f"""(()=>{{const el=document.querySelector("{sel}");if(el){{el.value="";el.dispatchEvent(new Event("input",{{bubbles:true}}));}}}})()""")
                for ch in str(val): await el.send_keys(ch); await tab.sleep(0.03)
                await tab.evaluate(f"""(()=>{{const el=document.querySelector("{sel}");if(el){{el.dispatchEvent(new Event("change",{{bubbles:true}}));el.dispatchEvent(new Event("blur",{{bubbles:true}}));}}}})()""")
        await fill("[data-cy=managerSurname]",PROFILE["last_name"])
        await fill("[data-cy=managerName]",PROFILE["first_name"])
        await fill("[data-cy=managerCity]",PROFILE["city"])
        await fill("[data-cy=managerEmail]",PROFILE["email"])
        await fill("[data-cy=managerConfirmEmail]",PROFILE["email"])
        await fill_phone("[data-cy=managerPhone]",PROFILE["phone"])
        await tab.sleep(0.3)
        await tab.evaluate("document.querySelector(\"[data-cy=managerSex]\")?.click()"); await tab.sleep(0.3)
        await tab.evaluate("document.querySelector(\"[data-cy=managerSexSection]\")?.click()"); await tab.sleep(0.3)
        await tab.evaluate("document.querySelector(\"[data-cy=managerCountry]\")?.click()"); await tab.sleep(0.3)
        await tab.evaluate("""(()=>{const s=document.querySelector("#searchInput_country");if(s){s.value="Ital";s.dispatchEvent(new Event("input",{bubbles:true}));}})()"""); await tab.sleep(0.4)
        await tab.evaluate("""(()=>{const items=Array.from(document.querySelectorAll("[data-cy=managerCountrySection]"));const italia=items.find(el=>/^ital/i.test(el.innerText.trim()));if(italia)italia.click();else if(items[0])items[0].click();})()"""); await tab.sleep(0.3)
        log("  Setting birth date...")
        birth_display = f"{PROFILE[birth_day].zfill(2)}/01/{PROFILE[birth_year]}"
        await tab.evaluate(f"""(()=>{{const inp=document.querySelector("[data-cy=dateCalendar]");if(!inp)return;inp.removeAttribute("readonly");inp.focus();inp.value="{birth_display}";inp.dispatchEvent(new Event("input",{{bubbles:true}}));inp.dispatchEvent(new Event("change",{{bubbles:true}}));inp.setAttribute("readonly","true");}})()"""); await tab.sleep(0.5)
        await tab.evaluate("document.querySelector(\"[data-cy=managerLanguage]\")?.click()"); await tab.sleep(0.3)
        await tab.evaluate("document.querySelector(\"[data-cy=managerLanguageSection]\")?.click()"); await tab.sleep(0.3)
        for i in range(visitors):
            if i>0:
                await tab.evaluate(f"""(()=>{{const el=document.querySelector("#participantElement_{i} div.tw-flex-grow > div");if(el)el.click();}})()"""); await tab.sleep(0.5)
            await fill(f"#participantSurname_{i}",PROFILE["last_name"])
            await fill(f"#participantName_{i}",PROFILE["first_name"])
        log("  GDPR...")
        await tab.evaluate("""(()=>{const cb=document.querySelectorAll("input[type=\\"checkbox\\"]")[0];if(cb&&!cb.checked)cb.click();})()"""); await tab.sleep(1.5)
        await tab.evaluate("""(()=>{const close=document.querySelector("[data-cy=purchase-rules-close-btn]")||Array.from(document.querySelectorAll("button")).find(b=>/chiudi|close/i.test(b.textContent));if(close)close.click();})()"""); await tab.sleep(1)
        await tab.evaluate("""(()=>{const cb=document.querySelectorAll("input[type=\\"checkbox\\"]")[1];if(cb&&!cb.checked)cb.click();})()"""); await tab.sleep(0.5)
        
        log("  Keepalive + Turnstile...")
        await tab.evaluate(f"""(()=>{{window._keepalive=setInterval(()=>{{fetch("/api/visit/recap",{{method:"POST",headers:{{"Content-Type":"application/json","X-Requested-With":"XMLHttpRequest"}},credentials:"include",body:JSON.stringify({{visitId:"{slot["slot_id"]}",visitTypeId:parseInt("{tid}"),visitorNum:{visitors},lang:"it",tickets:[{{id:60,name:"Biglietto Intero",price:20,quantity:"{visitors}"}},{{id:61,name:"Biglietto Ridotto",price:10,quantity:0}}],additionalCosts:{{"service-0":{{id:58,name:"Diritti di Prevendita",price:5,quantity:{visitors}}}}},services:[{{id:58,name:"Diritti di Prevendita",price:5,quantity:{visitors}}}]}})}}).catch(e=>console.log("keepalive err",e));}},60000);}})()""")
        await tab.sleep(4)
        
        log("[8] Clicking BUY...")
        clicked_buy = await tab.evaluate("""(()=>{const btn=document.querySelector("[data-cy=buyButton],[data-cy=buyVisit]");if(btn&&!btn.disabled){btn.click();return btn.getAttribute("data-cy");}const submits=Array.from(document.querySelectorAll("button[type=submit]")).filter(b=>!b.disabled);if(submits.length>0){submits[submits.length-1].click();return "submit-btn";}return null;})()""")
        log(f"  BUY: {clicked_buy}")
        
        log("[9] Waiting for epay...")
        epay_url = ""
        for i in range(120):
            await tab.sleep(0.5)
            try:
                cur = await tab.evaluate("window.location.href")
                if cur and "epay" in cur: epay_url = cur; log(f"  epay: {epay_url[:80]}"); break
                if cur and ("error" in cur.lower() or "errore" in cur.lower()): log(f"  Error: {cur}"); break
                if i==10:
                    cur_url = await tab.evaluate("window.location.href")
                    log(f"  URL: {cur_url[:100]}")
                    err = await tab.evaluate("""(()=>{for(const sel of["[class*=\\"error\\"]","[role=\\"alert\\"]","mat-snack-bar-container"]){const e=document.querySelector(sel);if(e&&e.innerText.trim().length>3)return e.innerText.trim().slice(0,200);}return null;})()""")
                    if err: log(f"  Page: {err}")
            except: pass
        if not epay_url: log("  No epay redirect"); return {"epay_url":"","slot":slot}
        
        log("[10] Payment page loaded!")
        await tab.sleep(60)
        return {"epay_url":epay_url,"slot":slot}
    except Exception as e: log(f"Error: {e}"); import traceback; traceback.print_exc(); return {"epay_url":"","slot":slot}
    finally:
        try: await tab.sleep(2); browser.stop()
        except: pass

async def main(target_date, visitors):
    print("\\n"+"="*60); print("  Vatican Full Reservation Test"); print("="*60)
    log("STEP 1: Finding slot...")
    slot = find_slot(target_date, visitors)
    if not slot: log("No slot found."); return
    log(f"STEP 2: Browser flow for {slot[date]} {slot[slot_time]} ({visitors}v)...")
    result = await run_in_browser(slot)
    print("\\n"+"="*60)
    if result and result.get("epay_url"):
        print(f"  SUCCESS\\n  Date: {slot[date]} {slot[slot_time]}\\n  PAYMENT: {result[epay_url]}")
    else: print("  FAILED")
    print("="*60)

if __name__=="__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date",default=None,help="DD/MM/YYYY")
    p.add_argument("--visitors",type=int,default=2)
    args = p.parse_args()
    asyncio.run(main(args.date, args.visitors))
