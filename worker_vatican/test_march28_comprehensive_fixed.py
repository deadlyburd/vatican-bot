#!/usr/bin/env python3
"""
Comprehensive test for March 28th ticket availability
Tests both curl and Playwright methods to identify the 17:30 slot issue
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Add the current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from god_tier_monitor_v2 import GodTierVaticanMonitorV2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("March28Test")

class March28TicketTester:
    def __init__(self):
        self.monitor = GodTierVaticanMonitorV2()
        self.test_date = "28/03/2026"
        self.test_visitors = 1
        self.results = {}
        
    async def get_ticket_ids_from_cache(self, date_str: str, visitors: int = None) -> List[Dict]:
        """Get ticket IDs from session cache"""
        # Get cached IDs
        cached_ids = self.monitor.session_cache.get("ids_cache", {}).get(date_str, [])
        if not cached_ids:
            logger.info(f"🔍 No cached IDs for {date_str}, checking __ALL__ cache...")
            cached_ids = self.monitor.session_cache.get("ids_cache", {}).get("__ALL__", [])
        
        return cached_ids
    
    async def test_with_curl_method(self):
        """Test using curl method (current implementation)"""
        logger.info(f"🔄 Testing with CURL method for {self.test_date} with {self.test_visitors} visitors")
        
        try:
            # First ensure we have valid session
            if not await self.monitor.validate_api_session():
                logger.info("🔄 Session invalid, refreshing with browser...")
                await self.monitor.refresh_session_with_browser(
                    target_date=self.test_date, 
                    visitors=self.test_visitors
                )
            
            # Get ticket IDs from cache
            ticket_ids = await self.get_ticket_ids_from_cache(self.test_date, self.test_visitors)
            logger.info(f"📋 Found {len(ticket_ids)} ticket IDs via cache: {[item['id'] for item in ticket_ids]}")
            
            # Use the monitor's check_availability method
            all_slots = await self.monitor.check_availability(
                self.test_date, 
                ticket_type=0,  # Standard tickets
                visitors=self.test_visitors
            )
            
            logger.info(f"✅ CURL method found {len(all_slots)} total slots")
            
            # Look for 17:30 slot specifically
            slot_1730 = [s for s in all_slots if s.get('time') == '17:30']
            
            self.results['curl'] = {
                'ticket_ids': [item['id'] for item in ticket_ids],
                'all_slots': all_slots,
                'slot_1730_found': len(slot_1730) > 0,
                'slot_1730_details': slot_1730[0] if slot_1730 else None
            }
            
            logger.info(f"🎯 CURL Results: Found {len(all_slots)} total slots, 17:30 slot: {'✅' if slot_1730 else '❌'}")
            
        except Exception as e:
            logger.error(f"❌ CURL method failed: {e}")
            self.results['curl'] = {'error': str(e)}
    
    async def test_with_playwright_method(self):
        """Test using Playwright to get fresh IDs and check availability"""
        logger.info(f"🔄 Testing with Playwright method for {self.test_date} with {self.test_visitors} visitors")
        
        try:
            # Refresh session with browser to get fresh cookies and IDs
            success = await self.monitor.refresh_session_with_browser(
                target_date=self.test_date,
                visitors=self.test_visitors
            )
            
            if not success:
                logger.error("❌ Failed to refresh session with browser")
                self.results['playwright'] = {'error': 'Failed to refresh session'}
                return
            
            # Get ticket IDs from updated cache
            ticket_ids = await self.get_ticket_ids_from_cache(self.test_date, self.test_visitors)
            logger.info(f"📋 Found {len(ticket_ids)} ticket IDs via Playwright: {[item['id'] for item in ticket_ids]}")
            
            # Use the monitor's check_availability method
            all_slots = await self.monitor.check_availability(
                self.test_date, 
                ticket_type=0,  # Standard tickets
                visitors=self.test_visitors
            )
            
            logger.info(f"✅ Playwright method found {len(all_slots)} total slots")
            
            # Look for 17:30 slot specifically
            slot_1730 = [s for s in all_slots if s.get('time') == '17:30']
            
            self.results['playwright'] = {
                'ticket_ids': [item['id'] for item in ticket_ids],
                'all_slots': all_slots,
                'slot_1730_found': len(slot_1730) > 0,
                'slot_1730_details': slot_1730[0] if slot_1730 else None
            }
            
            logger.info(f"🎯 Playwright Results: Found {len(all_slots)} total slots, 17:30 slot: {'✅' if slot_1730 else '❌'}")
            
        except Exception as e:
            logger.error(f"❌ Playwright method failed: {e}")
            self.results['playwright'] = {'error': str(e)}
    
    async def test_different_visitor_counts(self):
        """Test with different visitor numbers to see if 17:30 appears"""
        logger.info("🔄 Testing different visitor counts for 17:30 slot")
        
        try:
            # Test with 1 and 2 visitors
            for visitors in [1, 2]:
                logger.info(f"Testing with {visitors} visitors...")
                
                slots = await self.monitor.check_availability(
                    self.test_date, 
                    ticket_type=0,  # Standard tickets
                    visitors=visitors
                )
                
                slot_1730 = [s for s in slots if s.get('time') == '17:30']
                logger.info(f"Visitors={visitors}: Found {len(slots)} slots, 17:30 slot {'✅' if slot_1730 else '❌'}")
                
                if slot_1730:
                    logger.info(f"   17:30 slot details: {slot_1730[0]}")
            
            self.results['visitor_test'] = {'completed': True}
            
        except Exception as e:
            logger.error(f"❌ Visitor test failed: {e}")
            self.results['visitor_test'] = {'error': str(e)}
    
    async def test_different_ticket_types(self):
        """Test with different ticket types (standard vs guided)"""
        logger.info("🔄 Testing different ticket types for 17:30 slot")
        
        try:
            # Test standard tickets (type 0) and guided tickets (type 1)
            for ticket_type in [0, 1]:
                type_name = "Standard" if ticket_type == 0 else "Guided"
                logger.info(f"Testing {type_name} tickets...")
                
                slots = await self.monitor.check_availability(
                    self.test_date, 
                    ticket_type=ticket_type,
                    visitors=self.test_visitors
                )
                
                slot_1730 = [s for s in slots if s.get('time') == '17:30']
                logger.info(f"{type_name} tickets: Found {len(slots)} slots, 17:30 slot {'✅' if slot_1730 else '❌'}")
                
                if slot_1730:
                    logger.info(f"   17:30 slot details: {slot_1730[0]}")
            
            self.results['ticket_type_test'] = {'completed': True}
            
        except Exception as e:
            logger.error(f"❌ Ticket type test failed: {e}")
            self.results['ticket_type_test'] = {'error': str(e)}
    
    def print_comparison(self):
        """Print detailed comparison of results"""
        print("\n" + "="*80)
        print("📊 MARCH 28TH TICKET ANALYSIS COMPARISON")
        print("="*80)
        
        # CURL Results
        print("\n🔍 CURL METHOD RESULTS:")
        curl_data = self.results.get('curl', {})
        if 'error' in curl_data:
            print(f"❌ Error: {curl_data['error']}")
        else:
            print(f"📋 Ticket IDs found: {curl_data.get('ticket_ids', [])}")
            print(f"🎫 Total slots: {len(curl_data.get('all_slots', []))}")
            print(f"🕐 17:30 slot found: {'✅ YES' if curl_data.get('slot_1730_found') else '❌ NO'}")
            if curl_data.get('slot_1730_details'):
                print(f"   Details: {curl_data['slot_1730_details']}")
        
        # Playwright Results
        print("\n🔍 PLAYWRIGHT METHOD RESULTS:")
        pw_data = self.results.get('playwright', {})
        if 'error' in pw_data:
            print(f"❌ Error: {pw_data['error']}")
        else:
            print(f"📋 Ticket IDs found: {pw_data.get('ticket_ids', [])}")
            print(f"🎫 Total slots: {len(pw_data.get('all_slots', []))}")
            print(f"🕐 17:30 slot found: {'✅ YES' if pw_data.get('slot_1730_found') else '❌ NO'}")
            if pw_data.get('slot_1730_details'):
                print(f"   Details: {pw_data['slot_1730_details']}")
        
        # Analysis
        print("\n📈 ANALYSIS:")
        curl_1730 = self.results.get('curl', {}).get('slot_1730_found', False)
        pw_1730 = self.results.get('playwright', {}).get('slot_1730_found', False)
        
        if curl_1730 and pw_1730:
            print("✅ Both methods found the 17:30 slot - issue may be resolved!")
        elif curl_1730 and not pw_1730:
            print("⚠️  CURL found 17:30 but Playwright didn't - possible session/cookie issue")
        elif not curl_1730 and pw_1730:
            print("⚠️  Playwright found 17:30 but CURL didn't - possible API parameter issue")
        else:
            print("❌ Neither method found the 17:30 slot - slot may not exist for standard tickets with 1 visitor")
            print("   🔍 The 17:30 slot might be in a different product category (guided tour, special experience, etc.)")
        
        print("\n" + "="*80)

async def main():
    """Main test execution"""
    logger.info("🚀 Starting comprehensive March 28th ticket test")
    
    tester = March28TicketTester()
    
    # Run all tests
    await tester.test_with_curl_method()
    await tester.test_with_playwright_method()
    await tester.test_different_visitor_counts()
    await tester.test_different_ticket_types()
    
    # Print comparison
    tester.print_comparison()
    
    # Save detailed results to file
    results_file = f"march28_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(tester.results, f, indent=2, default=str)
    
    logger.info(f"💾 Detailed results saved to: {results_file}")

if __name__ == "__main__":
    asyncio.run(main())