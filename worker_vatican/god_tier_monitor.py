"""
God-Tier Vatican Monitor
========================
Fully automated ticket monitoring with:
- Automatic session validation & refresh
- Headless HTTP mode (99% of time) 
- Browser fallback only when needed
- Concurrency limiting & rate limiting
- Auto-retry with exponential backoff
"""

import asyncio
import json
import logging
import os
import random
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from curl_cffi.requests import AsyncSession

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("GodTierVatican")

# Constants
# Use script directory for session file (works on Windows + Docker)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.environ.get("VATICAN_SESSION_FILE", os.path.join(_SCRIPT_DIR, "vatican_session.json"))
CACHE_MAX_AGE_HOURS = 12  # Refresh session every 12 hours (extended for stability)
CONCURRENT_REQUESTS = 8   # Max parallel API calls
RATE_LIMIT_RPS = 10      # Max requests per second
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 1.0   # seconds


class GodTierVaticanMonitor:
    """
    Ultra-fast Vatican ticket monitor.
    Uses headless HTTP mode with automatic browser fallback.
    """
    
    def __init__(self, proxies: List[str] = None, sticky_proxy: bool = True):
        self.proxies = proxies or self._load_proxies()
        self.session_cache = self._load_session()
        self.semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
        self.rate_limit_delay = 1.0 / RATE_LIMIT_RPS
        self.last_request_time = 0
        
        # ✅ STICKY PROXY: Use same proxy for entire session
        self.sticky_proxy = sticky_proxy
        self.current_proxy = None
        if sticky_proxy and self.proxies:
            self.current_proxy = random.choice(self.proxies)
            logger.info(f"🎯 Sticky Proxy Selected: {self.current_proxy.split(':')[0]}:***")
        
    def _load_proxies(self) -> List[str]:
        """Load proxies from environment or files."""
        proxies = []
        try:
            # Check environment variable first
            proxy_env = os.getenv('PROXY_LIST')
            if proxy_env:
                return proxy_env.split(',')
            
            # Try to load from files
            search_paths = ["/app", ".", "..", "../.."]
            for base_dir in search_paths:
                # Webshare format
                txt_path = os.path.join(base_dir, "Webshare_10_proxies.txt")
                if os.path.exists(txt_path):
                    with open(txt_path, 'r') as f:
                        for line in f:
                            if line.strip() and ":" in line:
                                proxies.append(line.strip())
                    logger.info(f"✅ Loaded {len(proxies)} Webshare proxies")
                    return proxies
                
                # Oxylabs JSON format
                json_path = os.path.join(base_dir, "Proxy lists.json")
                if os.path.exists(json_path):
                    with open(json_path, 'r') as f:
                        data = json.load(f)
                        for p in data:
                            entry = f"{p['entryPoint']}:{p['port']}"
                            proxies.append(entry)
                    logger.info(f"✅ Loaded {len(proxies)} Oxylabs proxies")
                    return proxies
                    
        except Exception as e:
            logger.warning(f"⚠️ Could not load proxies: {e}")
        
        return proxies
    
    def _load_session(self) -> Dict:
        """Load cached session from file."""
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, 'r') as f:
                    data = json.load(f)
                    # Check age
                    last_updated = data.get('last_updated', '')
                    if last_updated:
                        last_dt = datetime.fromisoformat(last_updated)
                        age_hours = (datetime.now() - last_dt).total_seconds() / 3600
                        if age_hours < CACHE_MAX_AGE_HOURS:
                            logger.info(f"💾 Loaded fresh session (age: {age_hours:.1f}h)")
                            return data
                        else:
                            logger.info(f"⏰ Session expired (age: {age_hours:.1f}h)")
                    return data
            except Exception as e:
                logger.error(f"⚠️ Failed to load session: {e}")
        return {"cookies": [], "ids_cache": {}, "last_updated": ""}
    
    def _save_session(self, cookies: List[Dict], ids_cache: Dict):
        """Save session to file."""
        try:
            data = {
                "cookies": cookies,
                "ids_cache": ids_cache,
                "last_updated": datetime.now().isoformat()
            }
            os.makedirs(os.path.dirname(SESSION_FILE) or ".", exist_ok=True)
            with open(SESSION_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("💾 Session cached successfully")
            self.session_cache = data
        except Exception as e:
            logger.error(f"❌ Failed to save session: {e}")
    
    def _get_proxy_url(self, proxy_str: str) -> Optional[str]:
        """Convert proxy string to URL format for curl_cffi."""
        if not proxy_str:
            return None
        try:
            if "@" in proxy_str:
                return f"http://{proxy_str}" if "http" not in proxy_str else proxy_str
            elif ":" in proxy_str:
                parts = proxy_str.split(':')
                if len(parts) == 4:  # IP:PORT:USER:PASS
                    return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
                elif len(parts) == 2:  # IP:PORT (Oxylabs)
                    if 'oxylabs' in proxy_str.lower():
                        user = os.getenv('OXYLABS_USERNAME')
                        pwd = os.getenv('OXYLABS_PASSWORD')
                        if user and pwd:
                            return f"http://{user}:{pwd}@{parts[0]}:{parts[1]}"
                    return f"http://{parts[0]}:{parts[1]}"
        except Exception as e:
            logger.warning(f"⚠️ Proxy parse error: {e}")
        return None
    
    async def _rate_limited_request(self, session: AsyncSession, url: str, max_retries: int = RETRY_MAX_ATTEMPTS) -> Optional[Dict]:
        """Make rate-limited request with retry logic."""
        async with self.semaphore:  # Limit concurrency
            for attempt in range(max_retries):
                try:
                    # Rate limiting
                    now = time.time()
                    time_since_last = now - self.last_request_time
                    if time_since_last < self.rate_limit_delay:
                        await asyncio.sleep(self.rate_limit_delay - time_since_last)
                    
                    self.last_request_time = time.time()
                    
                    resp = await session.get(url, timeout=10)
                    
                    if resp.status_code == 200:
                        return resp.json()
                    elif resp.status_code in (401, 403):
                        logger.warning(f"🚫 Session expired (status {resp.status_code})")
                        return None  # Trigger session refresh
                    elif resp.status_code == 429:
                        wait_time = (attempt + 1) * RETRY_BASE_DELAY * 2
                        logger.warning(f"⏳ Rate limited, waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.debug(f"⚠️ HTTP {resp.status_code} for {url}")
                        
                except Exception as e:
                    wait_time = (attempt + 1) * RETRY_BASE_DELAY
                    logger.debug(f"⚠️ Request failed (attempt {attempt+1}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
            
            return None
    
    async def validate_session(self) -> bool:
        """Quick check if session cookies are still valid."""
        if not self.session_cache.get("cookies"):
            return False
        
        # Try a lightweight API call
        cookie_dict = {c['name']: c['value'] for c in self.session_cache['cookies']}
        
        try:
            async with AsyncSession(verify=False, impersonate="chrome120") as s:
                s.cookies.update(cookie_dict)
                s.headers.update({
                    "Referer": "https://tickets.museivaticani.va/",
                    "Accept": "application/json"
                })
                
                # Use home page as validation (lightweight)
                resp = await s.get("https://tickets.museivaticani.va/home", timeout=5)
                return resp.status_code == 200
                
        except Exception as e:
            logger.debug(f"Session validation failed: {e}")
            return False
    
    async def refresh_session_with_browser(self, ticket_type: int = 0, target_date: str = "27/02/2026", visitors: int = 2) -> bool:
        """
        Use Playwright browser to get fresh session cookies and IDs.
        Only called when headless mode fails.
        """
        if not HAS_PLAYWRIGHT:
            logger.error("❌ Playwright not installed, cannot refresh session")
            return False
        
        logger.info("🔄 Refreshing session with browser...")
        
        try:
            async with async_playwright() as p:
                # Use sticky proxy if enabled
                if self.sticky_proxy and self.current_proxy:
                    proxy = self.current_proxy
                    logger.info(f"🎯 Browser using sticky proxy: {proxy.split(':')[0]}")
                else:
                    proxy = random.choice(self.proxies) if self.proxies else None
                proxy_config = None
                
                if proxy and ":" in proxy:
                    parts = proxy.split(':')
                    if len(parts) == 4:
                        proxy_config = {
                            "server": f"http://{parts[0]}:{parts[1]}",
                            "username": parts[2],
                            "password": parts[3]
                        }
                    elif len(parts) == 2 and 'oxylabs' in proxy.lower():
                        user = os.getenv('OXYLABS_USERNAME')
                        pwd = os.getenv('OXYLABS_PASSWORD')
                        if user and pwd:
                            proxy_config = {
                                "server": f"http://{proxy}",
                                "username": user,
                                "password": pwd
                            }
                
                browser = await p.chromium.launch(
                    headless=True,
                    proxy=proxy_config,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage"
                    ]
                )
                
                context = await browser.new_context(
                    locale="it-IT",
                    timezone_id="Europe/Rome",
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                
                page = await context.new_page()
                
                # Apply stealth scripts
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    window.chrome = { runtime: {} };
                """)
                
                # Navigate to deep link
                from zoneinfo import ZoneInfo
                from datetime import datetime as dt
                
                if "/" in target_date:
                    day, month, year = target_date.split('/')
                    dt_obj = dt(int(year), int(month), int(day))
                else:
                    dt_obj = dt.strptime(target_date, "%Y-%m-%d")
                
                rome = ZoneInfo("Europe/Rome")
                midnight = dt_obj.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=rome)
                ts = int(midnight.timestamp() * 1000)
                
                slug = "MV-Biglietti" if ticket_type == 0 else "MV-Visite-Guidate"
                # Use the visitors parameter passed to the function
                deep_url = f"https://tickets.museivaticani.va/home/fromtag/{visitors}/{ts}/{slug}/1"
                
                logger.info(f"🕸️ Navigating to: {deep_url}")
                await page.goto(deep_url, timeout=45000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                
                # Extract cookies
                cookies = await context.cookies()
                
                # Extract ticket IDs with improved DOM traversal
                ids = await page.evaluate("""
                    () => {
                        const results = [];
                        
                        // Step 1: Get all ticket titles
                        const titles = [];
                        document.querySelectorAll('.muvaTicketTitle').forEach(el => {
                            titles.push({
                                text: el.textContent.trim(),
                                element: el
                            });
                        });
                        
                        // Step 2: Get all buttons with IDs
                        const buttons = [];
                        document.querySelectorAll('[data-cy^="bookTicket_"]').forEach(btn => {
                            const dataCy = btn.getAttribute('data-cy');
                            const id = dataCy ? dataCy.split('_')[1] : null;
                            buttons.push({
                                id: id,
                                element: btn
                            });
                        });
                        
                        // Step 3: Try to match titles with buttons
                        titles.forEach(titleInfo => {
                            const titleEl = titleInfo.element;
                            let matchedButton = null;
                            
                            // Try to find button in same container
                            let container = titleEl.closest('app-ticket-card') || 
                                           titleEl.closest('.card') || 
                                           titleEl.closest('.ticket-container') ||
                                           titleEl.closest('[class*="ticket"]') ||
                                           titleEl.closest('div[class*="muva"]');
                            
                            if (container) {
                                const btn = container.querySelector('[data-cy^="bookTicket_"]');
                                if (btn) {
                                    const dataCy = btn.getAttribute('data-cy');
                                    matchedButton = dataCy ? dataCy.split('_')[1] : null;
                                }
                            }
                            
                            if (matchedButton) {
                                results.push({
                                    id: matchedButton,
                                    name: titleInfo.text
                                });
                            }
                        });
                        
                        // Step 4: For unmatched buttons, search up parent tree
                        buttons.forEach(btnInfo => {
                            const alreadyMatched = results.some(r => r.id === btnInfo.id);
                            if (alreadyMatched) return;
                            
                            const btn = btnInfo.element;
                            let name = 'Unknown';
                            
                            // Search up to 10 parent levels
                            let parent = btn.parentElement;
                            for (let i = 0; i < 10 && parent; i++) {
                                const titleEl = parent.querySelector('.muvaTicketTitle, h1, h2, h3, h4, .card-title, [class*="title"], [class*="Title"]');
                                if (titleEl && titleEl.textContent.trim()) {
                                    name = titleEl.textContent.trim();
                                    break;
                                }
                                parent = parent.parentElement;
                            }
                            
                            results.push({
                                id: btnInfo.id,
                                name: name
                            });
                        });
                        
                        return results;
                    }
                """)
                
                await browser.close()
                
                if ids:
                    ids_cache = {target_date: ids}
                    self._save_session(cookies, ids_cache)
                    logger.info(f"✅ Session refreshed! Got {len(ids)} ticket IDs")
                    return True
                else:
                    logger.error("❌ No ticket IDs found during refresh")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Browser refresh failed: {e}")
            return False
    
    async def check_availability_headless(
        self, 
        date_str: str, 
        ticket_type: int = 0,
        languages: List[str] = None,
        visitors: int = 2
    ) -> List[Dict]:
        """
        Check ticket availability using headless HTTP mode.
        Automatically refreshes session if needed.
        """
        results = []
        
        # Validate session first
        if not await self.validate_session():
            logger.info("⏰ Session invalid, refreshing...")
            if not await self.refresh_session_with_browser(ticket_type, date_str, visitors=visitors):
                logger.error("❌ Failed to refresh session")
                return results
        
        # Get cached IDs
        cached_ids = self.session_cache.get("ids_cache", {}).get(date_str, [])
        if not cached_ids:
            logger.info(f"🔍 No cached IDs for {date_str}, harvesting...")
            if not await self.refresh_session_with_browser(ticket_type, date_str, visitors=visitors):
                return results
            cached_ids = self.session_cache.get("ids_cache", {}).get(date_str, [])
        
        if not cached_ids:
            logger.error("❌ No ticket IDs available")
            return results
        
        # Prepare date format
        if "-" in date_str:
            parts = date_str.split("-")
            api_date = f"{parts[2]}/{parts[1]}/{parts[0]}"
        else:
            api_date = date_str
        
        # Language setup
        lang_map = {"ITA": "it", "ENG": "en", "FRA": "fr", "DEU": "de", "SPA": "es", "TED": "de"}
        if not languages:
            languages = ["ITA", "ENG"] if ticket_type == 1 else ["ITA"]
        
        # Get proxy (sticky or random)
        proxy_url = None
        if self.proxies:
            if self.sticky_proxy and self.current_proxy:
                proxy_str = self.current_proxy  # Use same proxy for session
                logger.debug(f"🎯 Using sticky proxy: {proxy_str.split(':')[0]}")
            else:
                proxy_str = random.choice(self.proxies)  # Random rotation
            proxy_url = self._get_proxy_url(proxy_str)
        
        # Build requests
        cookie_dict = {c['name']: c['value'] for c in self.session_cache['cookies']}
        
        async with AsyncSession(
            verify=False, 
            impersonate="chrome120",
            proxies={"http": proxy_url, "https": proxy_url} if proxy_url else None
        ) as session:
            session.cookies.update(cookie_dict)
            session.headers.update({
                "Referer": "https://tickets.museivaticani.va/",
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest"
            })
            
            # Build all URLs to check
            check_tasks = []
            check_meta = []
            
            for item in cached_ids:
                t_id = item['id']
                t_name = item['name']
                
                # Filter by ticket type
                is_guided = "Guidat" in t_name or "Guided" in t_name
                if ticket_type == 0 and is_guided:
                    continue
                if ticket_type == 1 and not is_guided:
                    continue
                
                # Use the visitors parameter passed to the function
                
                for lang_code in languages:
                    api_lang = lang_map.get(lang_code, "en")
                    
                    # Add visitLang for guided tours
                    visit_lang_param = f"&visitLang={lang_code}" if is_guided else ""
                    
                    url = (
                        f"https://tickets.museivaticani.va/api/visit/timeavail"
                        f"?lang={api_lang}{visit_lang_param}"
                        f"&visitTypeId={t_id}&visitorNum={visitors}&visitDate={api_date}"
                    )
                    
                    check_tasks.append(self._rate_limited_request(session, url))
                    check_meta.append({
                        "id": t_id,
                        "name": t_name,
                        "lang": lang_code,
                        "date": date_str
                    })
            
            # Execute all requests
            logger.info(f"🚀 Checking {len(check_tasks)} ticket/language combinations...")
            responses = await asyncio.gather(*check_tasks, return_exceptions=True)
            
            # Process results
            for i, resp_data in enumerate(responses):
                if isinstance(resp_data, Exception):
                    continue
                
                if resp_data is None:
                    # Session might have expired during requests
                    continue
                
                meta = check_meta[i]
                timetable = resp_data.get("timetable", [])
                
                available_slots = [
                    {"time": t['time'], "availability": t['availability']}
                    for t in timetable
                    if t.get('availability') != 'SOLD_OUT'
                ]
                
                if available_slots:
                    results.append({
                        "ticket_id": meta['id'],
                        "ticket_name": meta['name'],
                        "language": meta['lang'],
                        "date": meta['date'],
                        "slots": available_slots,
                        "total_slots": len(timetable),
                        "available_count": len(available_slots)
                    })
                    logger.info(
                        f"🎉 FOUND: {meta['name']} ({meta['lang']}) - "
                        f"{len(available_slots)} slots on {meta['date']}"
                    )
        
        return results
    
    async def monitor_dates(
        self,
        dates: List[str],
        ticket_type: int = 0,
        interval_seconds: int = 30,
        max_cycles: int = None
    ):
        """
        Continuous monitoring loop.
        
        Args:
            dates: List of dates to monitor (DD/MM/YYYY format)
            ticket_type: 0 = Standard, 1 = Guided
            interval_seconds: Time between checks
            max_cycles: None = infinite, or number of cycles
        """
        cycle = 0
        
        logger.info("=" * 60)
        logger.info("🐉 GOD-TIER VATICAN MONITOR STARTED")
        logger.info("=" * 60)
        logger.info(f"📅 Dates: {dates}")
        logger.info(f"🎫 Ticket Type: {'Standard' if ticket_type == 0 else 'Guided'}")
        logger.info(f"⏱️  Interval: {interval_seconds}s")
        logger.info(f"🌐 Proxies: {len(self.proxies)} available")
        logger.info("=" * 60)
        
        while True:
            cycle += 1
            if max_cycles and cycle > max_cycles:
                logger.info(f"🏁 Completed {max_cycles} cycles")
                break
            
            logger.info(f"\n📍 Cycle {cycle} | {datetime.now().strftime('%H:%M:%S')}")
            start_time = time.time()
            
            try:
                for date in dates:
                    results = await self.check_availability_headless(
                        date_str=date,
                        ticket_type=ticket_type
                    )
                    
                    if results:
                        logger.info(f"✅ {date}: Found availability!")
                        for r in results:
                            slots_str = ", ".join([s['time'] for s in r['slots'][:5]])
                            if len(r['slots']) > 5:
                                slots_str += f" (+{len(r['slots']) - 5} more)"
                            logger.info(f"   🎫 {r['ticket_name']} ({r['language']}): {slots_str}")
                            
                            # TODO: Add notification logic here (Telegram, webhook, etc.)
                            # await self.send_notification(r)
                    else:
                        logger.info(f"❌ {date}: No availability")
                
                elapsed = time.time() - start_time
                sleep_time = max(0, interval_seconds - elapsed)
                
                if sleep_time > 0:
                    logger.info(f"💤 Sleeping {sleep_time:.1f}s...")
                    await asyncio.sleep(sleep_time)
                    
            except Exception as e:
                logger.error(f"💥 Cycle error: {e}")
                await asyncio.sleep(5)  # Brief pause before retry


async def main():
    """Example usage."""
    # Initialize monitor
    monitor = GodTierVaticanMonitor()
    
    # Dates to monitor
    dates = [
        "10/02/2026",
        "11/02/2026", 
        "12/02/2026",
        "13/02/2026",
        "14/02/2026",
    ]
    
    # Start monitoring
    await monitor.monitor_dates(
        dates=dates,
        ticket_type=0,  # Standard tickets
        interval_seconds=30,  # Check every 30 seconds
        max_cycles=None  # Run forever (or set a number)
    )


if __name__ == "__main__":
    asyncio.run(main())
