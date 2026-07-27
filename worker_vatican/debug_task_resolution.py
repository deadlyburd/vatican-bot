
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

async def debug_task_resolution_logic():
    """
    Mimics the logic inside tasks.py's resolve_ticket_id function
    to see exactly what ID it picks for March 26.
    """
    monitor = GodTierVaticanMonitorV2()
    date_str = "26/03/2026"
    visitors = 1
    
    # Simulate what tasks.py would be looking for
    # Standard Ticket
    target_ticket_name = "Musei Vaticani - Biglietti d'ingresso"
    ticket_type = 0 # Standard
    
    logger.info(f"🔍 Debugging Task Resolution Logic for '{target_ticket_name}' on {date_str}...")
    
    # 1. Refresh Session & Scrape IDs
    logger.info("1️⃣ Refreshing session and scraping IDs...")
    success = await monitor.refresh_session_with_browser(target_date=date_str, visitors=visitors)
    
    if not success:
        logger.error("❌ Failed to refresh session")
        return

    # 2. Get Resolved IDs (simulating bot.resolve_all_dynamic_ids)
    # In god_tier_monitor_v2, this info is in the cache
    cache = monitor.session_cache.get('ids_cache', {})
    
    # Find the key
    found_key = None
    for key in cache.keys():
        if date_str in key:
            found_key = key
            break
            
    if not found_key:
        logger.error(f"❌ No cache key found for {date_str}")
        return
        
    resolved_ids = cache[found_key]
    logger.info(f"📂 Found {len(resolved_ids)} candidates.")

    # 3. RUN THE EXACT LOGIC FROM tasks.py
    logger.info("\n3️⃣ Running tasks.py matching logic...")
    
    fresh_id = None
    exact_match = None
    
    # Strategy 1: Exact substring match
    for item in resolved_ids:
        r_name = item.get('name', '').lower()
        t_name = target_ticket_name.lower()
        
        if t_name in r_name or r_name in t_name:
            if ticket_type == 0 and "lunch" in r_name: continue
            exact_match = item['id']
            logger.info(f"✅ Strategy 1 (Substring): '{target_ticket_name}' -> ID {exact_match} ('{item['name']}')")
            break
    
    # Strategy 2: Keyword matching (if no exact match)
    if not exact_match:
        logger.info("⚠️ Strategy 1 failed. Trying Strategy 2 (Keywords)...")
        # Extract key terms from ticket name
        keywords = []
        t_lower = target_ticket_name.lower()
        
        if 'musei' in t_lower:
            keywords.extend(['musei', 'vaticani', 'aree', 'museali'])
        elif 'palazzo' in t_lower:
            keywords.extend(['palazzo', 'papale'])
        elif 'specola' in t_lower:
            keywords.extend(['specola', 'vaticana'])
        
        if 'biglietti' in t_lower or 'admission' in t_lower or 'ingresso' in t_lower:
            keywords.extend(['biglietti', 'ingresso'])
        if 'visita' in t_lower or 'guided' in t_lower or 'tour' in t_lower:
            keywords.extend(['visita', 'guidata'])
        
        best_match = None
        best_score = 0
        
        for item in resolved_ids:
            r_name = item.get('name', '').lower()
            score = sum(1 for kw in keywords if kw in r_name)
            
            if 'musei' in t_lower and 'palazzo' in r_name: continue
            if 'palazzo' in t_lower and 'musei' in r_name: continue
            if ticket_type == 0 and any(x in r_name for x in ['lunch', 'pranzo', 'pellegrinaggi']): continue
            
            if score > best_score:
                best_score = score
                best_match = item['id']
                logger.info(f"   Candidate: {item['name']} (Score: {score})")
        
        if best_match and best_score >= 2:
            exact_match = best_match
            logger.info(f"✅ Strategy 2 (Keywords): Match found -> ID {exact_match} (score: {best_score})")

    # Strategy 3: First standard ticket fallback
    if not exact_match and ticket_type == 0:
        logger.info("⚠️ Strategy 2 failed. Trying Strategy 3 (Fallback)...")
        for item in resolved_ids:
            r_name = item.get('name', '').lower()
            if any(x in r_name for x in ['biglietti', 'ingresso', 'aree museali', 'museali']):
                if not any(x in r_name for x in ['lunch', 'pranzo', 'pellegrinaggi', 'gruppi', 'palazzo', 'specola']):
                    exact_match = item['id']
                    logger.info(f"✅ Strategy 3 (Fallback): Using first standard ticket -> ID {exact_match} ('{item['name']}')")
                    break

    # FINAL VERDICT
    if exact_match:
        logger.info(f"\n🎉 FINAL RESOLUTION: ID {exact_match}")
        
        # Verify against known correct ID
        KNOWN_ID = 781814287 # From previous debug
        if int(exact_match) == KNOWN_ID:
            logger.info("✅ SUCCESS: Matches known correct ID!")
        else:
            logger.warning(f"⚠️ MISMATCH: Expected {KNOWN_ID}, got {exact_match}")
            
            # Find what the known ID corresponds to
            for item in resolved_ids:
                if int(item['id']) == KNOWN_ID:
                    logger.info(f"   (Known ID {KNOWN_ID} is: '{item['name']}')")
    else:
        logger.error("❌ FAILED: Could not resolve any ID.")

if __name__ == "__main__":
    asyncio.run(debug_task_resolution_logic())
