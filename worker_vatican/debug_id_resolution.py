
import asyncio
import logging
import os
import sys
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from god_tier_monitor_v2 import GodTierVaticanMonitorV2

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def debug_id_resolution():
    monitor = GodTierVaticanMonitorV2()
    date_str = "26/03/2026"
    visitors = 1
    
    logger.info(f"🔍 Debugging ID Resolution for {date_str}...")
    
    # 1. Refresh Session & Scrape IDs
    logger.info("1️⃣ Refreshing session and scraping IDs...")
    success = await monitor.refresh_session_with_browser(target_date=date_str, visitors=visitors)
    
    if not success:
        logger.error("❌ Failed to refresh session")
        return

    # 2. Inspect Cache
    logger.info("2️⃣ Inspecting Scraped IDs...")
    
    # The cache key format in god_tier_monitor_v2 is usually just the date_str or date_str + visitors
    # Let's check what's in the cache
    cache = monitor.session_cache.get('ids_cache', {})
    
    # Try to find the key for our date
    found_key = None
    for key in cache.keys():
        if date_str in key:
            found_key = key
            break
            
    if not found_key:
        logger.error(f"❌ No cache key found for {date_str}. Available keys: {list(cache.keys())}")
        return
        
    cached_items = cache[found_key]
    logger.info(f"📂 Found {len(cached_items)} items for key '{found_key}':")
    
    for idx, item in enumerate(cached_items):
        logger.info(f"   [{idx}] ID: {item['id']} | Name: {item['name']}")

    # 3. Simulate Selection Logic
    logger.info("\n3️⃣ Simulating Selection Logic (Standard Ticket - Type 0)...")
    
    # Copy-paste logic from god_tier_monitor_v2.py (approximate)
    # Usually it looks for "Musei Vaticani - Biglietti d'ingresso"
    
    target_names = [
        "Musei Vaticani - Biglietti d'ingresso",
        "Admission tickets - Vatican Museums",
        "Vatican Museums - Admission tickets"
    ]
    
    selected_item = None
    
    # Exact Match
    for item in cached_items:
        if item['name'] in target_names:
            selected_item = item
            logger.info(f"✅ Exact Match Found: {item['name']} (ID: {item['id']})")
            break
            
    # Fuzzy Match if no exact
    if not selected_item:
        logger.info("⚠️ No exact match. Trying fuzzy...")
        for item in cached_items:
            name_lower = item['name'].lower()
            if "musei vaticani" in name_lower and "ingresso" in name_lower:
                selected_item = item
                logger.info(f"✅ Fuzzy Match (Italian): {item['name']} (ID: {item['id']})")
                break
            if "vatican museums" in name_lower and "admission" in name_lower:
                selected_item = item
                logger.info(f"✅ Fuzzy Match (English): {item['name']} (ID: {item['id']})")
                break

    if not selected_item:
        logger.error("❌ FAILED TO SELECT ANY TICKET! Bot would see 'Unknown' or fail.")
        
        # Check what IT WOULD pick if we asked for "Gardens"
        logger.info("\nChecking for other types...")
        for item in cached_items:
            if "Giardini" in item['name'] or "Gardens" in item['name']:
                logger.info(f"   🌱 Gardens Ticket: {item['name']} (ID: {item['id']})")

if __name__ == "__main__":
    asyncio.run(debug_id_resolution())
