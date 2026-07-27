#!/usr/bin/env python3
"""
Final comprehensive analysis of March 28th ticket availability
Tests direct website access and provides complete analysis
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
logger = logging.getLogger("FinalAnalysis")

class March28FinalAnalysis:
    def __init__(self):
        # Test without proxies first to eliminate proxy issues
        self.monitor_no_proxy = GodTierVaticanMonitorV2(proxies=[])
        self.monitor_with_proxy = GodTierVaticanMonitorV2()
        self.test_date = "28/03/2026"
        self.test_visitors = 1
        self.results = {}
        
    async def test_without_proxy(self):
        """Test without proxy to eliminate proxy authentication issues"""
        logger.info(f"🔄 Testing WITHOUT proxy for {self.test_date} with {self.test_visitors} visitors")
        
        try:
            # Test standard tickets
            slots = await self.monitor_no_proxy.check_availability(
                self.test_date, 
                ticket_type=0,  # Standard tickets
                visitors=self.test_visitors
            )
            
            logger.info(f"✅ No-proxy test found {len(slots)} slots")
            
            # Look for 17:30 slot specifically
            slot_1730 = [s for s in slots if s.get('time') == '17:30']
            
            self.results['no_proxy'] = {
                'slots_found': len(slots),
                'all_slots': slots,
                'slot_1730_found': len(slot_1730) > 0,
                'slot_1730_details': slot_1730[0] if slot_1730 else None
            }
            
            if slots:
                logger.info("🕐 All available times:")
                for slot in slots:
                    logger.info(f"   {slot.get('time', 'N/A')} - Available: {slot.get('avail', 'N/A')}")
            
        except Exception as e:
            logger.error(f"❌ No-proxy test failed: {e}")
            self.results['no_proxy'] = {'error': str(e)}
    
    async def test_with_proxy(self):
        """Test with proxy for comparison"""
        logger.info(f"🔄 Testing WITH proxy for {self.test_date} with {self.test_visitors} visitors")
        
        try:
            # Test standard tickets
            slots = await self.monitor_with_proxy.check_availability(
                self.test_date, 
                ticket_type=0,  # Standard tickets
                visitors=self.test_visitors
            )
            
            logger.info(f"✅ Proxy test found {len(slots)} slots")
            
            # Look for 17:30 slot specifically
            slot_1730 = [s for s in slots if s.get('time') == '17:30']
            
            self.results['with_proxy'] = {
                'slots_found': len(slots),
                'all_slots': slots,
                'slot_1730_found': len(slot_1730) > 0,
                'slot_1730_details': slot_1730[0] if slot_1730 else None
            }
            
        except Exception as e:
            logger.error(f"❌ Proxy test failed: {e}")
            self.results['with_proxy'] = {'error': str(e)}
    
    async def test_nearby_dates(self):
        """Test nearby dates to see if March 28th is unique"""
        logger.info("🔍 Testing nearby dates for comparison")
        
        test_dates = [
            "26/03/2026",
            "27/03/2026", 
            "29/03/2026",
            "30/03/2026"
        ]
        
        date_results = {}
        
        for date_str in test_dates:
            logger.info(f"📅 Testing {date_str}...")
            
            try:
                slots = await self.monitor_no_proxy.check_availability(
                    date_str, 
                    ticket_type=0,  # Standard tickets
                    visitors=self.test_visitors
                )
                
                slot_1730 = [s for s in slots if s.get('time') == '17:30']
                
                date_results[date_str] = {
                    'slots_found': len(slots),
                    'slot_1730_found': len(slot_1730) > 0
                }
                
                logger.info(f"   Found {len(slots)} slots, 17:30: {'✅' if slot_1730 else '❌'}")
                
            except Exception as e:
                logger.error(f"   ❌ Failed for {date_str}: {e}")
                date_results[date_str] = {'error': str(e)}
        
        self.results['nearby_dates'] = date_results
    
    async def test_different_visitor_counts_detailed(self):
        """Test 1, 2, 3, 4 visitors to see if availability changes"""
        logger.info("🔍 Testing different visitor counts in detail")
        
        visitor_results = {}
        
        for visitors in [1, 2, 3, 4]:
            logger.info(f"👥 Testing with {visitors} visitors...")
            
            try:
                slots = await self.monitor_no_proxy.check_availability(
                    self.test_date, 
                    ticket_type=0,  # Standard tickets
                    visitors=visitors
                )
                
                slot_1730 = [s for s in slots if s.get('time') == '17:30']
                
                visitor_results[f'{visitors}_visitors'] = {
                    'slots_found': len(slots),
                    'slot_1730_found': len(slot_1730) > 0
                }
                
                logger.info(f"   Found {len(slots)} slots, 17:30: {'✅' if slot_1730 else '❌'}")
                
            except Exception as e:
                logger.error(f"   ❌ Failed for {visitors} visitors: {e}")
                visitor_results[f'{visitors}_visitors'] = {'error': str(e)}
        
        self.results['visitor_counts'] = visitor_results
    
    def generate_final_report(self):
        """Generate comprehensive final report"""
        print("\n" + "="*80)
        print("📊 FINAL COMPREHENSIVE ANALYSIS - MARCH 28TH TICKETS")
        print("="*80)
        
        # No Proxy Results
        print("\n🔍 NO PROXY TEST RESULTS:")
        no_proxy_data = self.results.get('no_proxy', {})
        if 'error' in no_proxy_data:
            print(f"❌ Error: {no_proxy_data['error']}")
        else:
            print(f"🎫 Slots found: {no_proxy_data.get('slots_found', 0)}")
            print(f"🕐 17:30 slot: {'✅ FOUND' if no_proxy_data.get('slot_1730_found') else '❌ NOT FOUND'}")
            if no_proxy_data.get('slot_1730_details'):
                print(f"   Details: {no_proxy_data['slot_1730_details']}")
        
        # Proxy Results
        print("\n🔍 WITH PROXY TEST RESULTS:")
        proxy_data = self.results.get('with_proxy', {})
        if 'error' in proxy_data:
            print(f"❌ Error: {proxy_data['error']}")
        else:
            print(f"🎫 Slots found: {proxy_data.get('slots_found', 0)}")
            print(f"🕐 17:30 slot: {'✅ FOUND' if proxy_data.get('slot_1730_found') else '❌ NOT FOUND'}")
        
        # Nearby Dates Analysis
        print("\n📅 NEARBY DATES ANALYSIS:")
        nearby_data = self.results.get('nearby_dates', {})
        for date, data in nearby_data.items():
            if 'error' in data:
                print(f"   {date}: ❌ Error")
            else:
                slots = data.get('slots_found', 0)
                has_1730 = '✅' if data.get('slot_1730_found') else '❌'
                print(f"   {date}: {slots} slots, 17:30: {has_1730}")
        
        # Visitor Count Analysis
        print("\n👥 VISITOR COUNT ANALYSIS:")
        visitor_data = self.results.get('visitor_counts', {})
        for visitors, data in visitor_data.items():
            if 'error' in data:
                print(f"   {visitors}: ❌ Error")
            else:
                slots = data.get('slots_found', 0)
                has_1730 = '✅' if data.get('slot_1730_found') else '❌'
                print(f"   {visitors}: {slots} slots, 17:30: {has_1730}")
        
        # Final Conclusions
        print("\n🎯 FINAL CONCLUSIONS:")
        
        # Check if any slots were found at all
        no_proxy_slots = self.results.get('no_proxy', {}).get('slots_found', 0)
        has_1730_no_proxy = self.results.get('no_proxy', {}).get('slot_1730_found', False)
        
        if no_proxy_slots == 0:
            print("❌ NO SLOTS FOUND FOR MARCH 28TH - This is the real issue!")
            print("   🔍 Possible reasons:")
            print("   • Tickets are genuinely sold out for March 28th")
            print("   • Tickets haven't been released yet for that date")
            print("   • The date is too far in the future (March 28, 2026)")
            print("   • Different product category needed (special tours, etc.)")
        else:
            print(f"✅ Found {no_proxy_slots} total slots for March 28th")
            if has_1730_no_proxy:
                print("✅ 17:30 slot IS available!")
            else:
                print("❌ 17:30 slot is NOT available, but other slots are")
        
        # Check proxy impact
        proxy_slots = self.results.get('with_proxy', {}).get('slots_found', 0)
        if proxy_slots != no_proxy_slots:
            print(f"⚠️  Proxy affects results: {no_proxy_slots} (no proxy) vs {proxy_slots} (with proxy)")
        
        print("\n" + "="*80)

async def main():
    """Main analysis execution"""
    logger.info("🚀 Starting final comprehensive analysis for March 28th tickets")
    
    analyzer = March28FinalAnalysis()
    
    # Run all tests
    await analyzer.test_without_proxy()
    await analyzer.test_with_proxy()
    await analyzer.test_nearby_dates()
    await analyzer.test_different_visitor_counts_detailed()
    
    # Generate final report
    analyzer.generate_final_report()
    
    # Save detailed results
    results_file = f"final_march28_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(analyzer.results, f, indent=2, default=str)
    
    logger.info(f"💾 Complete analysis saved to: {results_file}")

if __name__ == "__main__":
    asyncio.run(main())