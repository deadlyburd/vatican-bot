import asyncio
import json
import logging
import sys
import os
from datetime import datetime

# Ensure imports work
sys.path.append('/app')
sys.path.append('/app/worker_vatican')

try:
    from worker_vatican.hydra_monitor import HydraBot
except ImportError:
    # If running locally without docker structure
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from worker_vatican.hydra_monitor import HydraBot

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("CookieCollector")

async def collect_cookies():
    print(f"\n🍪 VATICAN COOKIE COLLECTOR")
    print("="*60)
    
    # Initialize Bot (Headless=True usually, but could be False if needed)
    bot = HydraBot(use_proxies=True)
    
    # Target Date (Arbitrary future date to ensure page loads)
    target_date = "27/02/2026"
    
    async with bot.get_browser() as browser:
        # Create Context with stealth
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="it-IT",
            timezone_id="Europe/Rome"
        )
        page = await context.new_page()
        await bot.apply_stealth(context, page)
        
        print(f"🕸️  Navigating to Vatican Tickets (Date: {target_date})...")
        
        # Use the bot's logic to navigate and resolve IDs
        # This will handle the Deep Link navigation and wait for Angular
        ids = await bot.resolve_all_dynamic_ids(page, ticket_type=0, target_date=target_date)
        
        if not ids:
            print("❌ Failed to resolve IDs (Page might not have loaded correctly).")
            return
            
        print(f"✅ Page Parsed! Found {len(ids)} Ticket Types.")
        for t in ids[:3]: # Show first 3
            print(f"   - {t['name']} (ID: {t['id']})")
            
        # Get Cookies
        cookies = await context.cookies()
        print(f"\n🍪 COLLECTED {len(cookies)} SESSION COOKIES")
        print("-" * 60)
        
        cookie_list = []
        for c in cookies:
            # Print minimal info
            print(f"   [{c['name']}] = {c['value'][:20]}... (Domain: {c['domain']})")
            cookie_list.append(c)
            
        # Save to file
        filename = "vatican_cookies.json"
        with open(filename, "w") as f:
            json.dump(cookie_list, f, indent=2)
            
        print("-" * 60)
        print(f"💾 Cookies saved to: {os.path.abspath(filename)}")
        
        # Verify API Access with these cookies
        print(f"\n🕵️  Verifying Cookies with Direct API Test...")
        # Just pick the first ID
        test_id = ids[0]['id']
        api_url = f"https://tickets.museivaticani.va/api/visit/timeavail?lang=it&visitTypeId={test_id}&visitorNum=2&visitDate=27/02/2026"
        
        js_fetch = f"""
        async () => {{
            const res = await fetch("{api_url}");
            return {{ status: res.status, json: await res.json() }};
        }}
        """
        try:
            result = await page.evaluate(js_fetch)
            if result['status'] == 200:
                print(f"✅ API Check SUCCESS! Status: 200")
                slots = result['json'].get('timetable', [])
                if slots:
                    print(f"   Timetable received ({len(slots)} slots). Session is Valid.")
                else:
                     print(f"   Timetable received (empty/sold out). Session is Valid.")
            else:
                print(f"❌ API Check Failed. Status: {result['status']}")
        except Exception as e:
            print(f"❌ API Check Error: {e}")

if __name__ == "__main__":
    asyncio.run(collect_cookies())
