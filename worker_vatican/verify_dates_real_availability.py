#!/usr/bin/env python3
"""
Comprehensive test to verify actual API responses for specific dates
Checks if dates 16, 28, 4 are actually available vs what bot shows
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("DateVerificationTest")

class DateVerificationTester:
    def __init__(self):
        self.monitor = GodTierVaticanMonitorV2()  # No proxy to avoid auth issues
        self.test_dates = [
            "16/03/2026",  # March 16
            "28/03/2026",  # March 28 (the problematic 17:30 date)
            "04/04/2026",  # April 4
        ]
        self.test_visitors = 1
        self.results = {}
        
    async def verify_actual_availability(self):
        """Check actual availability vs what bot reports"""
        logger.info("🔍 Verifying actual availability for specific dates")
        
        for date_str in self.test_dates:
            logger.info(f"\n📅 Testing date: {date_str}")
            
            try:
                # Test standard tickets
                standard_slots = await self.monitor.check_availability(
                    date_str, 
                    ticket_type=0,  # Standard tickets
                    visitors=self.test_visitors
                )
                
                # Test guided tickets
                guided_slots = await self.monitor.check_availability(
                    date_str, 
                    ticket_type=1,  # Guided tickets
                    languages=["ENG"],
                    visitors=self.test_visitors
                )
                
                # Check for 17:30 slot specifically
                standard_1730 = [s for s in standard_slots if s.get('time') == '17:30']
                guided_1730 = [s for s in guided_slots if s.get('time') == '17:30']
                
                self.results[date_str] = {
                    'standard': {
                        'total_slots': len(standard_slots),
                        'available_times': [s.get('time') for s in standard_slots if s.get('time')],
                        'slot_1730_found': len(standard_1730) > 0,
                        'slot_1730_details': standard_1730[0] if standard_1730 else None
                    },
                    'guided': {
                        'total_slots': len(guided_slots),
                        'available_times': [s.get('time') for s in guided_slots if s.get('time')],
                        'slot_1730_found': len(guided_1730) > 0,
                        'slot_1730_details': guided_1730[0] if guided_1730 else None
                    }
                }
                
                logger.info(f"✅ Standard: {len(standard_slots)} slots, 17:30: {'✅' if standard_1730 else '❌'}")
                logger.info(f"✅ Guided: {len(guided_slots)} slots, 17:30: {'✅' if guided_1730 else '❌'}")
                
                if standard_slots:
                    logger.info(f"🕐 Standard times: {[s.get('time') for s in standard_slots]}")
                if guided_slots:
                    logger.info(f"🕐 Guided times: {[s.get('time') for s in guided_slots]}")
                
            except Exception as e:
                logger.error(f"❌ Failed for {date_str}: {e}")
                self.results[date_str] = {'error': str(e)}
    
    async def check_raw_api_responses(self):
        """Check raw API responses to see what's actually returned"""
        logger.info("\n🔍 Checking raw API responses")
        
        # Ensure valid session
        if not await self.monitor.validate_api_session():
            logger.info("🔄 Refreshing session...")
            await self.monitor.refresh_session_with_browser(
                target_date="28/03/2026", 
                visitors=self.test_visitors
            )
        
        # Get ticket IDs from cache
        ticket_items = self.monitor.session_cache.get("ids_cache", {}).get("__ALL__", [])
        
        if not ticket_items:
            logger.error("❌ No ticket IDs found in cache")
            return
        
        logger.info(f"📋 Found {len(ticket_items)} ticket items in cache")
        
        for date_str in self.test_dates:
            logger.info(f"\n📡 Raw API check for {date_str}")
            
            for item in ticket_items[:2]:  # Test first 2 items
                ticket_id = item['id']
                ticket_name = item['name']
                
                logger.info(f"\n🔍 Ticket ID: {ticket_id} ({ticket_name})")
                
                try:
                    # Make direct API call
                    from curl_cffi.requests import AsyncSession
                    
                    cookie_dict = {c['name']: c['value'] for c in self.monitor.session_cache['cookies']}
                    
                    async with AsyncSession(
                        verify=False, 
                        impersonate="chrome120"
                    ) as session:
                        session.cookies.update(cookie_dict)
                        session.headers.update({
                            "Referer": "https://tickets.museivaticani.va/",
                            "Accept": "application/json, text/plain, */*",
                            "X-Requested-With": "XMLHttpRequest"
                        })
                        
                        url = (
                            f"https://tickets.museivaticani.va/api/visit/timeavail"
                            f"?id={ticket_id}&date={date_str}&visitorNum={self.test_visitors}&lang=it"
                        )
                        
                        logger.info(f"📡 URL: {url}")
                        
                        resp = await session.get(url, timeout=10)
                        
                        if resp.status_code == 200:
                            try:
                                data = resp.json()
                                logger.info(f"📊 Response: {json.dumps(data, indent=2)}")
                                
                                if isinstance(data, list) and data:
                                    times = [slot.get('time') for slot in data if slot.get('time')]
                                    logger.info(f"🕐 Available times: {times}")
                                    
                                    # Check for 17:30
                                    has_1730 = any(slot.get('time') == '17:30' and slot.get('avail') for slot in data)
                                    logger.info(f"🕐 17:30 available: {'✅' if has_1730 else '❌'}")
                                else:
                                    logger.info(f"📋 Empty or non-list response: {type(data)}")
                                    
                            except json.JSONDecodeError as e:
                                logger.error(f"❌ JSON decode error: {e}")
                                logger.info(f"📄 Raw text: {resp.text[:200]}")
                        else:
                            logger.error(f"❌ HTTP {resp.status_code}: {resp.text[:200]}")
                            
                except Exception as e:
                    logger.error(f"❌ API call failed: {e}")
                
                # Small delay
                await asyncio.sleep(0.5)
    
    def generate_verification_report(self):
        """Generate comprehensive verification report"""
        print("\n" + "="*80)
        print("📊 DATE VERIFICATION REPORT")
        print("="*80)
        
        for date_str in self.test_dates:
            print(f"\n📅 {date_str}:")
            
            if date_str not in self.results or 'error' in self.results[date_str]:
                print(f"❌ Error: {self.results.get(date_str, {}).get('error', 'Unknown error')}")
                continue
            
            data = self.results[date_str]
            
            # Standard tickets
            standard = data['standard']
            print(f"🏛️  Standard Tickets:")
            print(f"   Total slots: {standard['total_slots']}")
            print(f"   Available times: {standard['available_times']}")
            print(f"   17:30 slot: {'✅ FOUND' if standard['slot_1730_found'] else '❌ NOT FOUND'}")
            
            # Guided tickets
            guided = data['guided']
            print(f"🎤 Guided Tickets:")
            print(f"   Total slots: {guided['total_slots']}")
            print(f"   Available times: {guided['available_times']}")
            print(f"   17:30 slot: {'✅ FOUND' if guided['slot_1730_found'] else '❌ NOT FOUND'}")
        
        print("\n" + "="*80)
        print("🎯 ANALYSIS:")
        print("="*80)
        
        # Check patterns
        all_dates_empty = all(
            self.results.get(date, {}).get('standard', {}).get('total_slots', 0) == 0 and
            self.results.get(date, {}).get('guided', {}).get('total_slots', 0) == 0
            for date in self.test_dates if date in self.results and 'error' not in self.results[date]
        )
        
        if all_dates_empty:
            print("❌ ALL DATES SHOW ZERO AVAILABILITY")
            print("   This suggests:")
            print("   • Tickets are genuinely sold out for these dates")
            print("   • The dates are too far in the future")
            print("   • Different product categories needed")
            print("   • API responses are being filtered/cached incorrectly")
        else:
            print("✅ Some dates have availability")
            
            # Check 17:30 specifically
            found_1730 = False
            for date in self.test_dates:
                if date in self.results and 'error' not in self.results[date]:
                    standard_1730 = self.results[date].get('standard', {}).get('slot_1730_found', False)
                    guided_1730 = self.results[date].get('guided', {}).get('slot_1730_found', False)
                    if standard_1730 or guided_1730:
                        found_1730 = True
                        break
            
            if found_1730:
                print("✅ 17:30 slot found on at least one date")
            else:
                print("❌ 17:30 slot not found on any tested date")
                print("   This confirms the 17:30 slot issue is real, not a bot bug")

async def main():
    """Main verification execution"""
    logger.info("🚀 Starting date verification test")
    
    tester = DateVerificationTester()
    
    # Run verification tests
    await tester.verify_actual_availability()
    await tester.check_raw_api_responses()
    
    # Generate report
    tester.generate_verification_report()
    
    # Save detailed results
    results_file = f"date_verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(tester.results, f, indent=2, default=str)
    
    logger.info(f"💾 Detailed results saved to: {results_file}")

if __name__ == "__main__":
    asyncio.run(main())