import asyncio
import logging
from hydra_monitor import HydraBot

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("CookieTest")

async def test_cookie_session():
    """
    Test that cookies from deep link navigation are properly maintained
    for subsequent API calls.
    """
    bot = HydraBot(use_proxies=True)
    
    # Use a CLOSER date to find real availability
    TEST_DATE = "2026-02-05"  # Much closer - more likely to have slots
    VISITORS = 2
    
    logger.info("🚀 Cookie Session Test")
    logger.info(f"📅 Testing Date: {TEST_DATE} (closer date for real availability)\n")
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        proxy = bot.get_random_proxy()
        
        browser = await p.chromium.launch(
            headless=False,  # VISIBLE for debugging
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
        
        logger.info("=" * 80)
        logger.info("STEP 1: Navigate to Deep Link & Harvest Cookies")
        logger.info("=" * 80)
        
        # This should set cookies
        ticket_items = await bot.resolve_all_dynamic_ids(page, 0, TEST_DATE, VISITORS)
        
        if not ticket_items:
            logger.error("❌ No tickets found!")
            await browser.close()
            return
        
        logger.info(f"✅ Found {len(ticket_items)} ticket IDs")
        
        # Check cookies
        cookies = await context.cookies()
        logger.info(f"\n🍪 Active Cookies ({len(cookies)}):")
        for cookie in cookies[:5]:  # Show first 5
            logger.info(f"  - {cookie['name']}: {cookie['value'][:30]}...")
        
        logger.info("\n" + "=" * 80)
        logger.info("STEP 2: Call API (Should Use Same Cookies)")
        logger.info("=" * 80)
        
        # Test first ticket
        test_item = ticket_items[0]
        logger.info(f"\n📝 Testing: {test_item['name']} (ID: {test_item['id']})")
        
        slots = await bot.check_timeavail_api(
            page=page,
            visit_type_id=test_item['id'],
            target_date=TEST_DATE,
            visitors=VISITORS,
            language="it",
            visit_lang=""
        )
        
        logger.info("\n" + "=" * 80)
        logger.info("RESULTS")
        logger.info("=" * 80)
        
        if slots:
            logger.info(f"✅ SUCCESS! Found {len(slots)} available time slots:")
            for slot in slots[:10]:
                logger.info(f"  ⏰ {slot}")
        else:
            logger.info("⚠️ No slots returned - might be sold out or cookie issue")
            logger.info("💡 Try testing with browser visible to debug")
        
        # Keep browser open for 5 seconds to inspect
        logger.info("\n⏳ Keeping browser open for inspection...")
        await asyncio.sleep(5)
        
        await browser.close()
        logger.info("🏁 Test Complete!")

if __name__ == "__main__":
    asyncio.run(test_cookie_session())
