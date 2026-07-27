#!/usr/bin/env python3
"""
Test script to verify visitor count is working correctly
Tests different visitor counts to see if availability changes
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
logger = logging.getLogger("VisitorCountTest")

class VisitorCountTester:
    def __init__(self):
        self.monitor = GodTierVaticanMonitorV2()  # No proxy to avoid auth issues
        self.test_date = "26/03/2026"  # Use a date we know has availability
        self.results = {}
        
    async def test_visitor_counts(self):
        """Test different visitor counts to see availability differences"""
        logger.info(f"🧪 Testing visitor counts for {self.test_date}")
        
        # Test different visitor counts
        for visitors in [1, 2, 3, 4, 5]:
            logger.info(f"\n👥 Testing with {visitors} visitors...")
            
            try:
                # Test standard tickets (type 0)
                slots = await self.monitor.check_availability(
                    self.test_date, 
                    ticket_type=0,  # Standard tickets
                    visitors=visitors
                )
                
                logger.info(f"✅ Found {len(slots)} slots for {visitors} visitors")
                
                # Look for specific time slots
                times_found = [s.get('time') for s in slots if s.get('time')]
                logger.info(f"🕐 Available times: {times_found}")
                
                # Check if 17:30 is available
                slot_1730 = [s for s in slots if s.get('time') == '17:30']
                logger.info(f"🕐 17:30 slot: {'✅ FOUND' if slot_1730 else '❌ NOT FOUND'}")
                
                self.results[f'{visitors}_visitors'] = {
                    'slots_found': len(slots),
                    'available_times': times_found,
                    'slot_1730_found': len(slot_1730) > 0,
                    'slot_1730_details': slot_1730[0] if slot_1730 else None
                }
                
            except Exception as e:
                logger.error(f"❌ Failed for {visitors} visitors: {e}")
                self.results[f'{visitors}_visitors'] = {'error': str(e)}
    
    async def test_guided_tickets(self):
        """Test guided tickets with different visitor counts"""
        logger.info(f"\n🎯 Testing guided tickets with different visitor counts")
        
        for visitors in [1, 2]:
            logger.info(f"\n👥 Testing guided tickets with {visitors} visitors...")
            
            try:
                # Test guided tickets (type 1) with English language
                slots = await self.monitor.check_availability(
                    self.test_date, 
                    ticket_type=1,  # Guided tickets
                    languages=["ENG"],
                    visitors=visitors
                )
                
                logger.info(f"✅ Found {len(slots)} guided slots for {visitors} visitors")
                
                times_found = [s.get('time') for s in slots if s.get('time')]
                logger.info(f"🕐 Available guided times: {times_found}")
                
                self.results[f'{visitors}_visitors_guided'] = {
                    'slots_found': len(slots),
                    'available_times': times_found
                }
                
            except Exception as e:
                logger.error(f"❌ Failed for {visitors} visitors guided: {e}")
                self.results[f'{visitors}_visitors_guided'] = {'error': str(e)}
    
    def print_analysis(self):
        """Print detailed analysis of visitor count results"""
        print("\n" + "="*80)
        print("📊 VISITOR COUNT ANALYSIS RESULTS")
        print("="*80)
        
        # Standard tickets analysis
        print("\n🏛️  STANDARD TICKETS ANALYSIS:")
        for visitors in [1, 2, 3, 4, 5]:
            key = f'{visitors}_visitors'
            data = self.results.get(key, {})
            
            if 'error' in data:
                print(f"   {visitors} visitors: ❌ Error - {data['error']}")
            else:
                slots = data.get('slots_found', 0)
                has_1730 = '✅' if data.get('slot_1730_found') else '❌'
                print(f"   {visitors} visitors: {slots} slots, 17:30: {has_1730}")
        
        # Guided tickets analysis
        print("\n🎤 GUIDED TICKETS ANALYSIS:")
        for visitors in [1, 2]:
            key = f'{visitors}_visitors_guided'
            data = self.results.get(key, {})
            
            if 'error' in data:
                print(f"   {visitors} visitors: ❌ Error - {data['error']}")
            else:
                slots = data.get('slots_found', 0)
                print(f"   {visitors} visitors: {slots} guided slots")
        
        # Key insights
        print("\n🔍 KEY INSIGHTS:")
        
        # Check if visitor count affects availability
        standard_results = [self.results.get(f'{v}_visitors', {}).get('slots_found', 0) for v in [1, 2, 3, 4, 5]]
        if len(set(standard_results)) > 1:
            print("✅ Visitor count DOES affect availability!")
            print("   Different visitor counts show different slot availability")
        else:
            print("⚠️  Visitor count does not seem to affect availability for this date")
            print("   This could mean:")
            print("   • The Vatican API doesn't limit by visitor count for these tickets")
            print("   • All visitor counts show the same availability")
            print("   • The date has limited availability regardless of group size")
        
        # Check 17:30 availability across visitor counts
        has_1730_counts = [v for v in [1, 2, 3, 4, 5] if self.results.get(f'{v}_visitors', {}).get('slot_1730_found')]
        if has_1730_counts:
            print(f"✅ 17:30 slot found for visitor counts: {has_1730_counts}")
        else:
            print("❌ 17:30 slot not found for any visitor count on this date")
        
        print("\n" + "="*80)

async def main():
    """Main test execution"""
    logger.info("🚀 Starting visitor count test")
    
    tester = VisitorCountTester()
    
    # Run tests
    await tester.test_visitor_counts()
    await tester.test_guided_tickets()
    
    # Print analysis
    tester.print_analysis()
    
    # Save detailed results
    results_file = f"visitor_count_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(tester.results, f, indent=2, default=str)
    
    logger.info(f"💾 Detailed results saved to: {results_file}")

if __name__ == "__main__":
    asyncio.run(main())