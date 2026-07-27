
import asyncio
import logging
from datetime import datetime
import sys
import os

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from worker_vatican.god_tier_monitor_v2 import GodTierVaticanMonitorV2

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def debug_scraping():
    monitor = GodTierVaticanMonitorV2()
    
    # Dates to check
    dates_to_check = [
        "26/03/2026", # Thursday (User specifically asked for this)
        "23/03/2026", # Monday
        "30/03/2026"  # Monday
    ]
    
    for date_str in dates_to_check:
        logger.info(f"--- Checking date: {date_str} ---")
        
        # Try to refresh session and scrape IDs
        success = await monitor.refresh_session_with_browser(target_date=date_str, visitors=1)
        
        if success:
            logger.info(f"✅ Scraping successful for {date_str}")
            
            # Check what IDs were cached
            # Use the correct key format: {date}_v{visitors}
            cache_key = f"{date_str}_v1"
            cached_ids = monitor.session_cache.get('ids_cache', {}).get(cache_key, [])
            
            if cached_ids:
                logger.info(f"Found {len(cached_ids)} IDs for {date_str} (Key: {cache_key}):")
                for item in cached_ids:
                    logger.info(f"  - {item['name']} (ID: {item['id']})")
                
                # Check availability for the first ID (Standard Ticket)
                first_id = cached_ids[0]['id']
                logger.info(f"Checking availability for ID {first_id} on {date_str}...")
                
                slots = await monitor.check_availability(date_str, ticket_type=0, visitors=1)
                if slots:
                    logger.info(f"✅ Found {len(slots)} slots for {date_str}!")
                    try:
                        times = [s.get('time', 'N/A') for s in slots]
                        logger.info(f"   Times: {times}")
                    except Exception as e:
                        logger.error(f"Error extracting times: {e}")
                        logger.info(f"First slot raw: {slots[0]}")
                else:
                    logger.warning(f"❌ No slots found for {date_str} with ID {first_id}")
            else:
                logger.warning(f"⚠️ No IDs found in cache for {date_str} despite success (Key: {cache_key})")
                
                # Check ALL cache
                all_ids = monitor.session_cache.get('ids_cache', {}).get('__ALL__', [])
                if all_ids:
                    logger.info(f"Found {len(all_ids)} IDs in __ALL__ cache:")
                    for item in all_ids:
                        logger.info(f"  - {item['name']} (ID: {item['id']})")
        else:
            logger.error(f"❌ Scraping failed for {date_str}")

if __name__ == "__main__":
    asyncio.run(debug_scraping())
