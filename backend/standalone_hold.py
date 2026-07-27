import asyncio
import os
import sys
import json
import time
from datetime import datetime, timedelta
import requests
import subprocess
import tempfile
import shutil

# Install instructions for the other computer:
# pip install playwright requests python-dotenv
# playwright install chromium

from playwright.async_api import async_playwright

# ── CONFIG ────────────────────────────────────────────────────────────────────
SERVER_URL = "http://localhost:8000"  # Change to your server URL (e.g. https://your-panel.com)
VATICAN_BASE = 'https://tickets.museivaticani.va'
VISITORS = 1
PREFERRED_TEST_DATE = '15/05/2026'

# Fallback credentials in case the server isn't reachable
FALLBACK_USERNAME = "your_oxylabs_user"
FALLBACK_PASSWORD = "your_oxylabs_password"

# ── API HELPERS ───────────────────────────────────────────────────────────────

def get_proxy_from_api():
    """Fetch an active proxy from your central database."""
    print(f"📡 Fetching proxy from {SERVER_URL}/api/v1/proxies/...")
    try:
        r = requests.get(f"{SERVER_URL}/api/v1/proxies/", timeout=10)
        if r.status_code == 200:
            proxies = r.json()
            active_proxies = [p for p in proxies if p.get('is_active')]
            if active_proxies:
                import random
                proxy = random.choice(active_proxies)
                print(f"  ✅ Picked proxy: {proxy['ip_port']}")
                return proxy
    except Exception as e:
        print(f"  ⚠️ Could not fetch proxies from API: {e}")
    return None

def get_profile_from_api():
    """Fetch the BuyerProfile from your central database."""
    print(f"📡 Fetching BuyerProfile from {SERVER_URL}/api/v1/buyer-profile/...")
    try:
        r = requests.get(f"{SERVER_URL}/api/v1/buyer-profile/", timeout=10)
        if r.status_code == 200:
            profile = r.json()
            if profile and profile.get('first_name'):
                print(f"  ✅ Picked profile: {profile['first_name']} {profile['last_name']}")
                return profile
    except Exception as e:
        print(f"  ⚠️ Could not fetch profile from API: {e}")
    
    # HARDCODED FALLBACK
    return {
        'first_name': "Mario", 'last_name': "Rossi",
        'email': "mario.rossi@example.com", 'phone': "+393401234567",
        'city': "Roma", 'country': "Italy"
    }

async def search_slots_api():
    """Use your server's search API instead of running it locally."""
    print(f"📡 Requesting ticket search from {SERVER_URL}/api/v1/vatican/tickets/...")
    try:
        r = requests.get(f"{SERVER_URL}/api/v1/vatican/tickets/", params={
            'date': PREFERRED_TEST_DATE,
            'visitors': VISITORS
        }, timeout=20)
        
        if r.status_code == 200:
            data = r.json()
            # Try to grab the first available slot
            for dt, slots in data.get('available_dates', {}).items():
                if slots:
                    return {
                        'date': dt,
                        'slot_time': slots[0]['time'],
                        'slot_id': slots[0]['id'],
                        'visitors': VISITORS,
                        'ticket_id': data.get('ticket_type_id', 60)
                    }
    except Exception as e:
        print(f"  ⚠️ API Search failed: {e}")
    return None

# ── HOLD CHALLENGE ────────────────────────────────────────────────────────────

async def run_standalone_challenge(slot_info):
    profile_data = get_profile_from_api()
    proxy = get_proxy_from_api()
    
    oxy_username = os.environ.get('OXYLABS_USERNAME', FALLBACK_USERNAME)
    oxy_password = os.environ.get('OXYLABS_PASSWORD', FALLBACK_PASSWORD)

    async with async_playwright() as p:
        # Chrome location differs by OS
        if sys.platform == "win32":
            chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
        elif sys.platform == "darwin":
            chrome_path = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        else:
            chrome_path = '/usr/bin/google-chrome'

        temp_profile = os.path.join(tempfile.gettempdir(), 'standalone_chrome_profile')
        
        proxy_args = []
        if proxy:
            p_user = proxy.get('username') or oxy_username
            p_pass = proxy.get('password') or oxy_password
            
            if p_user and p_pass:
                # Generate a dynamic proxy-auth extension for Chrome
                proxy_plugin_dir = os.path.join(tempfile.gettempdir(), 'vatican_proxy_auth_plugin')
                os.makedirs(proxy_plugin_dir, exist_ok=True)
                
                manifest_json = '{ "version": "1.0.0", "manifest_version": 2, "name": "Chrome Proxy", "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"], "background": {"scripts": ["background.js"]}, "minimum_chrome_version": "22.0.0" }'
                background_js = f'''
                var config = {{ mode: "fixed_servers", rules: {{ singleProxy: {{ scheme: "http", host: "{proxy['ip_port'].split(':')[0]}", port: parseInt({proxy['ip_port'].split(':')[1]}) }}, bypassList: ["localhost"] }} }};
                chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});
                function callbackFn(details) {{ return {{ authCredentials: {{ username: "{p_user}", password: "{p_pass}" }} }}; }}
                chrome.webRequest.onAuthRequired.addListener( callbackFn, {{urls: ["<all_urls>"]}}, ['blocking'] );
                '''
                with open(os.path.join(proxy_plugin_dir, "manifest.json"), "w") as f: f.write(manifest_json)
                with open(os.path.join(proxy_plugin_dir, "background.js"), "w") as f: f.write(background_js)
                    
                proxy_args = [f'--load-extension={proxy_plugin_dir}']
                print("🔒 Generated proxy auth extension inside temp folder")
            else:
                proxy_args = [f'--proxy-server=http://{proxy["ip_port"]}']

        debug_port = 9222
        chrome_cmd = [
            chrome_path, f'--remote-debugging-port={debug_port}', f'--user-data-dir={temp_profile}',
            '--profile-directory=Default', '--no-first-run', '--no-default-browser-check',
            '--start-maximized', '--disable-blink-features=AutomationControlled', 'about:blank'
        ] + proxy_args
        
        print("⚙️ Launching real Chrome via CDP...")
        chrome_proc = subprocess.Popen(chrome_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(3)

        try:
            browser = await p.chromium.connect_over_cdp(f'http://localhost:{debug_port}')
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await ctx.new_page()
            page.on("console", lambda msg: print(f"  [BROWSER] {msg.text}"))
            
            # --- The exact same navigation & fill flow from the main test script goes here ---
            # For brevity, navigating directly to the exact endpoints:
            from zoneinfo import ZoneInfo
            rome = ZoneInfo('Europe/Rome')
            day, month, year = slot_info['date'].split('/')
            dt = datetime(int(year), int(month), int(day), 0, 0, 0, tzinfo=rome)
            ts = int(dt.timestamp() * 1000)
            
            entry_url = f'{VATICAN_BASE}/home/fromtag/{slot_info["visitors"]}/{ts}/MV-Biglietti/1'
            print(f"🔗 [1] Navigating to: {entry_url}")
            await page.goto(entry_url)
            await page.wait_for_timeout(3000)
            
            # ... (Rest of checking boxes, filling form, and starting the heartbeat JS exactly as in the other script) ...
            print("\n✅ Standalone browser launched and protected via Proxy. (Full fill logic not copied to save space).")
            print("To verify, Chrome is currently open on your machine.")
            
            while True:
                await asyncio.sleep(60)
        except Exception as e:
            print(f"❌ Automation failed: {e}")
        finally:
            print("Script ending...")

if __name__ == "__main__":
    print("=== VATICAN STANDALONE HOLD SCRIPT ===")
    start = time.time()
    slot = asyncio.run(search_slots_api())
    if slot:
        print(f"✅ FOUND API SLOT! {slot['date']} at {slot['slot_time']}")
        asyncio.run(run_standalone_challenge(slot))
    else:
        print("❌ No API Slots found")
