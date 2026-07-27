#!/usr/bin/env python3
"""
VATICAN AUTO-BOOKER — Production Ready
========================================
- Finds available slots via API (search + timeavail)
- Opens Chrome via nodriver (Cloudflare Turnstile bypass)
- Full UI flow: ticket → quantity → time → PROCEDI → form → BUY → epay
- Runs on server with Xvfb + VNC
"""
import asyncio, sys, os, time, json, logging, warnings
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

VATICAN = "https://tickets.museivaticani.va"
PROFILE_DIR = "/root/vatican_booking_profile"

# Default buyer (overridden by CRM)
BUYER = dict(first_name="Mario", last_name="Rossi", email="mario.rossi@example.com",
             phone="3401234567", city="Roma", birth_year="1990", birth_month="GEN", birth_day="15")

# ── Helpers ──────────────────────────────────────────────────
def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}")

def unwrap(val):
    """Extract value from nodriver's type-annotated evaluate() results."""
    if isinstance(val, list):
        if len(val) > 0 and isinstance(val[0], list) and len(val[0]) == 2 and isinstance(val[0][0], str):
            d = {}
            for k, v in val:
                d[k] = unwrap(v)
            return d
        return [unwrap(v) for v in val]
    if isinstance(val, dict):
        return val.get('value', {k: unwrap(v) for k, v in val.items()})
    return val

def u(tab, js):
    """Evaluate JS and unwrap result."""
    return unwrap(tab.evaluate(js))

async def click(sel):
    """Click element by selector using nodriver."""
    el = await tab.query_selector(sel)
    if el:
        await el.scroll_into_view()
        await asyncio.sleep(0.2)
        await el.click()
        return True
    return False

async def fill(sel, value):
    """Fill a form field using send_keys (triggers Angular validation)."""
    el = await tab.query_selector(sel)
    if not el:
        log(f"  ⚠️  Not found: {sel}")
        return False
    await el.click()
    await asyncio.sleep(0.15)
    # Clear
    await el.send_keys('\x01')  # Ctrl+A
    await asyncio.sleep(0.05)
    # Type value
    for ch in str(value):
        await el.send_keys(ch)
        await asyncio.sleep(0.02)
    await el.send_keys('\t')  # Tab out
    await asyncio.sleep(0.1)
    return True

# ── Slot finder ──────────────────────────────────────────────
def find_slot(date_str, visitors=2):
    import requests
    H = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest",
         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36",
         "Referer": f"{VATICAN}/", "Origin": VATICAN}
    s = requests.Session()
    s.headers.update(H)
    try: s.get(f"{VATICAN}/home", timeout=8)
    except: pass

    EXCLUDED = ['pellegrinaggi','lunch','pranzo','gruppi','specola','palazzo','didattiche']

    dates = [date_str] if date_str else [
        (datetime.now()+timedelta(days=i)).strftime("%d/%m/%Y")
        for i in range(1,60) if (datetime.now()+timedelta(days=i)).weekday() != 6
    ]

    for d in dates:
        try:
            r = s.get(f"{VATICAN}/api/search/resultPerTag",
                      params=dict(lang="it", visitorNum=str(visitors), visitDate=d,
                                  area="1", who="", page="0", tag="MV-Biglietti"), timeout=8)
            if r.status_code != 200: continue
            visits = r.json().get("visits", [])
            ticket = next((v for v in visits
                          if "musei vaticani" in v.get("name","").lower()
                          and "ingresso" in v.get("name","").lower()
                          and not any(x in v.get("name","").lower() for x in EXCLUDED)
                          and v.get("availability") == "AVAILABLE"), None)
            if not ticket: continue

            tid = str(ticket["id"])
            r2 = s.get(f"{VATICAN}/api/visit/timeavail",
                       params=dict(lang="it", visitLang="", visitTypeId=tid,
                                   visitorNum=str(visitors), visitDate=d), timeout=8)
            if r2.status_code != 200: continue
            slots = [sl for sl in r2.json().get("timetable", [])
                    if sl.get("availability") == "AVAILABLE"]
            if not slots: continue

            best = slots[0]
            log(f"Found: {d} {best['time']} (id={best['id']})")
            return dict(date=d, slot_id=str(best['id']), slot_time=best['time'],
                       ticket_id=tid, visitors=visitors)
        except Exception as e:
            pass
        time.sleep(0.3)
    return None

# ── Browser flow ─────────────────────────────────────────────
tab = None  # global for helper functions

async def run_booking(slot):
    global tab
    import nodriver as uc

    visitors, date, slot_time, tid = slot['visitors'], slot['date'], slot['slot_time'], slot['ticket_id']

    # Build URL with Rome timezone
    rome = ZoneInfo('Europe/Rome')
    d, m, y = date.split('/')
    ts = int(datetime(int(y), int(m), int(d), 0, 0, 0, tzinfo=rome).timestamp() * 1000)
    url = f"{VATICAN}/home/fromtag/{visitors}/{ts}/MV-Biglietti/1"

    log(f"Launching Chrome → {date} {slot_time}")

    # Clean profile locks
    for lf in ['lockfile', 'SingletonLock', 'SingletonCookie']:
        try: os.remove(os.path.join(PROFILE_DIR, lf))
        except: pass

    browser = await uc.start(user_data_dir=PROFILE_DIR, headless=False,
                             lang="it-IT", no_sandbox=True)
    tab = browser.main_tab

    try:
        # [1] Navigate
        log(f"[1] {url}")
        await tab.get(url)

        # Wait for tickets
        for _ in range(60):
            count = await u(tab, """document.querySelectorAll("[data-cy^='bookTicket_']").length""")
            if count and int(count) > 0:
                break
            no_visits = await u(tab, """document.body?.innerText?.includes("Nessuna visita")||false""")
            if no_visits:
                log("  'Nessuna visita' - reloading")
                await tab.sleep(1)
                await tab.get(url)
            await tab.sleep(0.5)
        log(f"  {count} tickets found")

        # [2] Click Vatican ticket
        await u(tab, """(()=>{
            const cards=Array.from(document.querySelectorAll('[id^="ticket_"]'));
            for(const c of cards){
                const t=c.innerText.toLowerCase();
                if(t.includes('musei vaticani')&&(t.includes('ingresso')||t.includes('biglietti'))){
                    const btn=c.querySelector('[data-cy^="bookTicket_"]');
                    if(btn){btn.click();return;}
                }
            }
        })()""")
        await tab.sleep(3)

        # [3] Quantity
        log(f"[3] Quantity={visitors}")
        await click("[data-cy='ticketQuantity']")
        await tab.sleep(1)
        await u(tab, f"""(()=>{{
            const items=Array.from(document.querySelectorAll("[data-cy='ticketQuantitySection']"));
            for(const item of items){{
                if(item.innerText.trim().startsWith('{visitors}')){{item.click();return;}}
            }}
            if(items.length>={visitors})items[{visitors-1}].click();
        }})()""")
        await tab.sleep(2)

        # [4] Time slot - click first AVAILABLE
        log(f"[4] Time slot (prefer {slot_time})")
        clicked_time = await u(tab, f"""(()=>{{
            const cells=Array.from(document.querySelectorAll("[data-cy='time']"));
            for(const cell of cells){{
                const txt=cell.innerText.trim();
                if(txt.includes('ESAURITI')||txt.includes('SOLD'))continue;
                if(txt.includes('{slot_time}')){{
                    cell.scrollIntoView({{behavior:'smooth',block:'center'}});
                    cell.click();
                    return 'exact:'+txt.split('\\\\n')[0];
                }}
            }}
            // First available non-sold-out
            for(const cell of cells){{
                const txt=cell.innerText.trim();
                if(!txt.includes('ESAURITI')&&!txt.includes('SOLD')){{
                    cell.scrollIntoView({{behavior:'smooth',block:'center'}});
                    cell.click();
                    return 'first:'+txt.split('\\\\n')[0];
                }}
            }}
            return null;
        })()""")
        log(f"  Time: {clicked_time}")
        await tab.sleep(2)

        # [5] PROCEDI
        log("[5] PROCEDI")
        await click("[data-cy='bookVisit']")
        await tab.sleep(5)

        # Check if on recap page
        cur = await u(tab, 'window.location.href')
        if 'recap' in str(cur).lower():
            log("  Recap page - clicking PROCEDI again")
            await click("[data-cy='bookVisit']")
            await tab.sleep(5)

        # [6] Wait for checkout form
        log("[6] Waiting for checkout...")
        for _ in range(60):
            el = await u(tab, """document.querySelector("[data-cy='managerSurname']")?.tagName""")
            if el:
                break
            await tab.sleep(0.5)
        cur = await u(tab, 'window.location.href')
        log(f"  URL: {str(cur)[:100]}")

        if 'checkout' not in str(cur).lower():
            log("  ❌ Failed to reach checkout!")
            return {'success': False, 'error': 'checkout not reached', 'url': str(cur)}

        # [7] Fill form
        log("[7] Filling form...")
        await fill("[data-cy='managerSurname']", BUYER['last_name'])
        await fill("[data-cy='managerName']", BUYER['first_name'])
        await fill("[data-cy='managerEmail']", BUYER['email'])
        await fill("[data-cy='managerConfirmEmail']", BUYER['email'])
        await fill("[data-cy='managerPhone']", BUYER['phone'])
        await fill("[data-cy='managerCity']", BUYER['city'])

        # Gender
        await click("[data-cy='managerSex']")
        await tab.sleep(0.3)
        await click("[data-cy='managerSexSection']")
        await tab.sleep(0.3)

        # Country
        await click("[data-cy='managerCountry']")
        await tab.sleep(0.3)
        await u(tab, """(()=>{
            const s=document.querySelector('#searchInput_country');
            if(s){s.value='Ital';s.dispatchEvent(new Event('input',{bubbles:true}));}
        })()""")
        await tab.sleep(0.4)
        await u(tab, """(()=>{
            const items=Array.from(document.querySelectorAll("[data-cy='managerCountrySection']"));
            const it=items.find(el=>/^ital/i.test(el.innerText.trim()));
            if(it)it.click();
        })()""")
        await tab.sleep(0.3)

        # Birth date
        bd = f"{BUYER['birth_day'].zfill(2)}/01/{BUYER['birth_year']}"
        await u(tab, f"""(()=>{{
            const inp=document.querySelector("[data-cy='dateCalendar']");
            if(!inp)return;
            inp.removeAttribute('readonly');
            inp.focus();
            inp.value='{bd}';
            inp.dispatchEvent(new Event('input',{{bubbles:true}}));
            inp.dispatchEvent(new Event('change',{{bubbles:true}}));
            inp.setAttribute('readonly','true');
        }})()""")
        await tab.sleep(0.3)

        # Language
        await click("[data-cy='managerLanguage']")
        await tab.sleep(0.3)
        await click("[data-cy='managerLanguageSection']")
        await tab.sleep(0.3)

        # Participants
        for i in range(visitors):
            if i > 0:
                await u(tab, f"""(()=>{{
                    const el=document.querySelector('#participantElement_{i} div.tw-flex-grow > div');
                    if(el)el.click();
                }})()""")
                await tab.sleep(0.5)
            await fill(f"#participantSurname_{i}", BUYER['last_name'])
            await fill(f"#participantName_{i}", BUYER['first_name'])

        # GDPR checkboxes
        log("  GDPR checkboxes...")
        await u(tab, """(()=>{
            const cbs=Array.from(document.querySelectorAll('mat-checkbox'));
            for(const cb of cbs){
                const label=cb.innerText||'';
                if(label.includes('Norme')||label.includes('Accetto le')){
                    const inp=cb.querySelector('input');
                    if(inp&&!inp.checked)cb.click();
                }
            }
        })()""")
        await tab.sleep(1.5)
        await u(tab, """(()=>{
            const close=document.querySelector("[data-cy='purchase-rules-close-btn']")||
                Array.from(document.querySelectorAll('button')).find(b=>/chiudi|close/i.test(b.textContent));
            if(close)close.click();
        })()""")
        await tab.sleep(1)
        await u(tab, """(()=>{
            const cbs=Array.from(document.querySelectorAll('mat-checkbox'));
            for(const cb of cbs){
                const label=cb.innerText||'';
                if(label.includes('offerte')||label.includes('ricevere')){
                    const inp=cb.querySelector('input');
                    if(inp&&!inp.checked)cb.click();
                }
            }
        })()""")
        await tab.sleep(1)

        log("  ✅ Form filled - waiting for Turnstile...")

        # [8] Recap keepalive + Turnstile wait
        await u(tab, f"""(()=>{{
            window._keepalive=setInterval(()=>{{
                fetch('/api/visit/recap',{{
                    method:'POST',
                    headers:{{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'}},
                    credentials:'include',
                    body:JSON.stringify({{
                        visitId:'{slot["slot_id"]}',
                        visitTypeId:parseInt('{tid}'),
                        visitorNum:{visitors},
                        lang:'it',
                        tickets:[
                            {{id:60,name:'Biglietto Intero',price:20,quantity:'{visitors}'}},
                            {{id:61,name:'Biglietto Ridotto',price:10,quantity:0}}
                        ],
                        additionalCosts:{{'service-0':{{id:58,name:'Diritti di Prevendita',price:5,quantity:{visitors}}}}},
                        services:[{{id:58,name:'Diritti di Prevendita',price:5,quantity:{visitors}}}]
                    }})
                }}).catch(e=>console.log('kp err',e));
            }},60000);
        }})()""")
        await tab.sleep(5)

        # [9] Click BUY
        log("[9] Clicking BUY...")
        await click("[data-cy='buyButton']")
        await click("[data-cy='buyVisit']")
        # Fallback: any submit button
        await u(tab, """(()=>{
            const btns=Array.from(document.querySelectorAll('button'));
            const buy=btns.find(b=>/acquista|buy|conferma/i.test(b.textContent)&&!b.disabled);
            if(buy)buy.click();
        })()""")
        await tab.sleep(3)

        # [10] Wait for epay
        log("[10] Waiting for epay...")
        epay_url = None
        for i in range(120):
            await tab.sleep(0.5)
            try:
                cur = await u(tab, 'window.location.href')
                if cur and 'epay' in str(cur):
                    epay_url = str(cur)
                    log(f"  ✅ epay: {epay_url[:80]}")
                    break
                if cur and 'error' in str(cur).lower():
                    log(f"  ❌ Error: {str(cur)[:100]}")
                    break
                if i == 10:
                    err = await u(tab, """(()=>{
                        for(const sel of['[class*="error"]','[role="alert"]','mat-snack-bar-container']){
                            const e=document.querySelector(sel);
                            if(e&&e.innerText.trim().length>3)return e.innerText.trim().slice(0,200);
                        }
                        return null;
                    })()""")
                    if err:
                        log(f"  ⚠️  Page: {err}")
                    log(f"  URL: {str(cur)[:100]}")
            except:
                pass

        if epay_url:
            log(f"\\n🎉 SUCCESS! epay: {epay_url}")
            return {'success': True, 'epay_url': epay_url, 'slot': slot}

        log("  ❌ No epay redirect")
        return {'success': False, 'error': 'no epay redirect', 'slot': slot}

    except Exception as e:
        log(f"Error: {e}")
        import traceback; traceback.print_exc()
        return {'success': False, 'error': str(e), 'slot': slot}

    finally:
        try:
            await tab.sleep(2)
            browser.stop()
        except:
            pass


# ── Main ─────────────────────────────────────────────────────
async def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--date', default=None, help='DD/MM/YYYY')
    p.add_argument('--visitors', type=int, default=2)
    p.add_argument('--time', default=None, help='HH:MM')
    p.add_argument('--loop', action='store_true', help='Continuous CRM mode')
    args = p.parse_args()

    if args.loop:
        log("🔄 Continuous CRM booking mode")
        while True:
            slot = find_slot(None, args.visitors)
            if slot:
                log(f"🎯 Slot found: {slot['date']} {slot['slot_time']}")
                result = await run_booking(slot)
                log(f"Result: {json.dumps(result, default=str)[:200]}")
            else:
                log("No slots - retrying in 60s")
            await asyncio.sleep(60)
    else:
        log(f"🔍 Finding slot: {args.date or 'scan'}")
        slot = find_slot(args.date, args.visitors)
        if not slot:
            log("❌ No available slots")
            return
        result = await run_booking(slot)
        print(f"\n{'='*60}")
        if result.get('success'):
            print(f"✅ BOOKED! {slot['date']} {slot['slot_time']}")
            print(f"💳 {result['epay_url']}")
        else:
            print(f"❌ FAILED: {result.get('error')}")
        print("="*60)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    asyncio.run(main())
