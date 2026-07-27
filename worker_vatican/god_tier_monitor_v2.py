"""
God-Tier Vatican Monitor V2
===========================
Fixed version with:
- Proper API session validation
- Correct cookie handling for HTTP API
- Better error handling and logging
- Playwright for ID extraction (required for dynamic content)
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
    logger.warning("⚠️ Playwright not available - ID harvesting will fail")

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("GodTierVaticanV2")

# Constants
# Use script directory for session file (works on Windows + Docker)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.environ.get("VATICAN_SESSION_FILE", os.path.join(_SCRIPT_DIR, "vatican_session.json"))
CACHE_MAX_AGE_HOURS = 4  # 4 hours as per working configuration
CONCURRENT_REQUESTS = 8
RATE_LIMIT_RPS = 10
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 1.0


class GodTierVaticanMonitorV2:
    """
    Ultra-fast Vatican ticket monitor with fixed session handling.
    Uses curl_cffi for API checks and Playwright for ID extraction.
    """
    
    def __init__(self, proxies: List[str] = None, sticky_proxy: bool = True):
        self.proxies = proxies if proxies is not None else self._load_proxies()
        self.session_cache = self._load_session()
        # Allow runtime overrides for bandwidth control
        try:
            conc_override = int(os.getenv("VATICAN_CONCURRENCY", "").strip())
        except Exception:
            conc_override = 0
        try:
            rps_override = float(os.getenv("VATICAN_RPS", "").strip())
        except Exception:
            rps_override = 0.0
        effective_concurrency = conc_override if conc_override > 0 else CONCURRENT_REQUESTS
        effective_rps = rps_override if rps_override > 0 else RATE_LIMIT_RPS
        self.semaphore = asyncio.Semaphore(effective_concurrency)
        self.rate_limit_delay = 1.0 / max(effective_rps, 1.0)
        self.last_request_time = 0
        
        # Sticky proxy
        self.sticky_proxy = sticky_proxy
        self.current_proxy = None
        if sticky_proxy and self.proxies:
            self.current_proxy = random.choice(self.proxies)
            logger.info(f"🔒 Sticky Proxy: {self.current_proxy.split(':')[0]}:***")
        
    def _load_proxies(self) -> List[str]:
        """Load proxies from environment or files."""
        proxies = []
        try:
            proxy_env = os.getenv('PROXY_LIST')
            if proxy_env:
                return proxy_env.split(',')
            
            base_here = os.path.dirname(os.path.abspath(__file__))
            search_paths = [
                _SCRIPT_DIR,             # Look in current script dir first (worker_vatican)
                ".",                    # Then root
                "..",                   # Then parent
                "/app"                  # Then docker container path
            ]
            for base_dir in search_paths:
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
                    last_updated = data.get('last_updated', '')
                    if last_updated:
                        last_dt = datetime.fromisoformat(last_updated)
                        age_hours = (datetime.now() - last_dt).total_seconds() / 3600
                        if age_hours < CACHE_MAX_AGE_HOURS:
                            logger.info(f"📂 Loaded cached session (age: {age_hours:.1f}h)")
                            return data
                        else:
                            logger.info(f"⏰ Session expired (age: {age_hours:.1f}h)")
                    return data
            except Exception as e:
                logger.error(f"❌ Failed to load session: {e}")
        return {"cookies": [], "ids_cache": {}, "last_updated": ""}
    
    def _save_session(self, cookies: List[Dict], new_ids_dict: Dict):
        """Save session to file, merging IDs into existing cache."""
        try:
            # Deep merge new IDs into the existing cache list-by-list
            existing_cache = self.session_cache.get("ids_cache", {})
            
            for date_key, fresh_list in new_ids_dict.items():
                current_list = existing_cache.get(date_key, [])
                # Create a set of existing IDs for de-duplication
                seen_ids = {str(item.get('id', '')) for item in current_list if item.get('id')}
                
                # Append only new ones
                for item in fresh_list:
                    if str(item.get('id', '')) not in seen_ids:
                        current_list.append(item)
                        seen_ids.add(str(item.get('id', '')))
                
                existing_cache[date_key] = current_list
            
            data = {
                "cookies": cookies,
                "ids_cache": existing_cache,
                "last_updated": datetime.now().isoformat()
            }
            os.makedirs(os.path.dirname(SESSION_FILE) or ".", exist_ok=True)
            with open(SESSION_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"💾 Session cached successfully (IDs tracked: {len(existing_cache.get('__ALL__', []))})")
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
                if len(parts) == 4:
                    return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
                elif len(parts) == 2:
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
        async with self.semaphore:
            for attempt in range(max_retries):
                try:
                    now = time.time()
                    time_since_last = now - self.last_request_time
                    if time_since_last < self.rate_limit_delay:
                        await asyncio.sleep(self.rate_limit_delay - time_since_last)
                    
                    self.last_request_time = time.time()
                    
                    resp = await session.get(url, timeout=15)
                    
                    if resp.status_code == 200:
                        try:
                            return resp.json()
                        except:
                            logger.warning(f"⚠️ Invalid JSON from {url}")
                            return None
                    elif resp.status_code in (401, 403):
                        logger.warning(f"🔒 Session expired (status {resp.status_code})")
                        return None
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
    
    async def validate_api_session(self) -> bool:
        """
        Validate session by making a real API call.
        This is the key fix - we test the actual API endpoint.
        """
        if not self.session_cache.get("cookies"):
            return False
        
        cookie_dict = {c['name']: c['value'] for c in self.session_cache['cookies']}
        
        try:
            proxy_url = None
            if self.proxies:
                proxy_str = self.current_proxy if self.sticky_proxy and self.current_proxy else random.choice(self.proxies)
                proxy_url = self._get_proxy_url(proxy_str)
            
            async with AsyncSession(
                verify=False, 
                impersonate="chrome120",
                proxies={"http": proxy_url, "https": proxy_url} if proxy_url else None
            ) as session:
                session.cookies.update(cookie_dict)
                session.headers.update({
                    "Referer": "https://tickets.museivaticani.va/",
                    "Accept": "application/json, text/plain, */*",
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive"
                })
                
                # Test with a real API call - use a known ticket ID or the home endpoint
                # The home/info endpoint is lightweight and good for validation
                # Call initValues first to establish session state
                await session.get("https://tickets.museivaticani.va/api/config/initValues", timeout=10)
                
                # Use startup endpoint instead of info
                resp = await session.get("https://tickets.museivaticani.va/api/config/startup?lang=it", timeout=10)
                
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if data.get("maintenance") == "off":
                            logger.info("✅ API session validation passed (startup)")
                            return True
                    except:
                        logger.warning("⚠️ Session validation response was not JSON")
                else:
                    logger.warning(f"❌ API session validation failed: HTTP {resp.status_code}")
                    return False
                
        except Exception as e:
            logger.debug(f"Session validation error: {e}")
            return False
    
    async def refresh_session_with_browser(self, ticket_type: int = 0, target_date: str = "27/02/2026", visitors: int = None) -> bool:
        """Use Playwright browser to get fresh session cookies and DYNAMIC IDs."""
        if not HAS_PLAYWRIGHT:
            logger.error("❌ Playwright not installed")
            return False
        
        logger.info("🔄 Refreshing session with browser...")
        
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime as dt
            
            # Build deep link
            if "/" in target_date:
                day, month, year = target_date.split('/')
                dt_obj = dt(int(year), int(month), int(day))
            else:
                dt_obj = dt.strptime(target_date, "%Y-%m-%d")
            
            rome = ZoneInfo("Europe/Rome")
            midnight = dt_obj.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=rome)
            ts = int(midnight.timestamp() * 1000)
            
            # Use correct slug based on ticket type
            slug = "MV-Biglietti" if ticket_type == 0 else "MV-Visite-Guidate"
            
            # Determine effective visitor count
            try:
                env_visitors = int(os.getenv("VATICAN_VISITORS", "").strip())
            except Exception:
                env_visitors = 0
            
            eff_visitors = visitors if (isinstance(visitors, int) and visitors > 0) else (env_visitors if env_visitors > 0 else 2)
            
            # ✅ CORRECT FORMAT: Use /fromtag/ with proper structure
            # Format: /home/fromtag/{visitors}/{timestamp}/{slug}/1
            if ticket_type == 0:
                slug = "MV-Biglietti"
            else:
                slug = "MV-Visite-Guidate"
            
            deep_url = f"https://tickets.museivaticani.va/home/fromtag/{eff_visitors}/{ts}/{slug}/1"
            
            logger.info(f"🔗 Navigating to: {deep_url}")
            
            async with async_playwright() as p:
                # No proxy for now (they're blocked by Cloudflare)
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage"
                    ]
                )
                
                context = await browser.new_context(
                    locale="it-IT",
                    timezone_id="Europe/Rome",
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                
                page = await context.new_page()
                
                # Navigate to the page
                await page.goto(deep_url, timeout=45000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                
                # Wait for ticket buttons to appear
                try:
                    await page.wait_for_selector('[data-cy^="bookTicket_"]', state="visible", timeout=10000)
                except:
                    logger.warning("⚠️ Timeout waiting for ticket buttons")
                
                # Extract cookies
                cookies = await context.cookies()
                
                # Extract ticket IDs using improved JavaScript with better DOM traversal
                ids = await page.evaluate('''() => {
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
                        if (dataCy) {
                            const id = dataCy.replace('bookTicket_', '');
                            buttons.push({
                                id: id,
                                element: btn
                            });
                        }
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
                                matchedButton = dataCy ? dataCy.replace('bookTicket_', '') : null;
                            }
                        }
                        
                        if (matchedButton) {
                            results.push({
                                id: matchedButton,
                                name: titleInfo.text
                            });
                        }
                    });
                    
                    // Step 4: For unmatched buttons, search up parent tree (up to 10 levels)
                    buttons.forEach(btnInfo => {
                        const alreadyMatched = results.some(r => r.id === btnInfo.id);
                        if (alreadyMatched) return;
                        
                        const btn = btnInfo.element;
                        let name = 'Vatican Ticket';
                        
                        // Search up to 10 parent levels (increased from 5)
                        let parent = btn.parentElement;
                        for (let i = 0; i < 10 && parent; i++) {
                            const titleEl = parent.querySelector('.muvaTicketTitle, h1, h2, h3, h4, .card-title, [class*="title"], [class*="Title"]');
                            if (titleEl && titleEl.textContent && titleEl.textContent.trim()) {
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
                }''')
                
                await browser.close()
                
                if ids and len(ids) > 0:
                    # Remove duplicates
                    unique_ids = list({v['id']: v for v in ids}.values())
                    
                    # Store IDs with visitor count in key
                    ids_cache = {
                        f"{target_date}_v{eff_visitors}": unique_ids,
                        f"__ALL___v{eff_visitors}": unique_ids
                    }
                    self._save_session(cookies, ids_cache)
                    logger.info(f"✅ Session refreshed! Got {len(unique_ids)} DYNAMIC ticket IDs for {eff_visitors} visitor(s)")
                    
                    # Log the IDs for verification
                    for idx, item in enumerate(unique_ids[:3], 1):
                        logger.info(f"   {idx}. {item['name']} (ID: {item['id']})")
                    
                    return True
                else:
                    logger.error("❌ No ticket IDs found during refresh")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Browser refresh failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def check_availability(
        self, 
        date_str: str, 
        ticket_type: int = 0,
        languages: List[str] = None,
        visitors: int = None
    ) -> List[Dict]:
        """
        Check ticket availability using HTTP API.
        Key fix: Proper session validation against actual API.
        """
        results = []
        
        # Step 1: Validate session against actual API
        if not await self.validate_api_session():
            logger.info("🔄 API session invalid, refreshing with browser...")
            if not await self.refresh_session_with_browser(ticket_type, date_str, visitors=visitors):
                logger.error("❌ Failed to refresh session")
                return results
        
        # ✅ FIX: Determine effective visitor count first (needed for cache key)
        try:
            env_visitors = int(os.getenv("VATICAN_VISITORS", "").strip())
        except Exception:
            env_visitors = 0
        eff_visitors = visitors if (isinstance(visitors, int) and visitors > 0) else (env_visitors if env_visitors > 0 else 2)
        
        # Step 2: Get cached IDs (with visitor count in key)
        ids_cache = self.session_cache.get("ids_cache", {})
        cache_key = f"{date_str}_v{eff_visitors}"
        fallback_key = f"__ALL___v{eff_visitors}"
        
        cached_ids = ids_cache.get(cache_key, [])
        if not cached_ids:
            logger.info(f"🔍 No cached IDs for {date_str} with {eff_visitors} visitor(s), harvesting...")
            if not await self.refresh_session_with_browser(ticket_type, date_str, visitors=eff_visitors):
                return results
            ids_cache = self.session_cache.get("ids_cache", {})
            cached_ids = ids_cache.get(cache_key, [])
        
        # Fallback: reuse last harvested IDs for this visitor count if date-specific cache is empty
        if not cached_ids:
            cached_ids = ids_cache.get(fallback_key, [])
            if cached_ids:
                logger.info(f"♻️ Reusing {len(cached_ids)} cached IDs from previous session ({eff_visitors} visitors)")
        
        if not cached_ids:
            logger.error("❌ No ticket IDs available")
            return results
        
        logger.info(f"🧾 Using {len(cached_ids)} ticket IDs for checks")
        
        # Format date for API
        if "-" in date_str:
            parts = date_str.split("-")
            api_date = f"{parts[2]}/{parts[1]}/{parts[0]}"
        else:
            api_date = date_str
        
        # Language setup
        lang_map = {"ITA": "it", "ENG": "en", "FRA": "fr", "DEU": "de", "SPA": "es", "TED": "de"}
        if not languages:
            languages = ["ITA", "ENG"] if ticket_type == 1 else ["ITA"]
        
        # Get proxy
        proxy_url = None
        if self.proxies:
            proxy_str = self.current_proxy if self.sticky_proxy and self.current_proxy else random.choice(self.proxies)
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
                "X-Requested-With": "XMLHttpRequest",
                "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive"
            })
            
            check_tasks = []
            check_meta = []
            
            for item in cached_ids:
                t_id = item['id']
                t_name = item['name']
                
                # Do not drop IDs based on name heuristics; guided pages often yield 'Unknown'
                # Apply language parameter purely based on requested ticket_type
                
                # Use the eff_visitors already determined above
                
                for lang_code in languages:
                    api_lang = lang_map.get(lang_code, "en")
                    visit_lang_param = f"&visitLang={lang_code}" if ticket_type == 1 else ""
                    
                    url = (
                        f"https://tickets.museivaticani.va/api/visit/timeavail"
                        f"?lang={api_lang}{visit_lang_param}"
                        f"&visitTypeId={t_id}&visitorNum={eff_visitors}&visitDate={api_date}"
                    )
                    
                    check_tasks.append(self._rate_limited_request(session, url))
                    check_meta.append({
                        "id": t_id,
                        "name": t_name,
                        "lang": lang_code,
                        "date": date_str
                    })
            
            logger.info(f"🔍 Checking {len(check_tasks)} ticket/language combinations...")
            responses = await asyncio.gather(*check_tasks, return_exceptions=True)
            
            # Implementation of self-healing retry for 500 errors
            has_500 = any(isinstance(r, dict) and r.get('status') == 500 for r in responses)
            if has_500:
                logger.warning("⚠️ Detected 500 errors in response. Forcing session refresh...")
                if await self.refresh_session_with_browser(ticket_type, date_str, visitors=visitors):
                    # Update cookie_dict and recreate session for retry
                    cookie_dict = {c['name']: c['value'] for c in self.session_cache['cookies']}
                    session.cookies.update(cookie_dict)
                    # Re-run the tasks
                    responses = await asyncio.gather(*check_tasks, return_exceptions=True)
            
            # Process results
            for i, resp_data in enumerate(responses):
                if isinstance(resp_data, Exception):
                    continue
                
                if resp_data is None:
                    continue
                
                if not isinstance(resp_data, dict):
                    # logger.debug(f"⚠️ Unexpected resp_data type: {type(resp_data)}")
                    continue
                
                meta = check_meta[i]
                timetable = resp_data.get("timetable", [])
                
                # If timetable is empty but status was 200, it might be truly sold out
                # or the response structure changed.
                
                # Check for error or invalid response
                if 'error' in resp_data:
                    logger.warning(f"⚠️ API Error for {meta['name']}: {resp_data.get('error')}")
                    continue

                available_slots = [
                    {"time": t['time'], "availability": t['availability']}
                    for t in timetable
                    if t.get('availability') not in ['SOLD_OUT', 'NOT_ALLOWED']
                ]
                
                # If we found no slots, double check if it's because of strict filtering
                # Sometimes availability might be 'LOW_AVAILABILITY' or other statuses
                if not available_slots and timetable:
                    # Log what statuses we did see to help debug
                    statuses = set(t.get('availability') for t in timetable)
                    if any(s not in ['SOLD_OUT', 'NOT_ALLOWED'] for s in statuses):
                        logger.warning(f"⚠️ Potential missed slots! Statuses seen: {statuses}")
                
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
                        f"{len(available_slots)} slots"
                    )
        
        return results


# Convenience function for direct use
async def check_vatican_availability(
    date: str,
    ticket_type: int = 0,
    languages: List[str] = None,
    proxies: List[str] = None
) -> List[Dict]:
    """
    Quick check function.
    
    Args:
        date: DD/MM/YYYY or YYYY-MM-DD format
        ticket_type: 0 = Standard, 1 = Guided
        languages: List of language codes (e.g., ["ENG", "ITA"])
        proxies: Optional list of proxy strings
    
    Returns:
        List of available ticket results
    """
    monitor = GodTierVaticanMonitorV2(proxies=proxies)
    return await monitor.check_availability(date, ticket_type, languages)


if __name__ == "__main__":
    # Test the monitor
    async def test():
        monitor = GodTierVaticanMonitorV2()
        results = await monitor.check_availability(
            date_str="27/02/2026",
            ticket_type=0,  # Standard
            languages=["ITA"]
        )
        print(f"Found {len(results)} available tickets")
        for r in results:
            print(f"  {r['ticket_name']}: {len(r['slots'])} slots")
    
    asyncio.run(test())
