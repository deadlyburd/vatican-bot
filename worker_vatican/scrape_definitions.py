import asyncio
import json
import logging
from playwright.async_api import async_playwright
# Import HydraBot to reuse stealth/proxy logic
# Assuming hydra_monitor.py is in the same directory
from hydra_monitor import HydraBot

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("Scraper")

async def scrape_all_definitions():
    bot = HydraBot(use_proxies=True)
    # We need to run a browser instance
    async with async_playwright() as p:
        # Launch browser (Reuse HydraBot proxy logic if possible, or just launch directly)
        proxy_config = bot.get_random_proxy()
        logger.info(f"Using Proxy: {proxy_config}")

        browser = await p.chromium.launch(
            headless=True, # Headless for speed, but maybe False if we need to see
            proxy=proxy_config,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--hide-scrollbars", 
                "--disable-gpu", 
            ]
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
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000) # Wait for cards to load

            # Scraping Logic
            # The page usually lists "Singoli", "Gruppi", etc.
            # We want to iterate everything.
            # Usually there are cards with 'details' or 'prenota' buttons.
            
            # Strategy: Get all 'section' or 'card' elements that represent ticket categories
            # Metadata is usually in the URL the card leads to, or attached to the button.
            
            # Let's try to extract from the visible text first to see what we have.
            # We will use a script to traverse the DOM.
            
            definitions = await page.evaluate("""() => {
                const results = [];
                // Look for elements that look like Ticket Cards
                // Selector might be something like .card-body or similar.
                // We'll broaden the search to any 'a' tag that links to '/details/' or '/calendar/'
                
                const links = Array.from(document.querySelectorAll('a[href*="/details/"], a[href*="/calendar/"]'));
                
                links.forEach(link => {
                    const href = link.getAttribute('href');
                    let id = "";
                    let type = "UNKNOWN";
                    
                    // Extract ID from URL
                    // Example: /home/calendar/visit/Biglietti-Musei-Vaticani-e-Cappella-Sistina/1
                    // Example: /home/details/1602099201
                    
                    const parts = href.split('/');
                    const lastPart = parts[parts.length - 1];
                    const secondLastPart = parts[parts.length - 2];
                    
                    if (!isNaN(lastPart)) {
                         id = lastPart; // Likely the ID
                    } else if (!isNaN(secondLastPart)) { 
                         id = secondLastPart; // Sometimes ID is not last?
                    }
                    
                    // Extract Title from the card
                    // Helper to look up the DOM tree for a heading
                    let title = link.textContent.trim();
                    let parent = link.parentElement;
                    let foundTitle = false;
                    for(let i=0; i<5; i++) {
                        if(!parent) break;
                        const h = parent.querySelector('h1, h2, h3, h4, h5, .card-title, .title');
                        if (h) {
                             title = h.textContent.trim();
                             foundTitle = true;
                             break;
                        }
                        parent = parent.parentElement;
                    }
                    
                    if (id) {
                        results.push({
                            id: id,
                            name: title,
                            url: href,
                            raw_text: link.textContent.trim()
                        });
                    }
                });
                return results;
            }""")
            
            # Deduplicate
            unique_defs = {}
            for d in definitions:
                unique_defs[d['id']] = d
            
            final_list = list(unique_defs.values())
            logger.info(f"Found {len(final_list)} unique ticket definitions.")
            
            # Save to file
            with open("vatican_tickets.json", "w", encoding="utf-8") as f:
                json.dump(final_list, f, indent=2, ensure_ascii=False)
                
            logger.info("Saved to vatican_tickets.json")
            return final_list

        except Exception as e:
            logger.error(f"Scrape failed: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_all_definitions())
