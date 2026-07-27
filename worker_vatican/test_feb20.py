import asyncio
import logging
from hydra_monitor import HydraBot

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("Feb20Test")

async def check_feb_20_availability():
    """
    Check Feb 20, 2026 for Standard Tickets
    With proper rate limiting to avoid bans
    """
    bot = HydraBot(use_proxies=True)
    
    # ✅ CORRECT: European format DD/MM/YYYY (Vatican API requirement)
    TEST_DATE = "20/02/2026"  # NOT "2026-02-20"
    TICKET_TYPE = 0  # Standard (MV-Biglietti)
    VISITORS = 2
    RATE_LIMIT_DELAY = 2.5  # Seconds between API calls (safe)
    
    logger.info("=" * 80)
    logger.info("🎯 VATICAN BOT - Feb 20, 2026 Availability Check")
    logger.info("=" * 80)
    logger.info(f"📅 Target Date: {TEST_DATE}")
    logger.info(f"👥 Visitors: {VISITORS}")
    logger.info(f"⏱️  Rate Limit: {RATE_LIMIT_DELAY}s delay between checks")
    logger.info("")
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        proxy = bot.get_random_proxy()
        
        browser = await p.chromium.launch(
            headless=False,  # Visible to debug
            proxy=proxy,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        
        context = await browser.new_context(
            locale="it-IT",
            timezone_id="Europe/Rome",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        
        page = await context.new_page()
        await bot.apply_stealth(context, page)
        
        # ===== STEP 1: EXTRACT ALL TICKET IDs =====
        logger.info("=" * 80)
        logger.info("STEP 1: Extracting All Standard Ticket IDs")
        logger.info("=" * 80)
        
        ticket_items = await bot.resolve_all_dynamic_ids(page, TICKET_TYPE, TEST_DATE, VISITORS)
        
        if not ticket_items:
            logger.error("❌ Failed to extract ticket IDs")
            await browser.close()
            return
        
        logger.info(f"\n✅ Extracted {len(ticket_items)} Ticket IDs:\n")
        for idx, item in enumerate(ticket_items, 1):
            logger.info(f"  {idx}. {item['name'][:50]:<50} | ID: {item['id']}")
        
        # ===== STEP 2: CHECK EACH ID WITH RATE LIMITING =====
        logger.info("\n" + "=" * 80)
        logger.info("STEP 2: Checking Availability (With Rate Limiting)")
        logger.info("=" * 80)
        
        available_tickets = []
        
        for idx, item in enumerate(ticket_items, 1):
            ticket_id = item['id']
            ticket_name = item['name']
            
            logger.info(f"\n[{idx}/{len(ticket_items)}] Checking: {ticket_name}")
            logger.info(f"  ID: {ticket_id}")
            
            # ✅ Use enhanced click-and-sniff with language support
            result = await bot.check_via_click(
                page=page,
                ticket_id=ticket_id,
                ticket_name=ticket_name,
                ticket_index=idx  # Pass index for language detection
            )
            
            slots = result.get("slots", [])
            language = result.get("language")
            
            if slots:
                lang_info = f" ({language})" if language else ""
                logger.info(f"  ✅ AVAILABLE{lang_info}! Found {len(slots)} time slots")
                available_tickets.append({
                    'name': ticket_name,
                    'id': ticket_id,
                    'language': language,
                    'slots': slots
                })
                
                # Print first few slots
                for slot in slots[:5]:
                    logger.info(f"    ⏰ {slot}")
                if len(slots) > 5:
                    logger.info(f"    ... and {len(slots) - 5} more")
            else:
                logger.info(f"  ❌ Sold Out")
            
            # RATE LIMITING: Wait before next check
            if idx < len(ticket_items):  # Don't wait after last item
                logger.info(f"  ⏳ Waiting {RATE_LIMIT_DELAY}s before next check...")
                await asyncio.sleep(RATE_LIMIT_DELAY)
        
        # ===== STEP 3: SUMMARY =====
        logger.info("\n" + "=" * 80)
        logger.info("FINAL RESULTS")
        logger.info("=" * 80)
        # Final summary
        logger.info("\n" + "="*50)
        logger.info("FINAL RESULTS")
        logger.info("="*50)
        
        if available_tickets:
            for ticket in available_tickets:
                lang_info = f" ({ticket['language']})" if ticket.get('language') else ""
                logger.info(f"📌 {ticket['name']}{lang_info}")
                logger.info(f"   ID: {ticket['id']}")
                logger.info(f"   Slots: {ticket['slots'][:10]}")  # First 10 slots
        else:
            logger.info("❌ No tickets available for this date")
            logger.info("   All standard tickets are sold out or date too far out")
        
        # Keep browser open for inspection
        logger.info("\n⏳ Keeping browser open for 10 seconds for inspection...")
        await asyncio.sleep(10)
        
        await browser.close()
        logger.info("=" * 80)
        logger.info("🏁 Test Complete!")
        logger.info("=" * 80)
        
        return available_tickets


if __name__ == "__main__":
    asyncio.run(check_feb_20_availability())
