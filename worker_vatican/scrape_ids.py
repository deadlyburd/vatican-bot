import asyncio
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright
from hydra_monitor import HydraBot

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("MasterScraper")

# Tags to Scan
TAGS = [
    "MV-Biglietti", 
    "MV-Visite-Guidate", 
    "MV-Prime", 
    "MV-Giardini", 
    "MV-Ville",
    "MV-Tour" # Frontend uses this, checking just in case
]

# Visitor Types (User hint: fromtag/6 might be key)
# 1 = Individual?
# 2 = ?
# 6 = ?
VISITOR_TYPES = [1, 2, 6]

# Date to check (Must be far in future to ensure availability)
TARGET_DATE = "2026-05-25" 

def get_ts(date_str):
    rome = ZoneInfo("Europe/Rome")
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=rome)
    return int(midnight.timestamp() * 1000)

async def scrape_ids():
    bot = HydraBot(use_proxies=True)
    all_tickets = {} # ID -> {name, tag, type}
    
    async with async_playwright() as p:
        # Launch once
        proxy = bot.get_random_proxy()
        logger.info(f"Using Proxy: {proxy}")
        
        browser = await p.chromium.launch(
            headless=True,
            proxy=proxy,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        
        context = await browser.new_context(
            locale="it-IT", 
            timezone_id="Europe/Rome",
             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = await context.new_page()
        await bot.apply_stealth(context, page)
        
        ts = get_ts(TARGET_DATE)
        
        for tag in TAGS:
            for v_type in VISITOR_TYPES:
                try:
                    # Construct URL
                    # Format: /home/fromtag/{v_type}/{TIMESTAMP}/{TAG}/1
                    # The trailing /1 might be volumeId or something else.
                    url = f"https://tickets.museivaticani.va/home/fromtag/{v_type}/{ts}/{tag}/1"
                    logger.info(f"Scanning: {tag} (Type {v_type}) -> {url}")
                    
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(4000) # Wait for cards
                    
                    # Extract Data
                    # We want the ID from data-cy="bookTicket_{ID}"
                    # AND the Title (usually in a h1/h2/div above it)
                    
                    # Script to extract with improved DOM traversal
                    items = await page.evaluate("""() => {
                        const results = [];
                        
                        // Step 1: Get all ticket titles
                        const titles = [];
                        document.querySelectorAll('.muvaTicketTitle').forEach(el => {
                            titles.push({
                                text: el.textContent.trim(),
                                element: el
                            });
                        });
                        
                        // Step 2: Get all buttons with IDs
                        const buttons = [];
                        document.querySelectorAll("[data-cy^='bookTicket_']").forEach(btn => {
                            const id = btn.getAttribute("data-cy").split("_")[1];
                            buttons.push({
                                id: id,
                                element: btn
                            });
                        });
                        
                        // Step 3: Try to match titles with buttons
                        titles.forEach(titleInfo => {
                            const titleEl = titleInfo.element;
                            let matchedButton = null;
                            
                            let container = titleEl.closest('app-ticket-card') || 
                                           titleEl.closest('.card') || 
                                           titleEl.closest('[class*="ticket"]') ||
                                           titleEl.closest('div[class*="muva"]');
                            
                            if (container) {
                                const btn = container.querySelector('[data-cy^="bookTicket_"]');
                                if (btn) {
                                    matchedButton = btn.getAttribute("data-cy").split("_")[1];
                                }
                            }
                            
                            if (matchedButton) {
                                results.push({
                                    id: matchedButton,
                                    title: titleInfo.text
                                });
                            }
                        });
                        
                        // Step 4: For unmatched buttons, search up parent tree
                        buttons.forEach(btnInfo => {
                            const alreadyMatched = results.some(r => r.id === btnInfo.id);
                            if (alreadyMatched) return;
                            
                            const btn = btnInfo.element;
                            let title = "Unknown Title";
                            
                            // Search up to 10 parent levels
                            let parent = btn.parentElement;
                            for (let i = 0; i < 10 && parent; i++) {
                                const titleEl = parent.querySelector('.muvaTicketTitle, h1, h2, h3, h4, .card-title, .title-class');
                                if (titleEl && titleEl.innerText && titleEl.innerText.trim()) {
                                    title = titleEl.innerText.trim();
                                    break;
                                }
                                parent = parent.parentElement;
                            }
                            
                            // Fallback: use container text
                            if (title === "Unknown Title") {
                                let container = btn.closest('div.card') || btn.closest('div.row') || btn.parentElement.parentElement;
                                if (container && container.innerText) {
                                    title = container.innerText.split('\\n')[0].substring(0, 50);
                                }
                            }
                            
                            results.push({id: btnInfo.id, title: title});
                        });
                        
                        return results;
                    }""")
                    
                    logger.info(f"Found {len(items)} items.")
                    
                    for item in items:
                        tid = item['id']
                        if tid not in all_tickets:
                            all_tickets[tid] = {
                                "id": tid,
                                "name": item['title'],
                                "tag": tag,
                                "visitor_type": v_type
                            }
                        else:
                            # Update with better name if needed?
                            pass
                            
                except Exception as e:
                    logger.error(f"Error scanning {tag}/{v_type}: {e}")
                    
        await browser.close()
        
    # Save Results
    results_list = list(all_tickets.values())
    logger.info(f"Total Unique Tickets Found: {len(results_list)}")
    
    with open("vatican_tickets.json", "w", encoding="utf-8") as f:
        json.dump(results_list, f, indent=2, ensure_ascii=False)
        
if __name__ == "__main__":
    asyncio.run(scrape_ids())
