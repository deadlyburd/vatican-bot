import asyncio
import logging
from playwright.async_api import async_playwright
import os
from hydra_monitor import HydraBot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DebugScraper")

async def packet_sniffer():
    bot = HydraBot(use_proxies=True)
    async with async_playwright() as p:
        proxy = bot.get_random_proxy()
        logger.info(f"Using Proxy: {proxy}")
        
        browser = await p.chromium.launch(
            headless=True,
            proxy=proxy,
            args=["--no-sandbox", "--disable-gpu"]
        )
        context = await browser.new_context(
            locale="it-IT",
            timezone_id="Europe/Rome",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = await context.new_page()
        await bot.apply_stealth(context, page)
        
        try:
            url = "https://tickets.museivaticani.va/home"
            logger.info(f"Navigating to {url}...")
            await page.goto(url, timeout=60000, wait_until="networkidle")
            
            # Screenshot
            await page.screenshot(path="debug_home.png")
            logger.info("Saved debug_home.png")
            
            # Dump HTML
            content = await page.content()
            with open("debug_home.html", "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("Saved debug_home.html")
            
            # Print Links
            links = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a')).map(a => ({href: a.href, text: a.innerText}));
            }""")
            
            logger.info(f"Found {len(links)} links:")
            for l in links[:20]: # Print first 20
                logger.info(f" - {l['text']} -> {l['href']}")
                
        except Exception as e:
            logger.error(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(packet_sniffer())
