#!/usr/bin/env python3
"""
Debug script to see raw API responses for March 28th
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime

# Add the current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from god_tier_monitor_v2 import GodTierVaticanMonitorV2
from curl_cffi.requests import AsyncSession

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # DEBUG level to see more details
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("March28Debug")

class March28APIDebugger:
    def __init__(self):
        self.monitor = GodTierVaticanMonitorV2()
        self.test_date = "28/03/2026"
        self.test_visitors = 1
        
    async def debug_api_calls(self):
        """Debug the actual API calls being made"""
        logger.info(f"🔍 Debugging API calls for {self.test_date} with {self.test_visitors} visitors")
        
        try:
            # Ensure valid session
            if not await self.monitor.validate_api_session():
                logger.info("🔄 Refreshing session...")
                await self.monitor.refresh_session_with_browser(
                    target_date=self.test_date, 
                    visitors=self.test_visitors
                )
            
            # Get ticket IDs from cache
            ticket_items = self.monitor.session_cache.get("ids_cache", {}).get(self.test_date, [])
            if not ticket_items:
                ticket_items = self.monitor.session_cache.get("ids_cache", {}).get("__ALL__", [])
            
            logger.info(f"📋 Found {len(ticket_items)} ticket items in cache")
            
            # Get proxy
            proxy_url = None
            if self.monitor.proxies:
                proxy_str = self.monitor.current_proxy if self.monitor.sticky_proxy and self.monitor.current_proxy else self.monitor.proxies[0]
                proxy_url = self.monitor._get_proxy_url(proxy_str)
            
            # Setup session
            cookie_dict = {c['name']: c['value'] for c in self.monitor.session_cache['cookies']}
            
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
                
                # Test a few specific ticket IDs
                test_items = ticket_items[:3]  # Test first 3 items
                
                for item in test_items:
                    ticket_id = item['id']
                    ticket_name = item['name']
                    
                    logger.info(f"\n🔍 Testing ticket ID: {ticket_id} ({ticket_name})")
                    
                    # Build API URL
                    url = (
                        f"https://tickets.museivaticani.va/api/visit/timeavail"
                        f"?id={ticket_id}&date={self.test_date}&visitorNum={self.test_visitors}&lang=it"
                    )
                    
                    logger.info(f"📡 API URL: {url}")
                    
                    try:
                        # Make the API call
                        resp = await session.get(url, timeout=10)
                        
                        logger.info(f"📊 Response status: {resp.status_code}")
                        logger.info(f"📊 Response headers: {dict(resp.headers)}")
                        
                        if resp.status_code == 200:
                            try:
                                data = resp.json()
                                logger.info(f"📊 Response data: {json.dumps(data, indent=2)}")
                                
                                # Check for slots
                                if isinstance(data, list):
                                    logger.info(f"✅ Found {len(data)} time slots")
                                    for slot in data:
                                        logger.info(f"   🕐 Slot: {slot.get('time', 'N/A')} - Available: {slot.get('avail', 'N/A')}")
                                elif isinstance(data, dict):
                                    logger.info(f"📋 Response is dict: {data}")
                                else:
                                    logger.info(f"📋 Response is: {type(data)} - {data}")
                                    
                            except json.JSONDecodeError as e:
                                logger.error(f"❌ Failed to parse JSON: {e}")
                                logger.info(f"📄 Raw response: {resp.text[:500]}")
                        else:
                            logger.error(f"❌ API call failed: HTTP {resp.status_code}")
                            logger.info(f"📄 Response text: {resp.text[:500]}")
                            
                    except Exception as e:
                        logger.error(f"❌ API call exception: {e}")
                    
                    # Small delay between calls
                    await asyncio.sleep(0.5)
                    
        except Exception as e:
            logger.error(f"❌ Debug session failed: {e}")
            import traceback
            traceback.print_exc()

    async def test_different_date_formats(self):
        """Test different date formats"""
        logger.info("🔍 Testing different date formats")
        
        date_formats = [
            "28/03/2026",  # Italian format
            "2026-03-28",  # ISO format
            "28-03-2026",  # Alternative format
        ]
        
        for date_fmt in date_formats:
            logger.info(f"\n📅 Testing date format: {date_fmt}")
            
            try:
                # Test with monitor's check_availability
                slots = await self.monitor.check_availability(
                    date_fmt, 
                    ticket_type=0,  # Standard tickets
                    visitors=self.test_visitors
                )
                
                logger.info(f"✅ Found {len(slots)} slots for {date_fmt}")
                
                # Look for 17:30
                slot_1730 = [s for s in slots if s.get('time') == '17:30']
                logger.info(f"🕐 17:30 slot: {'✅ Found' if slot_1730 else '❌ Not found'}")
                
            except Exception as e:
                logger.error(f"❌ Failed for {date_fmt}: {e}")

    async def test_march_27_comparison(self):
        """Test March 27th for comparison to see if it's date-specific"""
        logger.info("🔍 Testing March 27th for comparison")
        
        comparison_date = "27/03/2026"
        
        try:
            slots = await self.monitor.check_availability(
                comparison_date, 
                ticket_type=0,  # Standard tickets
                visitors=self.test_visitors
            )
            
            logger.info(f"✅ March 27th: Found {len(slots)} slots")
            
            # Show all available times
            if slots:
                logger.info("🕐 Available times on March 27th:")
                for slot in slots:
                    logger.info(f"   {slot.get('time', 'N/A')} - Available: {slot.get('avail', 'N/A')}")
            else:
                logger.info("❌ No slots found on March 27th either")
                
        except Exception as e:
            logger.error(f"❌ March 27th test failed: {e}")

async def main():
    """Main debug execution"""
    logger.info("🚀 Starting March 28th API debug session")
    
    debugger = March28APIDebugger()
    
    # Run debug tests
    await debugger.debug_api_calls()
    await debugger.test_different_date_formats()
    await debugger.test_march_27_comparison()
    
    logger.info("✅ Debug session completed")

if __name__ == "__main__":
    asyncio.run(main())