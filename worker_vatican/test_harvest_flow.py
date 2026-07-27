import asyncio
import logging
from hydra_monitor import HydraBot

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("TestHarvest")

async def test_harvest_and_check():
    """
    Test the complete workflow:
    1. Navigate to deep link
    2. Harvest ticket IDs
    3. Call timeavail API for each ID with correct visitLang parameter
    """
    bot = HydraBot(use_proxies=True)
    
    # Test Configuration
    TEST_DATE = "2026-02-19"
    VISITORS = 2
    
    logger.info("🚀 Starting Comprehensive Harvest + API Test")
    logger.info(f"📅 Date: {TEST_DATE}, Visitors: {VISITORS}\n")
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        proxy = bot.get_random_proxy()
        
        browser = await p.chromium.launch(
            headless=True,
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
        
        # Test 1: Standard Tickets (visitLang = empty)
        logger.info("=" * 80)
        logger.info("TEST 1: STANDARD TICKETS (MV-Biglietti)")
        logger.info("=" * 80)
        
        standard_items = await bot.resolve_all_dynamic_ids(page, 0, TEST_DATE, VISITORS)
        
        if standard_items:
            logger.info(f"✅ Harvested {len(standard_items)} Standard Ticket IDs\n")
            
            # Test first ID
            item = standard_items[0]
            logger.info(f"📝 Testing: {item['name']} (ID: {item['id']})")
            
            slots = await bot.check_via_api(
                page=page,
                visit_type_id=item['id'],
                target_date=TEST_DATE,
                visitors=VISITORS,
                language="it",
                visit_lang=""  # Empty for standard tickets
            )
            
            if slots:
                logger.info(f"  ✅ {len(slots)} slots available!")
                for slot in slots[:5]:
                    logger.info(f"    ⏰ {slot}")
            else:
                logger.info(f"  ❌ No slots available")
        else:
            logger.error("❌ No standard ticket IDs found!")
        
        # Test 2: Guided Tours (visitLang = ENG, FRA, ITA, DEU, SPA)
        logger.info("\n" + "=" * 80)
        logger.info("TEST 2: GUIDED TOURS (MV-Visite-Guidate)")
        logger.info("=" * 80)
        
        tour_items = await bot.resolve_all_dynamic_ids(page, 1, TEST_DATE, VISITORS)
        
        if tour_items:
            logger.info(f"✅ Harvested {len(tour_items)} Guided Tour IDs\n")
            
            # Test with different languages
            TOUR_LANGUAGES = ["ENG", "FRA", "ITA", "DEU", "SPA"]
            
            for lang in TOUR_LANGUAGES:
                logger.info(f"🌍 Testing Language: {lang}")
                
                # Test first tour ID with this language
                if tour_items:
                    item = tour_items[0]
                    
                    slots = await bot.check_via_api(
                        page=page,
                        visit_type_id=item['id'],
                        target_date=TEST_DATE,
                        visitors=VISITORS,
                        language="it",
                        visit_lang=lang  # Language-specific for guided tours
                    )
                    
                    if slots:
                        logger.info(f"  ✅ {len(slots)} slots available for {lang}!")
                        for slot in slots[:3]:
                            logger.info(f"    ⏰ {slot}")
                    else:
                        logger.info(f"  ❌ No slots available for {lang}")
                
                logger.info("")
        else:
            logger.error("❌ No guided tour IDs found!")
        
        await browser.close()
        logger.info("=" * 80)
        logger.info("🏁 Test Complete!")
        logger.info("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_harvest_and_check())

