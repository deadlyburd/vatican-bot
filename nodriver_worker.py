import asyncio
import os
import sys
import time
import requests
from datetime import datetime
import nodriver as uc
from zoneinfo import ZoneInfo

# === CONFIGURATION ===
# Set this to your Docker backend URL (e.g., 'http://your-vps-ip:8000')
BACKEND_BASE_URL = 'http://localhost:8000' 
VATICAN_BASE = 'https://tickets.museivaticani.va'
PROFILE_PATH = r"C:\Users\gotic\AppData\Local\Temp\vatican_multi_nodriver"
NODE_NAME = "WINDOWS_LOCAL_NODE"

async def hold_slot(task_data):
    """Performs the browser hold for a specific task."""
    tid = task_data['id']
    date = task_data['date'] # expected DD/MM/YYYY
    profile = task_data['profile']
    visitors = task_data['visitors']
    target_time = task_data['preferred_times'][0] if task_data['preferred_times'] else "09:00"

    print(f"🚀 [WORKER] Starting hold for Task #{tid} on {date} at {target_time}")
    
    # 1. Claim the task on server
    try:
        requests.post(f"{BACKEND_BASE_URL}/api/v1/worker/claim/{tid}/")
    except Exception as e:
        print(f"⚠️ Warning: Could not claim task: {e}")

    browser = await uc.start(
        user_data_dir=PROFILE_PATH,
        browser_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        headless=False,
        lang='it-IT',
    )
    tab = browser.main_tab

    try:
        # [Pre-flight] Warmup & Fetch available slot
        await tab.get(f'{VATICAN_BASE}/home')
        await tab.sleep(3)
        
        # Resolve ticket ID
        search_url = f"{VATICAN_BASE}/api/search/resultPerTag?lang=it&visitorNum={visitors}&visitDate={date}&area=1&who=&page=0&tag=MV-Biglietti"
        res = await tab.evaluate(f"fetch('{search_url}', {{headers: {{'Accept': 'application/json'}}}}).then(r => r.json())")
        
        visits = res.get('visits', [])
        ticket = next((v for v in visits if 'musei vaticani' in v.get('name','').lower() and 'ingresso' in v.get('name','').lower()), None)
        if not ticket:
            print("❌ [WORKER] Standard Ticket not found.")
            return
        ticket_id = str(ticket['id'])
        
        # Grab exact slot timestamp
        time_url = f"{VATICAN_BASE}/api/visit/timeavail?lang=it&visitLang=&visitTypeId={ticket_id}&visitorNum={visitors}&visitDate={date}"
        res2 = await tab.evaluate(f"fetch('{time_url}', {{headers: {{'Accept': 'application/json'}}}}).then(r => r.json())")
        slot = next((s for s in res2.get('timetable', []) if s.get('time') == target_time), None)
        if not slot:
            print(f"❌ [WORKER] Target time {target_time} not found in available list.")
            return
        
        slot_id = str(slot['id'])
        
        # Navigate to Booking Page
        # ts = milliseconds for start of day
        d_p, m_p, y_p = date.split('/')
        rome = ZoneInfo('Europe/Rome')
        ts = int(datetime(int(y_p), int(m_p), int(d_p), tzinfo=rome).timestamp() * 1000)
        entry_url = f"{VATICAN_BASE}/home/fromtag/{visitors}/{ts}/MV-Biglietti/1"
        await tab.get(entry_url)
        await tab.sleep(4)

        # UI Interactions
        await tab.evaluate(f"document.querySelector(\"[data-cy='bookTicket_{ticket_id}']\")?.click()")
        await tab.sleep(2)
        await tab.evaluate(f"""
            const items = Array.from(document.querySelectorAll("[data-cy='ticketQuantitySection']"));
            for(const item of items) {{
                if(item.innerText.trim().startsWith('{visitors}')) {{ item.click(); break; }}
            }}
        """)
        await tab.sleep(1)
        await tab.evaluate(f"""
            const cells = Array.from(document.querySelectorAll("[data-cy='time']"));
            for(const c of cells) {{
                if(c.innerText.includes('{target_time}')) {{ c.scrollIntoView(); c.click(); break; }}
            }}
        """)
        await tab.sleep(2)
        await tab.evaluate("document.querySelector(\"[data-cy='bookVisit']\")?.click()")
        await tab.sleep(5)

        # Fill Form
        await tab.evaluate(f"""
            const fields = [
                ['[data-cy="managerSurname"]', "{profile.get('last_name','Rossi')}"],
                ['[data-cy="managerName"]', "{profile.get('first_name','Mario')}"],
                ['[data-cy="managerCity"]', "{profile.get('city','Roma')}"],
                ['[data-cy="managerEmail"]', "{profile.get('email','mario.rossi@example.com')}"],
                ['[data-cy="managerConfirmEmail"]', "{profile.get('email','mario.rossi@example.com')}"],
                ['[data-cy="managerPhone"]', "{profile.get('phone','+39123')}" ]
            ];
            fields.forEach(([sel, val]) => {{
                const el = document.querySelector(sel);
                if(el) {{ el.focus(); el.value = val; el.dispatchEvent(new Event('input', {{bubbles:true}})); }}
            }});
        """)
        # Checkboxes
        await tab.evaluate("""
            const c1 = document.querySelector("#mat-mdc-checkbox-1-input");
            if(c1 && !c1.checked) { c1.click(); setTimeout(() => document.querySelector("[data-cy='purchase-rules-close-btn'] mat-icon")?.click(), 800); }
            const c4 = document.querySelector("#mat-mdc-checkbox-4-input");
            if(c4 && !c4.checked) c4.click();
        """)
        await tab.sleep(2)

        # Record Hold in Backend
        print("📝 Recording Hold in Central Database...")
        try:
            r = requests.post(f"{BACKEND_BASE_URL}/api/v1/worker/hold/record/", json={
                'task_id': tid,
                'date': date,
                'slot_id': slot_id,
                'slot_time': target_time,
                'ticket_id': ticket_id,
                'visitors': visitors,
                'worker_name': NODE_NAME
            })
            hold_id = r.json().get('hold_id')
        except Exception as e:
            print(f"❌ Critical Error recording hold: {e}")
            return

        # Inject Heartbeat
        await tab.evaluate(f"""
            window._vatican_heartbeat = setInterval(() => {{
                fetch('/api/visit/recap', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    credentials: 'include',
                    body: JSON.stringify({{
                        visitId: "{slot_id}",
                        visitTypeId: {ticket_id},
                        visitorNum: {visitors},
                        lang: 'it',
                        tickets: [{{ id: 60, name: 'Biglietto Intero', price: 20, quantity: "{visitors}" }}],
                        additionalCosts: {{ 'service-0': {{ id: 58, name: 'Diritti di Prevendita', price: 5, quantity: {visitors} }} }},
                        services: [ {{ id: 58, name: 'Diritti di Prevendita', price: 5, quantity: {visitors} }} ]
                    }})
                }}).then(r => console.log('Keepalive:', r.status));
            }}, 240000);
        """)

        print(f"✅ Slot Secured! Hold ID: {hold_id}. Polling for PAYMENT signal...")
        
        # Signal Polling Loop
        while True:
            try:
                sig_res = requests.get(f"{BACKEND_BASE_URL}/api/v1/worker/hold/{hold_id}/signal/", timeout=5).json()
                if sig_res.get('payment_ready'):
                    print("\n🔥 [WORKER] SIGNAL RECEIVED: PROCEEDING TO PAYMENT! 🔥")
                    await tab.evaluate("clearInterval(window._vatican_heartbeat);")
                    await tab.evaluate("""
                        const payBtn = document.querySelector("[data-cy='confirmDataAndBuy'] button") || 
                                       Array.from(document.querySelectorAll('button')).find(b => /pagamento/i.test(b.innerText));
                        if(payBtn) payBtn.click();
                    """)
                    print("✅ Redirected to Vatican Payment Gateway. User can now pay on this screen.")
                    break
                if sig_res.get('status') == 'released':
                    print("⏹️ [WORKER] Hold released on server. Closing browser.")
                    await browser.stop()
                    return
            except Exception:
                pass
            await asyncio.sleep(4)

        # Keep browser alive for manual payment
        while True:
            await asyncio.sleep(60)

    except Exception as e:
        print(f"❌ [WORKER] Error during hold: {e}")
    finally:
        # Optionally close browser if it crashed
        pass

async def main_loop():
    print(f"🤖 [NODE: {NODE_NAME}] Satellite Worker starting...")
    print(f"🛰️  Polling {BACKEND_BASE_URL} for Snipe tasks...")
    
    while True:
        try:
            r = requests.get(f"{BACKEND_BASE_URL}/api/v1/worker/tasks/", timeout=10)
            data = r.json()
            tasks = data.get('tasks', [])
            
            if tasks:
                # Pick the first task
                await hold_slot(tasks[0])
            
        except Exception as e:
            print(f"🕒 Polling Backend... ({e})")
            
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main_loop())
