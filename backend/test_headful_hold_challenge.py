import asyncio
import os
import sys
import json
import time
from datetime import datetime, timedelta
import requests

# Set up path to include root for worker_vatican and backend
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_dir)
sys.path.insert(0, os.path.join(root_dir, 'backend'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

from monitors.models import BuyerProfile, Agency
from worker_vatican.search_api_monitor import VaticanSearchAPIMonitor
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import argparse
import subprocess
import shutil
import tempfile

#  CONFIG 
VATICAN_BASE = 'https://tickets.museivaticani.va'
VISITORS = 1
ADULTS = 1
CHILDREN = 0
LOOKAHEAD_DAYS = 90
HEARTBEAT_INTERVAL_MS = 300000  # 5 minutes
TARGET_TICKET_NAME = "Musei Vaticani - Biglietti d'ingresso"
PREFERRED_TEST_DATE = "04/05/2026"
PERSISTENT_PROFILE_PATH = r"d:\bot\vatican_chrome_profile"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.7680.178 Safari/537.36"
# 

async def find_available_slot():
    """Iterate through the next 90 days and find the first available slot."""
    monitor = VaticanSearchAPIMonitor()
    
    # Try preferred date first
    dates_to_check = [PREFERRED_TEST_DATE]
    start_date = datetime.now()
    for i in range(LOOKAHEAD_DAYS):
        d = (start_date + timedelta(days=i)).strftime('%d/%m/%Y')
        if d not in dates_to_check:
            dates_to_check.append(d)

    print(f"SEARCHING for any available slot (Preferred: {PREFERRED_TEST_DATE})...")
    
    for date_str in dates_to_check:
        try:
            day, month, year = date_str.split('/')
            current_dt = datetime(int(year), int(month), int(day))
        except Exception:
            continue
            
        # Check if Sunday (Vatican usually closed)
        if current_dt.weekday() == 6:
            continue
            
        sys.stdout.write(f"\r  Checking {date_str}... ")
        sys.stdout.flush()
        
        try:
            success, slots, tid = monitor.check_ticket(
                target_date=date_str,
                ticket_name=TARGET_TICKET_NAME,
                visitors=VISITORS
            )
            
            if success and slots:
                best_slot = slots[0]
                print(f"\nFOUND SLOT! {date_str} at {best_slot.get('time')}")
                return {
                    'date': date_str,
                    'slot_id': best_slot.get('id'),
                    'slot_time': best_slot.get('time'),
                    'ticket_id': tid,
                    'visitors': VISITORS
                }
        except Exception as e:
            print(f"\nERROR checking {date_str}: {e}")
            
        await asyncio.sleep(0.5)
        
    print("\nNo slots found in the next 90 days.")
    return None

async def run_hold_challenge(slot_info):
    """
    Launch undetected Chrome via nodriver, fill form, and start heartbeat.
    nodriver patches Chrome binary to bypass Cloudflare Turnstile.
    """
    import nodriver as uc

    # Fetch profile (sync_to_async needed for Django ORM in async context)
    from asgiref.sync import sync_to_async
    
    @sync_to_async
    def get_profile():
        agency = Agency.objects.filter(is_active=True).exclude(plan='system').first()
        if not agency: 
            return {
                'first_name': 'Test', 'last_name': 'User', 'email': 'test@example.com',
                'phone': '123456789', 'city': 'Rome', 'country': 'Italy'
            }
        p = BuyerProfile.objects.filter(agency=agency).first()
        if not p: return None
        return {
            'first_name': p.first_name, 'last_name': p.last_name, 'email': p.email,
            'phone': p.phone, 'city': p.city, 'country': p.country
        }

    if slot_info is None:
        slot_info = {'visitors': 1, 'id': 'setup', 'date': '?', 'slot_time': '?', 'slot_id': 'setup'}
    
    is_setup = slot_info.get('id') == 'setup'
    
    profile_data = await get_profile()

    # Kill any leftover Chrome processes
    subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe', '/T'],
                   capture_output=True, timeout=5)
    await asyncio.sleep(1)

    # Clean stale lockfile
    lockfile = os.path.join(PERSISTENT_PROFILE_PATH, "lockfile")
    if os.path.exists(lockfile):
        try: os.remove(lockfile)
        except: pass

    print("\n" + "=" * 60)
    print(" LAUNCHING UNDETECTED CHROME (nodriver)")
    print(" Cloudflare CANNOT detect this browser.")
    print("=" * 60 + "\n")

    # ═══════════════════════════════════════════════════════════════
    # nodriver: Patches the Chrome binary itself to remove:
    #   - navigator.webdriver flag
    #   - CDP detection markers  
    #   - Automation-related JavaScript bindings
    #   - Chrome debugging protocol traces
    # This is what makes it invisible to Turnstile.
    # ═══════════════════════════════════════════════════════════════
    browser = await uc.start(
        user_data_dir=PERSISTENT_PROFILE_PATH,
        browser_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        headless=False,
        lang='it-IT',
    )

    tab = browser.main_tab
    print("   ✅ Undetected Chrome launched!")

    if is_setup:
        print("\nSETUP MODE: Navigate to https://tickets.museivaticani.va")
        print("Solve any challenges manually, then close Chrome or press Ctrl+C.")
        await tab.get('https://tickets.museivaticani.va/home')
        try:
            while True: await asyncio.sleep(60)
        except KeyboardInterrupt:
            print("Setup complete.")
            return

    # Build Entry URL
    from zoneinfo import ZoneInfo
    rome = ZoneInfo('Europe/Rome')
    day, month, year = slot_info['date'].split('/')
    dt = datetime(int(year), int(month), int(day), 0, 0, 0, tzinfo=rome)
    ts = int(dt.timestamp() * 1000)
    entry_url = f"{VATICAN_BASE}/home/visit/{slot_info['visitors']}/{ts}/1"

    try:
        # --- WARM-UP ---
        print(" [0] Warming up on Vatican homepage...")
        await tab.get('https://tickets.museivaticani.va/home')
        await tab.sleep(4)

        print(f" [1] Navigating to ticket page...")
        await tab.get(entry_url)
        await tab.sleep(4)

        # ── Step 1: Get ticket_id via Search API ──
        print(" [2] Resolving ticket ID via Search API...")
        search_url = f'{VATICAN_BASE}/api/search/resultPerTag?lang=it&visitorNum={slot_info["visitors"]}&visitDate={slot_info["date"]}&area=1&who=&page=0&tag=MV-Biglietti'
        
        # Use requests library for API call (more reliable than browser fetch)
        import requests as req
        # Get cookies from the browser for authenticated API call
        cookies = await browser.cookies.get_all()
        cookie_dict = {c.name: c.value for c in cookies if 'museivaticani' in (c.domain or '')}
        
        r = req.get(search_url, cookies=cookie_dict, headers={
            'Accept': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': USER_AGENT
        })
        
        if r.status_code != 200:
            print(f" Search API failed: {r.status_code}")
            # Try via browser JS instead
            result = await tab.evaluate(f"""
                fetch('{search_url}', {{
                    headers: {{ 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }},
                    credentials: 'include'
                }}).then(r => r.json())
            """)
            visits = result.get('visits', []) if result else []
        else:
            visits = r.json().get('visits', [])

        ticket = next((v for v in visits if 'musei vaticani' in v.get('name','').lower() and 'ingresso' in v.get('name','').lower()), None)
        if not ticket:
            print(f" Could not find standard entry ticket for {slot_info['date']}")
            return
        
        tid = str(ticket['id'])
        print(f"   found ticket_id: {tid}")

        # ── Step 2: Click bookTicket ──
        print(" [3] Clicking bookTicket...")
        try:
            await tab.evaluate(f"""
                document.querySelector("#ticket_{tid} img")?.click()
            """)
            await tab.sleep(1)
        except: pass

        await tab.sleep(1)
        await tab.evaluate(f"""
            document.querySelector("[data-cy='bookTicket_{tid}']")?.click()
        """)
        await tab.sleep(2)

        # ── Step 3: Set quantity ──
        print(f" [4] Setting quantity to {ADULTS} Adults...")
        await tab.evaluate("""
            const qty = document.querySelector("[data-cy='ticketQuantity']");
            if (qty) qty.click();
        """)
        await tab.sleep(0.5)
        await tab.evaluate("""
            const sec = document.querySelector("div.ng-touched section > div:nth-of-type(1)");
            if (sec) sec.click();
        """)
        await tab.sleep(0.3)
        await tab.evaluate("""
            const qty2 = document.querySelector("[data-cy='ticketQuantity']");
            if (qty2) qty2.click();
        """)
        await tab.sleep(0.5)
        clicked = await tab.evaluate("""
            (() => {
                const span = document.querySelector("[data-cy='ticketQuantitySection'] > span");
                if (span) { span.click(); return span.innerText.trim(); }
                const sec = document.querySelector("[data-cy='ticketQuantitySection']");
                if (sec) { sec.click(); return sec.innerText.trim(); }
                return null;
            })()
        """)
        print(f"   Quantity selected: {clicked}")
        await tab.sleep(0.5)

        # ── Step 4: Select time ──
        slot_time = slot_info['slot_time']
        print(f" [5] Selecting time: {slot_time}...")
        target_mins = int(slot_time.split(':')[0]) * 60 + int(slot_time.split(':')[1])
        if target_mins >= 14 * 60:
            await tab.evaluate("""
                (() => {
                    const tabs = Array.from(document.querySelectorAll('.tab')).filter(el => el.offsetParent !== null);
                    if (tabs.length >= 2) tabs[1].click();
                })()
            """)
            await tab.sleep(1)

        await tab.evaluate(f"""
            (() => {{
                const els = Array.from(document.querySelectorAll("[data-cy='time'] div.muvaCalendarNumber"))
                    .filter(el => el.innerText.trim() === '{slot_time}');
                if (els.length > 0) {{ els[0].scrollIntoView(); els[0].click(); }}
            }})()
        """)
        await tab.sleep(1.5)

        # ── Step 5: Click PROCEDI ──
        print(" [6] Clicking PROCEDI...")
        await tab.evaluate("""
            (() => {
                const btn = document.querySelector("[data-cy='bookVisit']") || 
                           Array.from(document.querySelectorAll("button")).find(b => b.textContent.includes("PROCEDI"));
                if (btn) btn.click();
            })()
        """)
        await tab.sleep(5)

        # ── Step 6: Fill Checkout Form ──
        print(" [7] Filling checkout form...")
        
        # Wait for form to load
        for i in range(15):
            el = await tab.evaluate("document.querySelector(\"[data-cy='managerSurname']\")?.tagName")
            if el: break
            await tab.sleep(1)

        async def fill_field(selector, value):
            await tab.evaluate(f"""
                (() => {{
                    const el = document.querySelector("{selector}");
                    if (el) {{
                        el.focus();
                        el.value = '';
                        el.value = "{value}";
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }})()
            """)

        await fill_field("[data-cy='managerSurname']", profile_data['last_name'])
        await fill_field("[data-cy='managerName']", profile_data['first_name'])
        await fill_field("[data-cy='managerCity']", profile_data['city'])
        await fill_field("[data-cy='managerEmail']", profile_data['email'])
        await fill_field("[data-cy='managerConfirmEmail']", profile_data['email'])
        await fill_field("[data-cy='managerPhone']", profile_data['phone'])

        # Check mandatory boxes
        print(" Checking mandatory boxes...")
        await tab.evaluate("""
            (() => {
                const cb1 = document.querySelector("#mat-mdc-checkbox-1-input");
                if (cb1 && !cb1.checked) {
                    cb1.click();
                    setTimeout(() => {
                        const close = document.querySelector("[data-cy='purchase-rules-close-btn'] mat-icon");
                        if (close) close.click();
                    }, 1000);
                }
                setTimeout(() => {
                    const cb4 = document.querySelector("#mat-mdc-checkbox-4-input");
                    if (cb4 && !cb4.checked) cb4.click();
                }, 1500);
            })()
        """)
        await tab.sleep(2)

        print(f"\n{'='*50}")
        print(" HOLD STABILIZED!")
        print(f"Slot: {slot_info['date']} {slot_info['slot_time']}")
        print(f" Starting Background Heartbeat (every 4 mins)")
        print(f" Checkboxes will be auto-maintained every 30s")
        print(f" Please wait for 70 minutes.")
        print(f"{'='*50}\n")

        # Inject Heartbeat
        adult_count = str(slot_info['visitors'])
        child_count = "0"
        await tab.evaluate("""
            ((slot_id, ticket_id, visitors, adult_count, child_count) => {
                window._vatican_heartbeat = setInterval(() => {
                    console.log('Sending heartbeat recap...');
                    fetch('/api/visit/recap', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({
                            visitId: slot_id,
                            visitTypeId: parseInt(ticket_id),
                            visitorNum: parseInt(visitors),
                            lang: 'it',
                            tickets: [
                                { id: 60, name: 'Biglietto Intero', price: 20, quantity: adult_count.toString() },
                                { id: 61, name: 'Biglietto Ridotto', price: 10, quantity: child_count.toString() }
                            ],
                            additionalCosts: {
                                'service-0': { id: 58, name: 'Diritti di Prevendita', price: 5, quantity: parseInt(visitors) }
                            },
                            services: [
                                { id: 58, name: 'Diritti di Prevendita', price: 5, quantity: parseInt(visitors) }
                            ]
                        })
                    }).then(r => {
                        const t = new Date().toLocaleTimeString();
                        if (r.status === 200) {
                            console.log('Heartbeat OK at', t);
                        } else {
                            console.log('Heartbeat ALERT:', r.status, 'at', t);
                        }
                    }).catch(e => console.log('Heartbeat error:', e));
                }, 240000);

                window._box_maintainer = setInterval(() => {
                    const cb1 = document.querySelector("#mat-mdc-checkbox-1-input");
                    const cb4 = document.querySelector("#mat-mdc-checkbox-4-input");
                    if (cb1 && !cb1.checked) {
                        cb1.click();
                        setTimeout(() => {
                            const close = document.querySelector("[data-cy='purchase-rules-close-btn'] mat-icon");
                            if (close) close.click();
                        }, 1000);
                    }
                    if (cb4 && !cb4.checked) cb4.click();
                }, 30000);
            })""" + f'("{slot_info["slot_id"]}", "{tid}", "{slot_info["visitors"]}", "{adult_count}", "{child_count}")')

        # Keep hold alive and show progress
        print("\n" + "🚀" * 20)
        print(" SESSION LOCKED! DO NOT CLOSE THE BROWSER.")
        print("🚀" * 20 + "\n")
        
        while True:
            elapsed = (time.time() - start_time) / 60
            sys.stdout.write(f"\r  🕒 HOLD ACTIVE: {elapsed:.1f}/70 mins passed... ")
            sys.stdout.flush()
            await asyncio.sleep(10)
            if elapsed >= 70:
                 print(f"\n\n🔥 70 MINUTES REACHED! 🔥")
                 print("You can now solve the captcha on the screen and click BUY.")

    except Exception as e:
        print(f"Script failed: {e}")
        import traceback
        traceback.print_exc()
        print("The browser is still open. You can finish manually.")
        try:
            while True: await asyncio.sleep(60)
        except KeyboardInterrupt:
            pass
    finally:
        print("\nShutting down...")
        try: browser.stop()
        except: pass
        try: subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe', '/T'], capture_output=True)
        except: pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true", help="Open browser for manual login")
    args = parser.parse_args()

    if args.setup:
        asyncio.run(run_hold_challenge(None))
    else:
        start_time = time.time()
        slot = asyncio.run(find_available_slot())
        if slot:
            asyncio.run(run_hold_challenge(slot))
        else:
            print("No slots found to test.")
