import asyncio
import logging
from worker_vatican.hydra_monitor import HydraBot

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("DebugDOM")

async def debug_dom():
    bot = HydraBot(use_proxies=True)
    async with bot.get_browser() as browser:
        page = await browser.new_page()
        
        # Target a known date (Feb 27, 2026 - future)
        # Using the Deep Link construction from hydra_monitor
        ts = bot.get_vatican_timestamp("27/02/2026")
        
        # Standard Tickets (Visitors=3)
        url = f"https://tickets.museivaticani.va/home/fromtag/3/{ts}/MV-Biglietti/1"
        
        logger.info(f"Navigating to: {url}")
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000) # Give it time to render
        
        # 1. Dump HTML
        content = await page.content()
        with open("/app/debug_page.html", "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("💾 Saved HTML to /app/debug_page.html")
        
        # 2. Test Selectors
        buttons_count = await page.locator("[data-cy^='bookTicket_']").count()
        logger.info(f"🔢 BUTTONS FOUND: {buttons_count}")
        
        if buttons_count == 0:
             logger.warning("⚠️ No bookTicket_ buttons found! Dumping all buttons to see attributes...")
             # Dump attributes of first 5 buttons to find the new ID pattern
             attrs = await page.evaluate("""() => {
                 return Array.from(document.querySelectorAll('button')).slice(0, 5).map(b => b.outerHTML);
             }""")
             for a in attrs:
                 logger.info(f"🔘 Button: {a}")
        
        # 3. Try alternative (Class based? Text based?)
        titles = await page.locator(".muvaTicketTitle").all_inner_texts()
        logger.info(f"📝 Found Titles ({len(titles)}): {titles}")
        
        await page.close()

if __name__ == "__main__":
    asyncio.run(debug_dom())
