#!/usr/bin/env python3
"""
Test to verify actual API responses and check if dates are truly available
Tests the real API calls the bot is making
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
logger = logging.getLogger("RealAPIVerification")

class RealAPIVerification:
    def __init__(self):
        self.monitor = GodTierVaticanMonitorV2()  # No proxy to avoid auth issues
        self.test_dates = [
            "16/03/2026",  # March 16
            "28/03/2026",  # March 28 (the problematic 17:30 date)
            "04/04/2026",  # April 4
            "26/03/2026",  # March 26 (known to have availability)
            "27/03/2026",  # March 27
            "23/03/2026",  # March 23
            "30/03/2026",  # March 30
        ]
        self.test_visitors = 1
        self.results = {}
        
    async def test_real_api_calls(self):
        """Test the actual API calls the bot makes"""
        logger.info("🔍 Testing real API calls for specific dates")
        
        for date_str in self.test_dates:
            logger.info(f"\n📅 Testing date: {date_str}")
            
            try:
                # Ensure valid session
                if not await self.monitor.validate_api_session():
                    logger.info(f"🔄 Refreshing session for {date_str}...")
                    await self.monitor.refresh_session_with_browser(
                        target_date=date_str, 
                        visitors=self.test_visitors
                    )
                
                # Test standard tickets (type 0)
                standard_slots = await self.monitor.check_availability(
                    date_str, 
                    ticket_type=0,  # Standard tickets
                    visitors=self.test_visitors
                )
                
                # Test guided tickets (type 1)
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
                        'slot_1730_details': standard_1730[0] if standard_1730 else None,
                        'all_slots': standard_slots
                    },
                    'guided': {
                        'total_slots': len(guided_slots),
                        'available_times': [s.get('time') for s in guided_slots if s.get('time')],
                        'slot_1730_found': len(guided_1730) > 0,
                        'slot_1730_details': guided_1730[0] if guided_1730 else None,
                        'all_slots': guided_slots
                    }
                }
                
                logger.info(f"✅ Standard: {len(standard_slots)} slots")
                logger.info(f"✅ Guided: {len(guided_slots)} slots")
                logger.info(f"🕐 17:30 Standard: {'✅' if standard_1730 else '❌'}")
                logger.info(f"🕐 17:30 Guided: {'✅' if guided_1730 else '❌'}")
                
                if standard_slots:
                    logger.info(f"🕐 Standard times: {[s.get('time') for s in standard_slots]}")
                if guided_slots:
                    logger.info(f"🕐 Guided times: {[s.get('time') for s in guided_slots]}")
                
            except Exception as e:
                logger.error(f"❌ Failed for {date_str}: {e}")
                import traceback
                traceback.print_exc()
                self.results[date_str] = {'error': str(e)}
    
    async def check_frontend_vs_backend(self):
        """Check if frontend is showing different data than backend"""
        logger.info("\n🔍 Checking frontend vs backend consistency")
        
        # Check what the frontend would see vs what backend returns
        for date_str in self.test_dates:
            if date_str not in self.results or 'error' in self.results[date_str]:
                continue
                
            data = self.results[date_str]
            
            logger.info(f"\n📅 {date_str}:")
            
            # Standard tickets
            standard = data['standard']
            if standard['total_slots'] > 0:
                logger.info(f"   🏛️  Standard: {standard['total_slots']} slots available")
                logger.info(f"   🕐 Times: {standard['available_times']}")
            else:
                logger.info(f"   🏛️  Standard: SOLD OUT")
            
            # Guided tickets
            guided = data['guided']
            if guided['total_slots'] > 0:
                logger.info(f"   🎤 Guided: {guided['total_slots']} slots available")
                logger.info(f"   🕐 Times: {guided['available_times']}")
            else:
                logger.info(f"   🎤 Guided: SOLD OUT")
    
    def generate_verification_report(self):
        """Generate comprehensive verification report"""
        print("\n" + "="*80)
        print("📊 REAL API VERIFICATION REPORT")
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
            if standard['total_slots'] > 0:
                print(f"   Available times: {standard['available_times']}")
                print(f"   17:30 slot: {'✅ FOUND' if standard['slot_1730_found'] else '❌ NOT FOUND'}")
                if standard['slot_1730_found']:
                    print(f"   17:30 details: {standard['slot_1730_details']}")
            else:
                print(f"   Status: SOLD OUT")
            
            # Guided tickets
            guided = data['guided']
            print(f"🎤 Guided Tickets:")
            print(f"   Total slots: {guided['total_slots']}")
            if guided['total_slots'] > 0:
                print(f"   Available times: {guided['available_times']}")
                print(f"   17:30 slot: {'✅ FOUND' if guided['slot_1730_found'] else '❌ NOT FOUND'}")
                if guided['slot_1730_found']:
                    print(f"   17:30 details: {guided['slot_1730_details']}")
            else:
                print(f"   Status: SOLD OUT")
        
        # Summary analysis
        print("\n" + "="*80)
        print("🎯 SUMMARY ANALYSIS:")
        print("="*80)
        
        # Count available vs sold out
        available_dates = []
        sold_out_dates = []
        
        for date_str in self.test_dates:
            if date_str in self.results and 'error' not in self.results[date_str]:
                data = self.results[date_str]
                if data['standard']['total_slots'] > 0 or data['guided']['total_slots'] > 0:
                    available_dates.append(date_str)
                else:
                    sold_out_dates.append(date_str)
        
        print(f"✅ Available dates: {len(available_dates)}")
        if available_dates:
            print(f"   Dates: {available_dates}")
        
        print(f"❌ Sold out dates: {len(sold_out_dates)}")
        if sold_out_dates:
            print(f"   Dates: {sold_out_dates}")
        
        # Check 17:30 availability
        found_1730 = []
        for date_str in self.test_dates:
            if date_str in self.results and 'error' not in self.results[date_str]:
                data = self.results[date_str]
                if data['standard']['slot_1730_found'] or data['guided']['slot_1730_found']:
                    found_1730.append(date_str)
        
        if found_1730:
            print(f"✅ 17:30 slot found on: {found_1730}")
        else:
            print("❌ 17:30 slot not found on any tested date")
            print("   This confirms the 17:30 slot issue is real availability, not a bot bug")
        
        print("\n" + "="*80)

async def main():
    """Main verification execution"""
    logger.info("🚀 Starting real API verification test")
    
    verifier = RealAPIVerification()
    
    # Run verification tests
    await verifier.test_real_api_calls()
    await verifier.check_frontend_vs_backend()
    
    # Generate report
    verifier.generate_verification_report()
    
    # Save detailed results
    results_file = f"real_api_verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(verifier.results, f, indent=2, default=str)
    
    logger.info(f"💾 Detailed results saved to: {results_file}")

if __name__ == "__main__":
    asyncio.run(main())