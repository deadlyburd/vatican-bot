import asyncio
import random
import logging
import json
import os
import re
from datetime import datetime
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright
try:
    from curl_cffi.requests import AsyncSession
except ImportError:
    AsyncSession = None # Logic will handle fallback/error

# --- CONFIGURATION ---
# Default targets if not overridden by env vars
DEFAULT_DATES = [
    "26/01/2026", "27/01/2026", "28/01/2026", "29/01/2026", "30/01/2026",
    # Add more dates as needed...
]

# ⚠️ DEPRECATED: DO NOT USE HARDCODED IDs - They rotate frequently
# Always use resolve_all_dynamic_ids() to get fresh IDs
GUIDED_TOUR_ID = "1602099201"  # Fallback only
STANDARD_TICKET_ID = "1015200310"  # Fallback only
LANGUAGES = ["ENG", "ITA", "FRA", "DEU", "ESP"]

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("HydraBot")

# Session Cache File (OS-aware: works on Windows + Docker)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.environ.get("VATICAN_SESSION_FILE", os.path.join(_SCRIPT_DIR, "vatican_session.json"))

class HydraBot:
    def __init__(self, use_proxies=True):
        self.use_proxies = use_proxies
        self.proxies = self._load_proxies() if use_proxies else []
        self.target_dates = DEFAULT_DATES  # Can be updated to read from ENV
        self.session_cache = self._load_session()

    def _load_session(self):
        """Loads session cookies and ID cache from file."""
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, 'r') as f:
                    data = json.load(f)
                    logger.info(f"💾 Loaded cached session (Last Updated: {data.get('last_updated', 'Unknown')})")
                    return data
            except Exception as e:
                logger.error(f"⚠️ Failed to load session cache: {e}")
        return {"cookies": [], "ids_cache": {}, "last_updated": ""}

    def _save_session(self, cookies, ids_cache):
        """Saves current session and IDs to file."""
        try:
            from datetime import datetime
            data = {
                "cookies": cookies,
                "ids_cache": ids_cache, # Format: { "DD/MM/YYYY": [{"id":..., "name":...}] }
                "last_updated": datetime.now().isoformat()
            }
            with open(SESSION_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("💾 Session and IDs cached successfully")
            self.session_cache = data # Update in-memory
        except Exception as e:
            logger.error(f"❌ Failed to save session cache: {e}")

    async def validate_session(self):
        """
        HEADLESS CHECK: Pings API with cached cookies to see if session is valid.
        Returns: True if valid, False if expired/invalid.
        """
        if not self.session_cache.get("cookies"):
            return False

        if not AsyncSession:
            logger.warning("⚠️ curl_cffi not installed, skipping headless check")
            return False

        try:
            # Convert cookies to dict for curl_cffi
            cookie_dict = {c['name']: c['value'] for c in self.session_cache['cookies']}
            
            # Use a fast ping
            # We use an arbitrary ID just to check the session response code
            # If session is invalid, API usually returns 401 or similar, or specific JSON error
            # Actually, let's use a known ping or just check if we get a JSON response
            test_url = "https://tickets.museivaticani.va/api/visit/timeavail" # Base URL response check
            
            # Better: Use a real query if we have a cached ID
            ids = self.session_cache.get("ids_cache", {})
            if ids:
                # Pick first available date/id
                first_date = next(iter(ids))
                first_id = ids[first_date][0]['id']
                test_url = f"https://tickets.museivaticani.va/api/visit/timeavail?lang=it&visitTypeId={first_id}&visitorNum=2&visitDate={first_date}"
            else:
                # If no IDs, we can't really validat fully, but let's try generic
                return False

            async with AsyncSession(verify=False, impersonate="chrome120") as s:
                s.cookies.update(cookie_dict)
                resp = await s.get(test_url, timeout=5)
                
                if resp.status_code == 200:
                    # Double check it's not a soft-fail HTML page
                    if "timetable" in resp.text or "availability" in resp.text:
                        logger.info("✅ Cached Session is VALID (Headless Ping Success)")
                        return True
                
                logger.warning(f"⚠️ Cache Invalid: Status {resp.status_code}")
                return False

        except Exception as e:
            logger.warning(f"⚠️ Headless validation failed: {e}")
            return False

    def _load_proxies(self):
        """Loads proxies from project root or parent directories (robust path finding)"""
        proxies = []
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            
            # Possible locations for Proxy lists.json
            # 1. 2 levels up (Docker /app)
            path_2_up = os.path.dirname(os.path.dirname(current_dir))
            # 2. 3 levels up (Local Project Root)
            path_3_up = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
            # 3. 4 levels up (Just in case)
            path_4_up = os.path.dirname(path_3_up)

            search_paths = [path_2_up, path_3_up, path_4_up, "/app", "/root/travelagentbot"]
            
            base_dir = None
            for p in search_paths:
                # We prioritize the Webshare file now
                json_p = os.path.join(p, "Webshare_10_proxies.txt")
                if os.path.exists(json_p):
                    base_dir = p
                    logger.info(f"📂 Found Webshare proxies at {p}")
                    break
            
            if not base_dir:
                 # Fallback search for original JSON if text file missing
                 for p in search_paths:
                    if os.path.exists(os.path.join(p, "Proxy lists.json")):
                        base_dir = p
                        break
                 if not base_dir:
                    base_dir = path_3_up 
                    logger.warning("⚠️ Could not find proxy files, defaulting to 3 levels up")

            # 1. Webshare proxies (PRIORITY - Because Oxylabs are Firewall Blocked)
            # Correct filename: Webshare_10_proxies.txt (underscores)
            txt_path = os.path.join(base_dir, "Webshare_10_proxies.txt")
            # 1. Load from Proxy lists.json (Oxylabs Shared ISP - High Quality)
            # Confirmed working with 
            json_path = os.path.join(base_dir, "Proxy lists.json")
            if os.path.exists(json_path):
                with open(json_path, 'r') as f:
                    data = json.load(f)
                    for p in data:
                        # entryPoint is 'isp.oxylabs.io'
                        proxies.append(f"{p['entryPoint']}:{p['port']}") 
                logger.info(f"✅ Loaded {len(proxies)} Oxylabs proxies (Primary)")

            # 2. Webshare proxies (Backup)
            txt_path = os.path.join(base_dir, "Webshare_10_proxies.txt")
            if not proxies and os.path.exists(txt_path):
                 with open(txt_path, 'r') as f:
                     for line in f:
                         if line.strip() and ":" in line:
                             proxies.append(line.strip())
                 logger.info(f"✅ Loaded {len(proxies)} Webshare proxies (Backup)")
                            
            logger.info(f"✅ Loaded {len(proxies)} proxies from {base_dir}")
        except Exception as e:
            logger.error(f"⚠️ Error loading proxies: {e}")
            
        return proxies

    @asynccontextmanager
    async def get_browser(self, headless=True):
        """
        Context manager for browser lifecycle.
        
        Usage:
            async with bot.get_browser() as browser:
                page = await browser.new_page()
                # ... use page ...
        
        Args:
            headless: If False, opens visible browser (useful for debugging/Mondays)
        """
        playwright = await async_playwright().start()
        browser = None
        try:
            browser = await playwright.chromium.launch(
                headless=headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )
            yield browser
        finally:
            if browser:
                await browser.close()
            await playwright.stop()


    def get_random_proxy(self):
        if not self.proxies:
            return None
        
        p_str = random.choice(self.proxies)
        # Handle different formats
        parts = p_str.split(':')
        
        # Oxylabs format: entryPoint:port (needs username/password from env)
        if len(parts) == 2:
            # Check if this is Oxylabs (isp.oxylabs.io)
            if 'oxylabs' in p_str.lower():
                # Get credentials from ENV
                username = os.getenv('OXYLABS_USERNAME')
                password = os.getenv('OXYLABS_PASSWORD')
                
                if not username or not password:
                    return None
                
                # Shared ISP Proxies usually don't support "session-id" parameter in username
                # They are static ports.
                # So we just use raw auth.
                
                return {
                    "server": f"http://{p_str}",
                    "username": username,
                    "password": password
                }
            else:
                return {"server": f"http://{p_str}"}
        
        # Webshare format: ip:port:user:pass
        elif len(parts) == 4:
            return {
                "server": f"http://{parts[0]}:{parts[1]}",
                "username": parts[2],
                "password": parts[3]
            }
        
        return None

    async def apply_stealth(self, context, page):
        """Manually apply stealth scripts to context and page"""
        # 1. Remove webdriver
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        # 2. Mock Chrome
        await context.add_init_script("window.chrome = { runtime: {} };")
        # 3. Mock Permissions (Notification check often reveals bots)
        await context.add_init_script("""
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
            Promise.resolve({ state: 'denied' }) :
            originalQuery(parameters)
        );
        """)
        
        # 4. Canvas Noise (Ghost Browser Feature)
        await context.add_init_script("""
        const toBlob = HTMLCanvasElement.prototype.toBlob;
        const toDataURL = HTMLCanvasElement.prototype.toDataURL;
        const getImageData = CanvasRenderingContext2D.prototype.getImageData;
        
        var noise = {
            "r": Math.floor(Math.random() * 10) - 5,
            "g": Math.floor(Math.random() * 10) - 5,
            "b": Math.floor(Math.random() * 10) - 5,
            "a": Math.floor(Math.random() * 10) - 5
        };
        
        // Overwrite toDataURL
        HTMLCanvasElement.prototype.toDataURL = function() {
            const ctx = this.getContext("2d");
            if (ctx) {
                const w = this.width;
                const h = this.height;
                const iData = ctx.getImageData(0, 0, w, h);
                for (let i = 0; i < h; i++) {
                    for (let j = 0; j < w; j++) {
                        const index = ((i * (w * 4)) + (j * 4));
                        iData.data[index] = iData.data[index] + noise.r;
                        iData.data[index+1] = iData.data[index+1] + noise.g;
                        iData.data[index+2] = iData.data[index+2] + noise.b;
                        iData.data[index+3] = iData.data[index+3] + noise.a;
                    }
                }
                ctx.putImageData(iData, 0, 0);
            }
            return toDataURL.apply(this, arguments);
        }
        """)

        # 5. Resource Blocking (Aggressive Speed)
        await page.route("**/*", lambda route: route.abort() 
            if route.request.resource_type in ["image", "media", "font", "stylesheet"] 
            else route.continue_())

    async def fetch_api_ninja(self, page, ticket_id, date, lang_code=None):
        """
        Executes fetch() INSIDE the browser context.
        This inherits all the browser's cookies, TLS fingerprints, and headers automatically.
        """
        lang_param = f"&visitLang={lang_code}" if lang_code else ""
        
        js_code = f"""
        async () => {{
            const url = "https://tickets.museivaticani.va/api/visit/timeavail?lang=it{lang_param}&visitTypeId={ticket_id}&visitorNum=2&visitDate={date}";
            try {{
                const response = await fetch(url, {{
                    "headers": {{ 
                        "accept": "application/json, text/plain, */*", 
                        "x-requested-with": "XMLHttpRequest"
                    }},
                    "method": "GET"
                }});
                if (response.status !== 200) {{
                     return {{ "error": "HTTP " + response.status }};
                }}
                return await response.json();
            }} catch (e) {{ 
                return {{ "error": e.toString() }}; 
            }}
        }}
        """
        return await page.evaluate(js_code)

    async def process_results(self, label, date, data):
        """Analyzes the JSON result from the browser"""
        if "timetable" in data:
            # Filter non-sold-out
            available = [t['time'] for t in data['timetable'] if t['availability'] != 'SOLD_OUT']
            
            if available:
                logger.info(f"✅ {label} [{date}]: FOUND {len(available)} SLOTS! -> {available}")
                # TODO: Trigger Notifications/Telegram here
                if any("16:30" in t for t in available): 
                     logger.info(f"🎯 SNIPER HIT: 16:30 available for {label} on {date}!")
            else:
                pass
        elif "error" in data:
            logger.warning(f"⚠️ API Error ({label} - {date}): {data['error']}")
            
    async def resolve_id_by_tag(self, page, tag="MV-Visite-Guidate"):
        """
        Dynamically finds the Tour ID for a given tag.
        """
        logger.info(f"🔍 Resolving ID for tag: {tag}...")
        js_code = f"""
        async () => {{
            try {{
                const response = await fetch(
                    "https://tickets.museivaticani.va/api/search/resultPerTag?lang=it&visitorNum=2&visitDate={self.target_dates[0]}&volumeId=1&tag={tag}",
                    {{ "headers": {{ "accept": "application/json" }}, "method": "GET" }}
                );
                return await response.json();
            }} catch (e) {{ return {{ "error": e.toString() }}; }}
        }}
        """
        data = await page.evaluate(js_code)
        
        if "visits" in data:
             for visit in data["visits"]:
                 if visit.get("availability") != "SOLD_OUT":
                     gid = visit.get("id")
                     logger.info(f"✅ Resolved {tag} -> ID: {gid}")
                     return str(gid)
                 
             if data["visits"]:
                 gid = data["visits"][0].get("id")
                 logger.info(f"⚠️ All Sold Out, but using ID: {gid}")
                 return str(gid)
                 
        logger.warning(f"❌ Could not resolve ID for {tag}. Using fallback.")
        return None

    async def check_standard_ticket_ui(self, page, date):
        """
        Implements the User's explicit UI logic for Standard Tickets.
        Flow: Date -> Visitors -> Confirm -> Prenota (Ticket 0) -> Check Slots
        """
        try:
            logger.info(f"🖱️ UI CHECK: Standard Ticket for {date}...")
            
            # Format Date: "28/01/2026" -> "January 28," (approximate matching)
            # We need to be careful with Locale. The page usually follows the browser locale.
            # We set locale="en-US" or "it-IT" in context? Code below sets "it-IT".
            # If "it-IT", date would be "28 gennaio".
            # User snippet said: name: 'January 28,' -> This implies English locale!
            # START FIX: The container runs with "it-IT" locale in original code? 
            # Original code: locale="it-IT".
            # If user wants "January 28", we must ensure page is in English or we translate.
            # SAFE BET: The button usually has the DAY NUMBER clearly. 
            # Let's try to match by Day Number and Month if possible, OR assume user meant English.
            # Let's switch context to 'en-US' to match the snippet? 
            # Or just adapt the selector to be robust. 
            
            # User snippet: await page.getByRole('button', { name: 'January 28,' }).click();
            
            # Parsing the input date
            # DB format is usually "YYYY-MM-DD" (e.g. 2026-01-28)
            # User snippet implied "28/01/2026"
            # Let's handle both
            if "-" in date:
                year, month, day = date.split('-')
            else:
                day, month, year = date.split('/')
            
            # Navigate to generic "Biglietti" page or assume we are on a list
            # We need to start from a clean state or specific URL
            await page.goto("https://tickets.museivaticani.va/home", timeout=60000, wait_until="domcontentloaded")
            
            # RATE LIMITING: Add delay to appear human
            await page.wait_for_timeout(random.randint(1500, 3000))
            
            # Select Date
            # The calendar might need opening.
            # Assuming the user snippet runs on the DATE SELECTION step of the flow.
            # We need to click "Biglietti" first to get there?
            # Let's try direct URL to "Biglietti" DATE SELECTOR if possible.
            # URL: https://tickets.museivaticani.va/home/calendar/visit/Biglietti-Musei-Vaticani-e-Cappella-Sistina/1
            
            await page.goto("https://tickets.museivaticani.va/home/calendar/visit/Biglietti-Musei-Vaticani-e-Cappella-Sistina/1", timeout=60000, wait_until="networkidle")
            
            # RATE LIMITING: Wait for page to fully render
            await page.wait_for_timeout(random.randint(2000, 4000))
            
            # Handling Date Selection
            # The calendar is likely displayed. match the date.
            # Note: User snippet uses English text. We will try to execute that exact logic.
            # But we must be sure the month is visible.
            
            # Quick hack: Force English language
            await page.goto(page.url + "?lang=en", timeout=10000)
            
            # RATE LIMITING: Small delay after language change
            await page.wait_for_timeout(random.randint(1000, 2000))
            
            # DEBUG: Screenshot initial state
            os.makedirs("/app/screenshots", exist_ok=True)
            await page.screenshot(path=f"/app/screenshots/debug_{day}_step1_cal.png")
            logger.info(f"📸 Debug Screenshot saved: debug_{day}_step1_cal.png")

            # Convert to datetime for month comparison
            from datetime import datetime
            # Use the already split variables to avoid format issues
            dt = datetime(int(year), int(month), int(day))
            date_str = dt.strftime("%B %d").replace(" 0", " ") # January 28
            
            # Check if we need to navigate to a different month
            from datetime import datetime as dt_now
            current_month = dt_now.now().month
            target_month = int(month)
            
            # If target month is greater than current month, we need to click forward arrows
            months_ahead = target_month - current_month
            if months_ahead < 0:
                # Handle year wrap (e.g., December -> January next year)
                months_ahead += 12
            
            logger.info(f"📅 Target date: {date_str} ({months_ahead} months ahead)")
            
            # Navigate forward through months if needed
            if months_ahead > 0:
                for i in range(months_ahead):
                    try:
                        # Click the right arrow button to go to next month
                        arrow_btn = page.get_by_role('button').filter(has_text="keyboard_arrow_right")
                        await arrow_btn.click(timeout=3000)
                        await page.wait_for_timeout(1000)  # Wait for calendar to update
                        logger.info(f"➡️ Navigated forward {i+1} month(s)")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to navigate to month {i+1}: {e}")
                        break
            
            logger.info(f"🖱️ Attempting to click date: '{date_str}'")

            # Try user's selector
            try:
                # DEBUG: Log all buttons to see what we have
                buttons_text = await page.evaluate("() => Array.from(document.querySelectorAll('button')).map(b => b.textContent.trim()).join(' | ')")
                logger.info(f"🔘 VISIBLE BUTTONS: {buttons_text[:1000]}...")
                
                # First try exact "January 28"
                await page.get_by_role('button', name=date_str).click(timeout=3000)
                logger.info(f"✅ Clicked Date Button: {date_str}")
                await page.screenshot(path=f"/app/screenshots/debug_{day}_step2_clicked.png")
            except:
                logger.warning(f"⚠️ Could not click exact date '{date_str}', trying robust fallback...")
                
                # Fallback: Find any button with the DAY number.
                try:
                     # Nuclear Option: JS Click
                    was_clicked = await page.evaluate(f"""() => {{
                        const query = "{int(day)}";
                        // Broad search: Any element with text exactly matching the day
                        const allElems = Array.from(document.querySelectorAll('div, span, button, a'));
                        const dayElem = allElems.find(el => {{
                            return el.textContent.trim() === query && el.offsetParent !== null; // Visible
                        }});
                        
                        if (dayElem) {{
                            dayElem.click();
                            return "Clicked generic element for " + query;
                        }}
                        
                        // Try Partial match on Buttons
                        const buttons = Array.from(document.querySelectorAll('button'));
                        const dayBtn = buttons.find(b => {{
                             const t = b.textContent.trim();
                             return t.startsWith(query + ' ') || t === query;
                        }});
                        
                        if (dayBtn) {{
                            dayBtn.click();
                            return "Clicked button for " + query;
                        }}
                        return false;
                    }}""")
                    
                    if was_clicked:
                        logger.info(f"✅ Fallback JS Result: {was_clicked}")
                        await page.wait_for_timeout(1000)
                        await page.screenshot(path=f"/app/screenshots/debug_{day}_step2_fallback_clicked.png")
                    else:
                        raise Exception("JS could not find any element for day")
                        
                except Exception as e_fallback:
                    logger.error(f"❌ Fallback Date Click Failed: {e_fallback}")
                    await page.screenshot(path=f"/app/screenshots/debug_{day}_error_click.png")


            # Visitors
            logger.info("⏳ Waiting for #numberInput...")
            try:
                # Wait for the input to appear (it might be hidden initially)
                await page.locator('#numberInput').wait_for(state="visible", timeout=10000)
                await page.screenshot(path=f"/app/screenshots/debug_{day}_step3_visitors.png")
                await page.locator('#numberInput').click()
                await page.locator('#numberInput').fill('2')
            except Exception as e_vis:
                 logger.error(f"❌ Failed to find/click #numberInput: {e_vis}")
                 await page.screenshot(path=f"/app/screenshots/debug_{day}_error_visitors.png")
                 # Dump HTML to see what's wrong (e.g. maybe date didn't select?)
                 html = await page.content()
                 with open(f"/app/screenshots/debug_{day}_error.html", "w") as f:
                     f.write(html)
                 raise e_vis

            # Handle CONFIRM vs CONFERMA
            # It might be a small popup or modal
            try:
                await page.get_by_role('button', name='CONFIRM').click(timeout=3000)
            except:
                try:
                    await page.get_by_role('button', name='CONFERMA').click(timeout=3000)
                except:
                    logger.warning("⚠️ Could not find CONFIRM/CONFERMA button, maybe auto-advanced?")
            
            # Prenota/Book
            logger.info("🖱️ Clicking PRENOTA...")
            await page.locator('#ticket_dx_0').get_by_role('button').click(timeout=5000)
            
            # Check Results Page
            await page.wait_for_load_state("networkidle")
            await page.screenshot(path=f"/app/screenshots/debug_{day}_step4_results.png")
            
            # Scrape Slots Logic
            available_slots = []
            
            logger.info("📋 Analyzing results page for time slots...")
            
            # Helper to scrape visible times
            async def scrape_visible_times(label):
                found_times = []
                # 1. Get all text from ENABLED button elements (most likely slots)
                # We specifically check for visibility and enabled state
                slots_data = await page.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('button, .time-slot, .slot-item'));
                    return buttons.map(b => ({
                        text: b.textContent.trim(),
                        disabled: b.disabled || b.getAttribute('aria-disabled') === 'true' || b.classList.contains('disabled'),
                        visible: !!(b.offsetWidth || b.offsetHeight || b.getClientRects().length)
                    }));
                }""")
                
                import re
                time_pattern = re.compile(r'^(\d{1,2}:\d{2})$')
                
                for item in slots_data:
                    text = item['text']
                    if time_pattern.match(text):
                        if item['visible'] and not item['disabled']:
                            found_times.append(text)
                        else:
                            logger.info(f"🚫 Ignoring slot {text} (Visible: {item['visible']}, Disabled: {item['disabled']})")
                
                logger.info(f"🔎 {label}: Found {len(found_times)} valid ENABLED time slots: {found_times[:5]}")
                return found_times

            # 1. Check MATTINA / MORNING
            # User snippet: locator('div').filter({ hasText: /^POMERIGGIO$/ }).click()
            # We try to click these tabs to reveal slots
            
            # Try Morning first
            try:
                morning_btn = page.locator('div').filter(has=re.compile(r"MATTINA|MORNING", re.IGNORECASE))
                count = await morning_btn.count()
                logger.info(f"🔍 Found {count} MATTINA buttons")
                
                if count > 0:
                    # Wait for visibility
                    await morning_btn.first.wait_for(state="visible", timeout=3000)
                    logger.info("🖱️ Clicking MATTINA tab...")
                    await morning_btn.first.click()
                    await page.wait_for_timeout(random.randint(1000, 2000))
                    times = await scrape_visible_times("MATTINA")
                    available_slots.extend(times)
            except Exception as e:
                logger.warning(f"⚠️ MATTINA tab click failed: {e}")
            
            # 2. Check POMERIGGIO / AFTERNOON  
            try:
                pomeriggio_btn = page.locator('div').filter(has=re.compile(r"POMERIGGIO|AFTERNOON", re.IGNORECASE))
                count = await pomeriggio_btn.count()
                logger.info(f"🔍 Found {count} POMERIGGIO buttons")
                
                if count > 0:
                    await pomeriggio_btn.first.wait_for(state="visible", timeout=3000)
                    logger.info("🖱️ Clicking POMERIGGIO tab...")
                    await pomeriggio_btn.first.click()
                    await page.wait_for_timeout(random.randint(1000, 2000))
                    times = await scrape_visible_times("POMERIGGIO")
                    available_slots.extend(times)
            except Exception as e:
                logger.warning(f"⚠️ POMERIGGIO tab click failed: {e}")

            # Deduplicate
            available_slots = list(set(available_slots))
            
            if available_slots:
                 logger.info(f"✅ SLOT FOUND via UI Check: {available_slots}")
                 # Convert to Standard Format
                 return [{"time": t, "availability": "AVAILABLE_UI"} for t in available_slots]

            # Fallback: If tabs didn't work, just scrape ALL visible times
            logger.info("⚠️ Fallback: Scraping all visible times without tab navigation...")
            all_times = await scrape_visible_times("FALLBACK")
            if all_times:
                logger.info(f"✅ FALLBACK FOUND SLOTS: {all_times}")
                return [{"time": t, "availability": "AVAILABLE_UI"} for t in all_times]
            
            logger.info("❌ No Slots found (Sold Out view?)")
            return []
            
            
        except Exception as e:
            logger.error(f"UI Check Failed: {e}")
            await page.screenshot(path=f"/app/screenshots/debug_error_final.png")
            return []

    def get_vatican_timestamp(self, date_str):
        """
        Calculates the Vatican Midnight Timestamp (ms) for Deep Linking.
        Uses explicit Europe/Rome timezone via zoneinfo.
        """
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime
            
            rome = ZoneInfo("Europe/Rome")
            # Handle both YYYY-MM-DD and DD/MM/YYYY
            if "/" in date_str:
                dt = datetime.strptime(date_str, "%d/%m/%Y")
            else:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                
            midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=rome)
            ts = int(midnight.timestamp() * 1000)
            logger.info(f"🕒 Timestamp Calc: {date_str} -> {ts} (Midnight Rome)")
            return ts
        except Exception as e:
            logger.error(f"Timestamp calc failed: {e}")
            return 0 # Should probably fallback or error

    async def resolve_all_dynamic_ids(self, page, ticket_type, target_date, visitors=1, force_refresh=False):
        """
        Navigates to the Deep Link and extracts ALL valid `visitTypeId`s available.
        IMPORTANTLY: This also establishes the necessary session cookies for subsequent API calls.
        
        ✅ OPTIMIZATION: IDs are stable with the same JSESSIONID, so we cache them together
        ✅ 24/7 RELIABILITY: Regenerates session when cache expires or force_refresh=True
        
        Returns a list of dicts: [{"id": "123", "name": "Ticket Name"}, ...]
        
        Args:
            visitors: Number of visitors (MUST match the visitor count used in API calls!)
            force_refresh: Force regeneration of session and IDs (default: False)
        """
        try:
            # Check if we have valid cached IDs for this session
            cache_key = f"{target_date}_{visitors}_{ticket_type}"
            
            if not force_refresh and "ids_cache" in self.session_cache and cache_key in self.session_cache["ids_cache"]:
                cached_data = self.session_cache["ids_cache"][cache_key]
                cached_ids = cached_data.get('ids', [])
                cached_jsessionid = cached_data.get('jsessionid')
                cached_time = cached_data.get('timestamp', '')
                
                # Check if current page has the same JSESSIONID
                try:
                    current_cookies = await page.context.cookies()
                    current_jsessionid = None
                    for cookie in current_cookies:
                        if cookie['name'] == 'JSESSIONID':
                            current_jsessionid = cookie['value']
                            break
                    
                    if cached_ids and cached_jsessionid == current_jsessionid:
                        logger.info(f"✅ Using cached IDs ({len(cached_ids)} IDs) - JSESSIONID matches")
                        logger.info(f"   Cached at: {cached_time}")
                        return cached_ids
                    elif cached_ids:
                        logger.info(f"⚠️ Cached IDs found but JSESSIONID changed - will extract fresh IDs")
                except Exception as e:
                    logger.warning(f"⚠️ Error checking cached IDs: {e} - will extract fresh IDs")
            
            if force_refresh:
                logger.info(f"🔄 Force refresh requested - extracting fresh IDs")
            
            # ✅ CRITICAL FIX: Use the ACTUAL visitor count from the task
            # The deep link visitor count MUST match the API visitor count
            # Otherwise, the Vatican website shows different availability
            
            # Use the actual visitors parameter (from task.visitors)
            link_visitors = visitors
            
            if ticket_type == 0:
                slug = "MV-Biglietti"
            else:
                slug = "MV-Visite-Guidate"
            
            ts = self.get_vatican_timestamp(target_date)
            
            # ✅ CORRECT FORMAT: Use /fromtag/ with proper structure
            # Format: /home/fromtag/{visitors}/{timestamp}/{slug}/1
            # For standard tickets: slug = "MV-Biglietti"
            # For guided tours: slug = "MV-Visite-Guidate"
            if ticket_type == 0:
                slug = "MV-Biglietti"
            else:
                slug = "MV-Visite-Guidate"
            
            deep_url = f"https://tickets.museivaticani.va/home/fromtag/{link_visitors}/{ts}/{slug}/1"
            
            logger.info(f"🕸️ [Multi-Scan] Navigating to Deep Link: {deep_url}")
            
            # ✅ RETRY LOGIC: Try with proxy first, fallback to no-proxy if timeout
            navigation_success = False
            for attempt in range(2):
                try:
                    if attempt == 0:
                        # First attempt: Normal navigation with proxy (if enabled)
                        timeout_ms = 90000  # 90 seconds
                        logger.info(f"🔄 Attempt {attempt + 1}/2: With proxy (timeout: {timeout_ms/1000}s)")
                    else:
                        # Second attempt: Shorter timeout, will trigger fallback
                        timeout_ms = 60000  # 60 seconds
                        logger.warning(f"⚠️ Attempt {attempt + 1}/2: Retry with shorter timeout")
                    
                    await page.goto(deep_url, timeout=timeout_ms, wait_until="networkidle")
                    navigation_success = True
                    logger.info(f"✅ Navigation successful on attempt {attempt + 1}")
                    break
                    
                except Exception as nav_error:
                    if attempt == 0:
                        logger.warning(f"⚠️ Navigation timeout on attempt {attempt + 1}: {str(nav_error)[:100]}")
                        logger.info(f"🔄 Will retry with shorter timeout...")
                        await page.wait_for_timeout(5000)  # Wait 5s before retry
                    else:
                        logger.error(f"❌ Navigation failed after {attempt + 1} attempts")
                        raise
            
            if not navigation_success:
                raise Exception("Navigation failed after all retry attempts")
            
            # Additional wait for Angular to fully hydrate and API to be ready
            await page.wait_for_timeout(8000)
            
            # Verify cookies were set
            cookies = await page.context.cookies()
            logger.info(f"🍪 Session Cookies: {len(cookies)} cookies set")
            for cookie in cookies:
                logger.debug(f"   • {cookie['name']}: {cookie['value'][:30]}...")
            
            # ✅ ROBUSTNESS: Wait for tickets to surely render (Angular hydration)
            # Try multiple selectors since Angular might render different elements first
            try:
                # Wait for either the ticket container div OR the title to appear
                await page.wait_for_selector("div[id^='ticket_'], .muvaTicketTitle, [data-cy^='bookTicket_']", state="attached", timeout=25000)
                logger.info("✅ Ticket elements detected")
                
                # Give Angular more time to finish rendering all elements
                await page.wait_for_timeout(3000)
                
                # Try to expand any collapsed sections
                try:
                    await page.evaluate('''() => {
                        const expandButtons = document.querySelectorAll('[data-toggle="collapse"], .accordion-button, .btn-collapse, [aria-expanded="false"]');
                        expandButtons.forEach(btn => {
                            try {
                                btn.click();
                            } catch(e) {}
                        });
                    }''')
                    # Wait for expansions to complete
                    await page.wait_for_timeout(2000)
                    logger.info("✅ Expanded collapsed sections")
                except:
                    pass
                
                # Check if titles are visible
                title_count = await page.locator(".muvaTicketTitle").count()
                logger.info(f"✅ Found {title_count} ticket titles")
                
            except Exception as e:
                logger.warning(f"⚠️ Timeout waiting for ticket elements: {e}. Page might be empty or sold out.")
            
            # ✅ MONDAY FIX: Check if this is a Monday date (use headful mode + HTML extraction)
            from datetime import datetime
            import time
            start_time = time.time()
            
            is_monday = False
            try:
                if '/' in target_date:
                    day, month, year = target_date.split('/')
                else:
                    year, month, day = target_date.split('-')
                date_obj = datetime(int(year), int(month), int(day))
                is_monday = date_obj.weekday() == 0
                
                if is_monday:
                    logger.info("📅 MONDAY DETECTED - Using HEADFUL mode with HTML extraction")
                    logger.info("⏱️ Waiting 30 seconds for all tickets to load (including Musei Vaticani)...")
                    
                    # Wait longer for Mondays
                    await page.wait_for_timeout(30000)
                    
                    # Check how many tickets loaded
                    ticket_count = await page.evaluate('''() => {
                        return document.querySelectorAll('div[id^="ticket_"]').length;
                    }''')
                    logger.info(f"✅ Found {ticket_count} ticket containers after wait")
                    logger.info(f"⏱️ Total Monday wait time: {time.time() - start_time:.1f}s")
                else:
                    logger.info("📅 Not a Monday - using standard extraction")
            except Exception as e:
                logger.warning(f"⚠️ Monday detection failed: {e}")
                is_monday = False
            
            # Extract ticket IDs from the page with improved name detection
            # ✅ MONDAY SPECIAL: Use raw HTML parsing for better extraction
            if is_monday:
                logger.info("🔍 MONDAY MODE: Using raw HTML extraction...")
                
                # Get the full HTML content
                html_content = await page.content()
                
                # Save HTML for debugging
                try:
                    with open(f'/tmp/monday_page_{target_date.replace("/", "_")}.html', 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    logger.info(f"💾 Saved HTML to /tmp/monday_page_{target_date.replace('/', '_')}.html")
                except:
                    pass
                
                # Parse HTML to extract ALL ticket IDs and names
                import re
                ids = []
                seen_ids = set()
                
                # Pattern 1: Find all div id="ticket_XXXXX"
                ticket_pattern = re.compile(r'<div[^>]*id="ticket_(\d+)"[^>]*>', re.IGNORECASE)
                ticket_matches = ticket_pattern.finditer(html_content)
                
                for match in ticket_matches:
                    ticket_id = match.group(1)
                    if ticket_id in seen_ids or ticket_id.startswith('dx_'):
                        continue
                    
                    # Extract context around this ticket (2000 chars before and after)
                    start_pos = max(0, match.start() - 2000)
                    end_pos = min(len(html_content), match.end() + 3000)
                    context = html_content[start_pos:end_pos]
                    
                    # Try multiple patterns to find the ticket name
                    ticket_name = None
                    
                    # Pattern A: class="muvaTicketTitle"
                    name_match = re.search(r'class="muvaTicketTitle"[^>]*>([^<]+)<', context)
                    if name_match:
                        ticket_name = name_match.group(1).strip()
                    
                    # Pattern B: <h1>, <h2>, <h3> tags
                    if not ticket_name:
                        name_match = re.search(r'<h[1-6][^>]*>([^<]{10,150})<', context)
                        if name_match:
                            text = name_match.group(1).strip()
                            if '€' not in text and 'PRENOTA' not in text:
                                ticket_name = text
                    
                    # Pattern C: Any element with "title" or "Title" in class
                    if not ticket_name:
                        name_match = re.search(r'class="[^"]*[Tt]itle[^"]*"[^>]*>([^<]{10,150})<', context)
                        if name_match:
                            text = name_match.group(1).strip()
                            if '€' not in text and 'PRENOTA' not in text:
                                ticket_name = text
                    
                    # Pattern D: Look for text between > and < that looks like a title
                    if not ticket_name:
                        # Find substantial text (15-150 chars, starts with capital)
                        text_matches = re.findall(r'>([A-Z][^<]{15,150})<', context)
                        for text in text_matches:
                            text = text.strip()
                            if ('€' not in text and 'PRENOTA' not in text and 
                                'NON DISPONIBILI' not in text and 'BOOK' not in text):
                                ticket_name = text
                                break
                    
                    if ticket_name:
                        # Clean up the name
                        ticket_name = re.sub(r'\s+', ' ', ticket_name).strip()
                        ticket_name = ticket_name.replace('&nbsp;', ' ')
                        
                        ids.append({
                            'id': ticket_id,
                            'name': ticket_name
                        })
                        seen_ids.add(ticket_id)
                        logger.info(f"   📋 HTML: {ticket_id} | {ticket_name}")
                
                logger.info(f"🔢 HTML extraction found {len(ids)} tickets")
                
            else:
                # Standard JavaScript extraction for non-Monday dates
                ids = await page.evaluate('''() => {
                const results = [];
                const seenIds = new Set();
                
                console.log('🔍 Starting ticket extraction...');
                
                // STEP 1: Force expand ALL collapsible elements (critical for Mondays)
                const expandButtons = document.querySelectorAll('[data-toggle="collapse"], .accordion-button, .btn-collapse, [aria-expanded="false"], .collapsed');
                console.log(`Found ${expandButtons.length} expand buttons`);
                expandButtons.forEach(btn => {
                    try {
                        btn.click();
                    } catch(e) {}
                });
                
                // Also try to show hidden elements
                const hiddenElements = document.querySelectorAll('[style*="display: none"], [style*="display:none"], .d-none, .hidden');
                console.log(`Found ${hiddenElements.length} hidden elements`);
                hiddenElements.forEach(el => {
                    try {
                        el.style.display = 'block';
                        el.classList.remove('d-none', 'hidden');
                    } catch(e) {}
                });
                
                // STEP 2: Extract from div containers with id="ticket_XXXXX" (PRIMARY METHOD)
                const ticketContainers = document.querySelectorAll('div[id^="ticket_"]');
                console.log(`Found ${ticketContainers.length} ticket containers`);
                
                ticketContainers.forEach((container, index) => {
                    const containerId = container.getAttribute('id');
                    const ticketId = containerId ? containerId.replace('ticket_', '') : null;
                    
                    // Skip if ID is invalid or already seen
                    if (!ticketId || ticketId.startsWith('dx_') || seenIds.has(ticketId)) {
                        console.log(`Skipping container ${index}: invalid or duplicate ID`);
                        return;
                    }
                    
                    console.log(`Processing ticket ${ticketId}...`);
                    
                    // ✅ ULTRA-AGGRESSIVE TITLE SEARCH - 6 strategies
                    let ticketName = null;
                    
                    // Strategy 1: .muvaTicketTitle class (standard)
                    let titleEl = container.querySelector('.muvaTicketTitle');
                    if (titleEl && titleEl.textContent.trim()) {
                        ticketName = titleEl.textContent.trim();
                        console.log(`  Strategy 1 (muvaTicketTitle): ${ticketName}`);
                    }
                    
                    // Strategy 2: Standard heading tags
                    if (!ticketName) {
                        titleEl = container.querySelector('h1, h2, h3, h4, h5, h6');
                        if (titleEl && titleEl.textContent.trim()) {
                            ticketName = titleEl.textContent.trim();
                            console.log(`  Strategy 2 (heading): ${ticketName}`);
                        }
                    }
                    
                    // Strategy 3: app-ticket-details component
                    if (!ticketName) {
                        const detailsEl = container.querySelector('app-ticket-details');
                        if (detailsEl) {
                            titleEl = detailsEl.querySelector('.muvaTicketTitle, h1, h2, h3, h4, span[class*="title"], span[class*="Title"], div[class*="title"], div[class*="Title"]');
                            if (titleEl && titleEl.textContent.trim()) {
                                ticketName = titleEl.textContent.trim();
                                console.log(`  Strategy 3 (app-ticket-details): ${ticketName}`);
                            }
                        }
                    }
                    
                    // Strategy 4: ANY element with "title" or "Title" in class name
                    if (!ticketName) {
                        const titleElements = container.querySelectorAll('[class*="title"], [class*="Title"], [class*="name"], [class*="Name"]');
                        for (const el of titleElements) {
                            const text = el.textContent.trim();
                            if (text.length > 10 && !text.includes('€') && !text.includes('PRENOTA') && !text.includes('BOOK') && !text.includes('NON DISPONIBILI')) {
                                ticketName = text;
                                console.log(`  Strategy 4 (class name): ${ticketName}`);
                                break;
                            }
                        }
                    }
                    
                    // Strategy 5: Search ALL spans for substantial text
                    if (!ticketName) {
                        const allSpans = container.querySelectorAll('span, div, p');
                        for (const el of allSpans) {
                            const text = el.textContent.trim();
                            // Must be substantial text, not a price or button
                            if (text.length > 15 && text.length < 200 && 
                                !text.includes('€') && 
                                !text.includes('PRENOTA') && 
                                !text.includes('BOOK') && 
                                !text.includes('NON DISPONIBILI') &&
                                !text.includes('NON PRENOTABILE') &&
                                !text.match(/^\\d+$/)) {  // Not just numbers
                                ticketName = text;
                                console.log(`  Strategy 5 (span search): ${ticketName}`);
                                break;
                            }
                        }
                    }
                    
                    // Strategy 6: Get ALL text from container and extract first meaningful line
                    if (!ticketName) {
                        const allText = container.innerText || container.textContent || '';
                        const lines = allText.split('\\n')
                            .map(l => l.trim())
                            .filter(l => l.length > 15 && l.length < 200)
                            .filter(l => !l.includes('€') && !l.includes('PRENOTA') && !l.includes('BOOK'));
                        
                        if (lines.length > 0) {
                            ticketName = lines[0];
                            console.log(`  Strategy 6 (text extraction): ${ticketName}`);
                        }
                    }
                    
                    // Add to results if we found a name
                    if (ticketName && ticketName.length > 5) {
                        // Clean up the name (remove extra whitespace, newlines)
                        ticketName = ticketName.replace(/\\s+/g, ' ').trim();
                        
                        results.push({
                            id: ticketId,
                            name: ticketName
                        });
                        seenIds.add(ticketId);
                        console.log(`  ✅ Added: ${ticketId} - ${ticketName}`);
                    } else {
                        console.log(`  ❌ No name found for ${ticketId}`);
                    }
                });
                
                console.log(`After container extraction: ${results.length} tickets`);
                
                // STEP 3: Parse raw HTML for ticket IDs (FALLBACK)
                const htmlContent = document.documentElement.innerHTML;
                const ticketIdRegex = /id="ticket_(\\d+)"/g;
                let match;
                let htmlMatches = 0;
                
                while ((match = ticketIdRegex.exec(htmlContent)) !== null) {
                    const ticketId = match[1];
                    
                    if (seenIds.has(ticketId)) continue;
                    
                    // Find the ticket name near this ID in the HTML
                    const idPosition = match.index;
                    const contextStart = Math.max(0, idPosition - 1000);
                    const contextEnd = Math.min(htmlContent.length, idPosition + 3000);
                    const context = htmlContent.substring(contextStart, contextEnd);
                    
                    // Try multiple regex patterns to find the title
                    const patterns = [
                        /class="muvaTicketTitle"[^>]*>([^<]+)</,
                        /<h[1-6][^>]*>([^<]+)</,
                        /class="[^"]*[Tt]itle[^"]*"[^>]*>([^<]+)</,
                        /<span[^>]*>([A-Z][^<]{15,150})</  // Capitalized text 15-150 chars
                    ];
                    
                    for (const pattern of patterns) {
                        const titleMatch = context.match(pattern);
                        if (titleMatch) {
                            const ticketName = titleMatch[1].trim();
                            if (ticketName && ticketName.length > 10 && !ticketName.includes('€')) {
                                results.push({
                                    id: ticketId,
                                    name: ticketName
                                });
                                seenIds.add(ticketId);
                                htmlMatches++;
                                console.log(`  HTML extraction: ${ticketId} - ${ticketName}`);
                                break;
                            }
                        }
                    }
                }
                
                console.log(`HTML extraction added ${htmlMatches} tickets`);
                
                console.log(`✅ Total extracted: ${results.length} tickets`);
                return results;
            }''')
            
            # Filter duplicates if any
            unique_ids = list({v['id']: v for v in ids}.values())
            
            extraction_time = time.time() - start_time
            logger.info(f"🔢 Resolved {len(unique_ids)} Dynamic IDs from Page")
            logger.info(f"⏱️ Total extraction time: {extraction_time:.1f}s")
            
            # ✅ DEBUG: Log all ticket names found
            for item in unique_ids:
                logger.info(f"   • ID: {item['id']} | Name: {item['name']}")
            
            # ✅ CRITICAL CHECK: If we're missing Musei Vaticani on a Monday, log warning
            if is_monday:
                has_musei = any('musei' in item['name'].lower() and 'vaticani' in item['name'].lower() 
                               for item in unique_ids)
                if not has_musei:
                    logger.warning("⚠️ MONDAY ISSUE: 'Musei Vaticani' not found in extracted tickets!")
                    logger.warning(f"⚠️ Only found {len(unique_ids)} tickets - may need longer wait time")
                else:
                    logger.info("✅ Monday extraction successful - Musei Vaticani found!")
            
            # --- CACHE UPDATE ---
            # ✅ Cache IDs with JSESSIONID - they are stable together!
            # IDs are tied to the JSESSIONID and remain valid for the session
            try:
                cookies = await page.context.cookies()
                
                # Get JSESSIONID
                jsessionid = None
                for cookie in cookies:
                    if cookie['name'] == 'JSESSIONID':
                        jsessionid = cookie['value']
                        break
                
                # Cache IDs with their JSESSIONID
                if "ids_cache" not in self.session_cache:
                    self.session_cache["ids_cache"] = {}
                
                # Store IDs with JSESSIONID as key
                cache_key = f"{target_date}_{visitors}_{ticket_type}"
                self.session_cache["ids_cache"][cache_key] = {
                    'ids': unique_ids,
                    'jsessionid': jsessionid,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Save to file
                self._save_session(cookies, self.session_cache["ids_cache"])
                logger.info(f"💾 Cached {len(unique_ids)} IDs with JSESSIONID for session reuse")
            except Exception as e:
                logger.error(f"⚠️ Failed to cache session: {e}")

            return unique_ids

        except Exception as e:
            logger.error(f"❌ ID Resolution Failed: {e}")
            return []

            
            

    async def check_headless(self, date_str, ticket_type=0):
        """
        FAST PATH: Checks availability using cached session + curl_cffi.
        Returns: list of (time, link) tuples OR None if cache missing/invalid.
        """
        # 1. Validation
        if not self.session_cache.get("cookies") or not self.session_cache.get("ids_cache"):
            return None
            
        cached_ids = self.session_cache["ids_cache"].get(date_str)
        if not cached_ids:
            logger.info(f"⚠️ No cached IDs for {date_str}, switching to Browser.")
            return None
            
        try:
            # Random Proxy Selection
            proxy_url = None
            if self.proxies:
                p_str = random.choice(self.proxies)
                # Format: IP:PORT:USER:PASS or IP:PORT
                # curl_cffi needs: http://user:pass@ip:port
                try:
                    if "@" in p_str: # Already formatted?
                         proxy_url = f"http://{p_str}" if "http" not in p_str else p_str
                    elif ":" in p_str:
                        parts = p_str.split(":")
                        if len(parts) == 4: # IP:PORT:USER:PASS
                            proxy_url = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
                        elif len(parts) == 2: # IP:PORT (Likely Oxylabs)
                            if 'oxylabs' in p_str.lower():
                                user = os.getenv('OXYLABS_USERNAME')
                                pwd = os.getenv('OXYLABS_PASSWORD')
                                if user and pwd:
                                    proxy_url = f"http://{user}:{pwd}@{parts[0]}:{parts[1]}"
                                else:
                                    proxy_url = f"http://{parts[0]}:{parts[1]}"
                            else:
                                proxy_url = f"http://{parts[0]}:{parts[1]}"
                except:
                    pass
            
            # Note: We use the same session cookies, but a DIFFERENT IP.
            # Some WAFs hate this (Session IP Binding). 
            # If so, we might need to stick to the *original* proxy used for that session.
            # But usually for public sites, IP rotation on same session is tolerated or they just kill session (401).
            # Given we are "Headless", if session dies, we just get a 401/403 and the bot will auto-launch browser to refreshing.
            
            async with AsyncSession(verify=False, impersonate="chrome120", proxies={"http": proxy_url, "https": proxy_url} if proxy_url else None) as s:
                # Convert cookies to dict for curl_cffi
                cookie_dict = {c['name']: c['value'] for c in self.session_cache['cookies']}
                s.cookies.update(cookie_dict)
                s.headers.update({
                    "Referer": "https://tickets.museivaticani.va/"
                })
                
                # Check ALL cached IDs for this date
                # Ticket Type Filter: 
                # Implementation Note: Currently we treat all cached IDs as valid.
                # Ideally, we should filter by name if 'ticket_type' checks for names.
                # For now, we check ALL resolved IDs.
                
                tasks = []
                task_meta = [] # Store metadata to map response back to ID + Lang

                for item in cached_ids:
                    t_id = item['id']
                    t_name = item['name']
                    
                    # Filter by ticket type logic if needed (Standard vs Guided)
                    # Simple heuristic: "Guidat" in name vs not
                    is_guided = "Guidat" in t_name or "Guided" in t_name
                    if ticket_type == 0 and is_guided: continue # Skip guided if looking for standard
                    if ticket_type == 1 and not is_guided: continue # Skip standard if looking for guided

                    visitors = 3 if ticket_type == 0 else 2
                    
                    # Determine Languages to Check (User requires 3-letter codes)
                    # Standard -> ITA is sufficient (neutral)
                    # Guided -> Check ITA and ENG (to cover different pools/errors)
                    langs_to_check = ["ITA", "ENG"] if is_guided else ["ITA"]
                    
                    # Language Mapping (System=3-letter, API=2-letter)
                    # User specified: German is TED.
                    lang_map = {"ITA": "it", "ENG": "en", "FRA": "fr", "TED": "de", "SPA": "es"}

                    # Convert Date to DD/MM/YYYY
                    if "-" in date_str:
                         parts = date_str.split("-")
                         api_date = f"{parts[2]}/{parts[1]}/{parts[0]}"
                    else:
                         api_date = date_str
                    
                    for lang_code in langs_to_check:
                        api_lang = lang_map.get(lang_code, "en") # Default to en if unknown
                        url = f"https://tickets.museivaticani.va/api/visit/timeavail?lang={api_lang}&visitTypeId={t_id}&visitorNum={visitors}&visitDate={api_date}"
                        tasks.append(s.get(url))
                        task_meta.append({"id": t_id, "name": t_name, "lang": lang_code})
                
                if not tasks:
                    return [] # No matching IDs found in cache
                
                results = []  # Initialize results list
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                
                for i, resp in enumerate(responses):
                    if isinstance(resp, Exception):
                        continue
                        
                    meta = task_meta[i]
                    if resp.status_code == 200:
                        data = resp.json()
                        slots = [t['time'] for t in data.get('timetable', []) if t['availability'] != 'SOLD_OUT']
                        if slots:
                            t_name = meta['name']
                            lang = meta['lang']
                            logger.info(f"🎉 [HEADLESS] Found {len(slots)} slots for {t_name} ({lang.upper()}) on {date_str}")
                            # Construct result link (Generic deep link)
                            link = f"https://tickets.museivaticani.va/home/fromtag/2/123/MV-Biglietti/1" # Placeholder
                            # Store unique slots (tuple with lang info if needed, but for now just slots)
                            # We append lang to name for clarity in UI/Logs
                            results.extend([(time, link, f"{t_name} ({lang})") for time in slots])
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Headless Check Error: {e}")
            return None

    async def check_via_api_direct(self, page, ticket_id, ticket_name, visit_date, visitors, language=None):
        """
        ✅ OPTIMIZED: Call API directly with extracted IDs and cookies
        
        This method assumes:
        1. Page has already navigated to the deep link
        2. Cookies are established in the browser context
        3. We have the dynamic ticket ID
        
        Args:
            page: Playwright page object (with established session)
            ticket_id: The dynamic ticket ID
            ticket_name: Human-readable name for logging
            visit_date: Date in YYYY-MM-DD format
            visitors: Number of visitors
            language: Language code for guided tours (ENG/ITA/FRA/DEU/SPA) or None for standard tickets
            
        Returns:
            Dict with slots: {"slots": [...], "language": language, "is_guided_tour": bool}
        """
        is_guided = language is not None
        lang_str = f" ({language})" if language else ""
        logger.info(f"🌐 API Direct Check: '{ticket_name}'{lang_str} (ID: {ticket_id})")
        
        try:
            # Convert date to DD/MM/YYYY format for API
            if '-' in visit_date:
                parts = visit_date.split('-')
                api_date = f"{parts[2]}/{parts[1]}/{parts[0]}"
            elif '/' in visit_date:
                api_date = visit_date
            else:
                api_date = visit_date
            
            logger.info(f"   📅 Date: {api_date}, Visitors: {visitors}, Language: {language or 'None'}")
            
            # Ensure we're on the Vatican domain before making API call
            current_url = page.url
            if 'museivaticani.va' not in current_url:
                logger.warning(f"   ⚠️ Not on Vatican domain, current URL: {current_url}")
                return {"slots": [], "language": language, "is_guided_tour": is_guided}
            
            # Build API URL with visitLang parameter for guided tours
            visit_lang_param = language if language else ""
            
            # Call API using page.evaluate to leverage browser's session and cookies
            api_result = await page.evaluate(f'''async () => {{
                const url = '/api/visit/timeavail?lang=it&visitLang={visit_lang_param}&visitTypeId={ticket_id}&visitorNum={visitors}&visitDate=' + encodeURIComponent('{api_date}');
                
                console.log('Calling API:', url);
                console.log('Full URL:', window.location.origin + url);
                
                try {{
                    const response = await fetch(url, {{
                        method: 'GET',
                        headers: {{
                            'Accept': 'application/json',
                            'Content-Type': 'application/json'
                        }},
                        credentials: 'include'
                    }});
                    
                    console.log('Response status:', response.status);
                    
                    if (response.ok) {{
                        const data = await response.json();
                        console.log('Response data:', data);
                        return {{
                            success: true,
                            data: data,
                            status: response.status
                        }};
                    }}
                    
                    const errorText = await response.text();
                    console.error('Response not OK:', response.status, errorText);
                    return {{
                        success: false,
                        status: response.status,
                        statusText: response.statusText,
                        error: errorText
                    }};
                }} catch (e) {{
                    console.error('Fetch error:', e);
                    return {{
                        success: false,
                        error: e.toString()
                    }};
                }}
            }}''')
            
            if api_result and api_result.get('success'):
                data = api_result.get('data', {})
                timetable = data.get('timetable', [])
                
                logger.info(f"   ✅ API Response: {api_result.get('status')} - {len(timetable)} total slots")
                
                # Extract available slots
                available = [t['time'] for t in timetable if t.get('availability') != 'SOLD_OUT']
                sold_out = len(timetable) - len(available)
                
                logger.info(f"   📊 Available: {len(available)}, Sold Out: {sold_out}")
                
                if available:
                    logger.info(f"   ✅ Found {len(available)} available slots")
                    return {"slots": available, "language": language, "is_guided_tour": is_guided}
                else:
                    logger.info(f"   ❌ All slots are SOLD OUT")
                    return {"slots": [], "language": language, "is_guided_tour": is_guided}
            else:
                status = api_result.get('status', 'unknown') if api_result else 'unknown'
                error = api_result.get('error', 'Unknown error') if api_result else 'No response'
                
                # If API returns 500 or other error, it might be because the ticket ID is stale
                logger.warning(f"   ⚠️ API call failed: Status {status} - {error}")
                logger.warning(f"   ⚠️ Ticket ID might be stale, will retry with fresh IDs")
                return {"slots": [], "language": language, "is_guided_tour": is_guided, "needs_refresh": True}
                
        except Exception as e:
            logger.error(f"   ❌ API check failed: {e}")
            return {"slots": [], "language": language, "is_guided_tour": is_guided, "needs_refresh": True}
    
    async def check_via_click(self, page, ticket_id, ticket_name, ticket_index=0, visit_date=None, visitors=1):
        """
        ✅ OPTIMIZED: Uses API directly for both standard and guided tickets
        
        For standard tickets: Calls API with visitLang=""
        For guided tours: Calls API with visitLang set to each language (ENG/ITA/FRA/DEU/SPA)
        
        Args:
            page: Playwright page object
            ticket_id: The ticket ID to check
            ticket_name: Human-readable name for logging
            ticket_index: Position in list (1-based) - not used anymore
            visit_date: Date in YYYY-MM-DD format (required for API calls)
            visitors: Number of visitors (required for API calls)
            
        Returns:
            Dict with slots, detected language, and ticket type: 
            {"slots": [...], "language": "ENG" or None, "is_guided_tour": True/False}
        """
        logger.info(f"🎫 Checking '{ticket_name}' (ID: {ticket_id})...")
        
        # Detect if this is a standard ticket (no language) based on name
        name_lower = ticket_name.lower()
        
        # Check for guided tour indicators (if any present, it's a guided tour)
        is_guided_tour = any(keyword in name_lower for keyword in [
            'guidate', 'guided', 'tour', 'visite guidate', 'visita guidata'
        ])
        
        # Check for standard ticket indicators (Italian or English)
        has_standard_keywords = any(keyword in name_lower for keyword in [
            'biglietti', 'ingresso', 'admission', 'entry', 'standard entry', 'musei vaticani'
        ])
        
        # It's a standard ticket if it has standard keywords AND no guided tour keywords
        is_standard_ticket = has_standard_keywords and not is_guided_tour
        
        if not visit_date or not visitors:
            logger.error(f"   ❌ Missing visit_date or visitors - cannot check via API")
            return {"slots": [], "language": None, "is_guided_tour": not is_standard_ticket}
        
        try:
            if is_standard_ticket:
                # Standard ticket - call API once with no language
                logger.info(f"   � Standard ticket - calling API")
                return await self.check_via_api_direct(page, ticket_id, ticket_name, visit_date, visitors, language=None)
            else:
                # Guided tour - try each language
                logger.info(f"   🌐 Guided tour - trying multiple languages")
                
                languages_to_try = ["ENG", "ITA", "FRA", "DEU", "SPA"]
                
                for lang in languages_to_try:
                    logger.info(f"   🔍 Trying language: {lang}")
                    
                    result = await self.check_via_api_direct(
                        page, 
                        ticket_id, 
                        ticket_name, 
                        visit_date, 
                        visitors, 
                        language=lang
                    )
                    
                    slots = result.get('slots', [])
                    
                    if slots:
                        logger.info(f"   ✅ Found {len(slots)} slots for {lang}")
                        return result
                    else:
                        logger.info(f"   ❌ No slots for {lang}")
                
                # No language had slots
                logger.info(f"   ❌ No slots in any language")
                return {"slots": [], "language": None, "is_guided_tour": True}
                
        except Exception as e:
            logger.error(f"⚠️ Check failed: {e}")
            return {"slots": [], "language": None, "is_guided_tour": not is_standard_ticket}
    
    async def check_via_api(self, page, visit_type_id, target_date, visitors=1, language=None, visit_lang=""):
        """
        FAST: Calls /api/visit/timeavail directly using browser fetch (keeps session).
        Replaces slow UI clicking.
        
        Args:
            language: Language code for guided tours, None for standard tickets
        """
        try:
            # Format date as DD/MM/YYYY
            if "-" in target_date:
                from datetime import datetime
                dt = datetime.strptime(target_date, "%Y-%m-%d")
                api_date = dt.strftime("%d/%m/%Y")
            else:
                api_date = target_date
            
            # Map language codes
            lang_code = language.lower()[:2] if language else "it" # Default IT
            
            # API URL
            # Standard Tickets: visitLang is empty
            # Guided Tours: visitLang is required (e.g. ENG, FRA)
            visit_lang_param = f"&visitLang={visit_lang}" if visit_lang else ""
            
            # Construct URL
            url = f"https://tickets.museivaticani.va/api/visit/timeavail?lang={lang_code}{visit_lang_param}&visitTypeId={visit_type_id}&visitorNum={visitors}&visitDate={api_date}"
            
            # Execute Fetch in Browser Context
            api_js = f"""
            async () => {{
                try {{
                    const response = await fetch("{url}");
                    if (response.ok) {{
                        return await response.json();
                    }}
                    return {{error: response.status}};
                }} catch (e) {{
                    return {{error: e.message}};
                }}
            }}
            """
            
            data = await page.evaluate(api_js)
            
            if "error" in data:
                # 400/404 often means "Sold Out" or "Invalid Param", treat as empty
                # logger.warning(f"⚠️ API Error {data['error']} for ID {visit_type_id}")
                return []
            
            # Parse Slots
            time_slots = data.get("timetable", [])
            available = [t['time'] for t in time_slots if t.get('availability') != 'SOLD_OUT']
            
            if available:
                # logger.info(f"   ✅ [API] Found {len(available)} slots for {visit_type_id} ({visit_lang})")
                return available
            
            return []
                
        except Exception as e:
            logger.error(f"❌ API Check Failed: {e}")
            return []



    async def _worker_task(self, worker_id, browser, proxy_str, dates_chunk, ticket_type, language=None, name_pattern=None):
        """
        Runs a solitary 'Virtual User' using Hybrid API-based checking.
        Prioritizes HEADLESS (No Browser) if session is valid.
        Falls back to BROWSER if fresh session needed.
        
        Args:
            language: Language code for guided tours, None for standard tickets
        """
        results = []
        
        # 1. TRY HEADLESS FAST PATH
        # We try to process ALL dates in headless mode first.
        # If any fail (return None), we mark them for Browser processing.
        browser_dates = []
        
        for date in dates_chunk:
            headless_res = await self.check_headless(date, ticket_type)
            if headless_res is not None:
                # Success! (Even if empty, it means we successfully checked and found 0 slots)
                if headless_res: 
                    # Convert tuples to dicts
                    for (time, link, tname) in headless_res:
                        results.append({
                            "date": date,
                            "time": time,
                            "slots": [time],
                            "ticket_type": tname,
                            "link": link
                        })
            else:
                # Cache Miss or Invalid -> Needs Browser
                browser_dates.append(date)

        if not browser_dates:
            if results: logger.info(f"⚡ [Worker {worker_id}] Headless Check Complete! Found {len(results)} slots.")
            else: logger.info(f"⚡ [Worker {worker_id}] Headless Check Complete. No slots found.")
            return results

        # 2. SLOW PATH: BROWSER FALLBACK
        logger.info(f"🐢 [Worker {worker_id}] Switching to Browser for {len(browser_dates)} dates (Cache Miss)")
        
        # PARSE PROXY
        proxy_config = None
        try:
            if proxy_str:
                if "@" in proxy_str:
                    user_pass, ip_port = proxy_str.split("@")
                    user, pwd = user_pass.split(":")
                    proxy_config = {"server": f"http://{ip_port}", "username": user, "password": pwd}
                elif "oxylabs" in proxy_str and os.getenv('OXYLABS_USERNAME'):
                    user = os.getenv('OXYLABS_USERNAME')
                    pwd = os.getenv('OXYLABS_PASSWORD')
                    proxy_config = {"server": f"http://{proxy_str}", "username": user, "password": pwd}
                else: # IP:PORT:USER:PASS or IP:PORT
                    parts = proxy_str.split(':')
                    if len(parts) == 4:
                        proxy_config = {"server": f"http://{parts[0]}:{parts[1]}", "username": parts[2], "password": parts[3]}
                    else:
                        proxy_config = {"server": f"http://{proxy_str}"}
        except Exception as e:
            logger.error(f"❌ [Worker {worker_id}] Proxy Parse Error: {e}")
            return []

        context = None
        try:
            # 2. CREATE CONTEXT
            context = await browser.new_context(
                proxy=proxy_config,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="it-IT",
                timezone_id="Europe/Rome",
            )
            
            # Apply Stealth
            page = await context.new_page()
            await self.apply_stealth(context, page)

            # 3. PROCESS DATES (Browser)
            # Only process the dates that failed headless check
            for date in browser_dates:
                 # ... (Existing Check Logic)
                 # 3a. Resolve IDs (This will also SAVE valid session to cache!)
                 ids = await self.resolve_all_dynamic_ids(page, ticket_type, date)
                 
                 for item in ids:
                     v_id = item['id']
                     tname = item['name']
                     
                     # Filter Logic (Standard vs Guided) based on Name or Task Type
                     is_guided = "Guidat" in tname or "Guided" in tname
                     if ticket_type == 0 and is_guided: continue 
                     if ticket_type == 1 and not is_guided: continue

                     # 3b. API Check
                     visit_lang = language[:2] if ticket_type == 1 else ""
                     slots = await self.check_via_api(page, v_id, date, visitors=2, language=language, visit_lang=visit_lang)
                     
                     if slots:
                         logger.info(f"🎉 [Worker] Found {len(slots)} slots for {tname} on {date}")
                         results.append({
                            "date": date,
                            "time": slots[0],
                            "slots": slots,
                            "ticket_type": tname,
                            "link": f"https://tickets.museivaticani.va/home/fromtag/2/123/MV-Biglietti/1"
                        })

        except Exception as e:
            logger.error(f"❌ [Worker {worker_id}] Browser Task Failed: {e}")
        finally:
            if context: await context.close()
            
        return results



    async def run_once(self, ticket_type=0, language=None, name_pattern=None):
        """
        Executes a PARALLEL TURBO pass.
        Launches 1 Browser, then N Contexts (Workers).
        Shards dates among available proxies.
        
        Args:
            ticket_type: 0 for standard, 1 for guided tours
            language: Language code (ENG/ITA/etc.) for guided tours, None for standard
            name_pattern: Optional pattern to filter ticket names
        """
        results_map = {} # Maps date -> status
        
        # If no proxies, we can't do sharding effectively, but we try with 1
        worker_proxies = self.proxies if self.proxies else [None]
        
        async with async_playwright() as p:
            # 1. Launch One Heavy Browser
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--hide-scrollbars",
                    "--disable-dev-shm-usage" # RAM optimization
                ]
            )
            
            logger.info(f"🚀 [TURBO] Browser Launched. Spawning Workers for {len(self.target_dates)} dates...")
            
            try:
                # 2. Assign Dates to Proxies (Sharding)
                tasks = []
                # Cap max workers to avoid overload
                max_workers = 10
                actual_workers = min(len(worker_proxies), max_workers, len(self.target_dates))
                if actual_workers < 1: actual_workers = 1
                
                # Round Robin distribution
                chunks = [[] for _ in range(actual_workers)]
                for i, date in enumerate(self.target_dates):
                    chunks[i % actual_workers].append(date)
                    
                for i in range(actual_workers):
                    if not chunks[i]: continue
                    proxy = worker_proxies[i % len(worker_proxies)]
                    # Spawn Worker
                    tasks.append(self._worker_task(i, browser, proxy, chunks[i], ticket_type, language, name_pattern))
                    
                logger.info(f"⚡ Launching {len(tasks)} Parallel Workers...")
                
                # 3. Gather Results
                worker_results = await asyncio.gather(*tasks)
                
                # 4. Aggregate
                for date in self.target_dates:
                    results_map[date] = [] 
                    
                found_any = False
                for w_res in worker_results:
                    for item in w_res:
                        d = item['date']
                        slots = item['slots']
                        v_id = item.get('id_used')
                        
                        # Find name from resolved IDs if possible?
                        # _worker_task appends dict with id_used. 
                        # Ideally we want the name too.
                        # Let's check _worker_task return structure.
                        # It returns: { "date":..., "id_used":..., "slots":..., "name":... } -> We need to add "name" to _worker_task first.
                        
                        rich_data = {
                            "slots": slots,
                            "id": v_id,
                            "name": item.get('name', 'Unknown')
                        }
                        
                        if d in results_map:
                            results_map[d].append(rich_data)
                        else:
                            results_map[d] = [rich_data]
                        
                        if slots: found_any = True

                logger.info(f"🏁 Turbo Cycle Complete. Found Availability: {found_any}")
                return results_map

            except Exception as e:
                logger.error(f"Single Pass Failed: {e}")
                import traceback
                traceback.print_exc()
                return {"error": str(e)}
            finally:
                if browser: await browser.close()

    async def run_hydra_cycle(self):
        """Main loop for the bot (Persistent Monitoring with Rotation)"""
        logger.info(f"🐉 HYDRA STARTING | Monitoring {len(self.target_dates)} dates")
        
        while True:
            # 1. Pick a Proxy for this session
            proxy_config = self.get_random_proxy()
            proxy_display = proxy_config['server'] if proxy_config else "DIRECT"
            logger.info(f"� ROTATION: New Session with Proxy: {proxy_display}")

            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        headless=True,
                        proxy=proxy_config,
                        args=[
                            "--no-sandbox",
                            "--disable-blink-features=AutomationControlled",
                            "--disable-infobars",
                            "--hide-scrollbars", 
                            "--disable-gpu", 
                        ]
                    )

                    context = await browser.new_context(
                        locale="it-IT",
                        timezone_id="Europe/Rome",
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    )

                    page = await context.new_page()
                    await self.apply_stealth(context, page)

                    logger.info("⏳ Warming Session...")
                    # Targeted Warming
                    try:
                        await page.goto(f"https://tickets.museivaticani.va/home/details/{STANDARD_TICKET_ID}", timeout=60000, wait_until="domcontentloaded")
                    except:
                        logger.warning("Targeted warming timeout, proceeding anyway...")

                    # Run for X cycles before rotating proxy to avoid detection patterns
                    # If we just do 1 loop, it's very safe but higher overhead.
                    # Let's do 5 loops (approx 2-3 mins) then rotate.
                    CYCLES_PER_SESSION = 5
                    
                    for i in range(CYCLES_PER_SESSION):
                        logger.info(f"📍 Cycle {i+1}/{CYCLES_PER_SESSION} for this session")
                        
                        start_time = asyncio.get_event_loop().time()
                        
                        for date in self.target_dates:
                            # 1. Check Standard Ticket (UI LOGIC)
                            std_results = await self.check_standard_ticket_ui(page, date)
                            await self.process_results("STD-UI", date, std_results)
                            
                            # 2. Check Guided Tours (API NINJA LOGIC)
                            tasks = []
                            resolved_id = GUIDED_TOUR_ID 
                            for lang in LANGUAGES:
                                tasks.append(self.fetch_api_ninja(page, resolved_id, date, lang))
                            
                            guided_results = await asyncio.gather(*tasks)
                            for i, lang in enumerate(LANGUAGES):
                                await self.process_results(f"GUIDED-{lang}", date, guided_results[i])
                                
                            await asyncio.sleep(1) # Gap between dates

                        elapsed = asyncio.get_event_loop().time() - start_time
                        logger.info(f"💤 Cycle processed in {elapsed:.2f}s. Resting...")
                        await asyncio.sleep(random.uniform(20, 40))

                    logger.info("♻️ Session Finished. Rotating Proxy...")
                    await browser.close()
            
            except Exception as e:
                 logger.error(f"💥 Critical Error in Session: {e}. Restarting session immediately.")
                 await asyncio.sleep(5) # Brief pause before retry


if __name__ == "__main__":
    bot = HydraBot(use_proxies=True)
    asyncio.run(bot.run_hydra_cycle())
