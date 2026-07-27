import asyncio
import sys
import os

# Ensure imports work
sys.path.append('/app')
sys.path.append('/app/worker_vatican')

try:
    from worker_vatican.hydra_monitor import HydraBot, SESSION_FILE
except ImportError:
    from hydra_monitor import HydraBot, SESSION_FILE

async def main():
    print(f"📂 Configured Session File: {SESSION_FILE}")
    print("🚀 Initializing Session Cache...")
    bot = HydraBot(use_proxies=True)
    
    async with bot.get_browser() as browser:
        # Create minimal context
        context = await browser.new_context(
            locale="it-IT",
            timezone_id="Europe/Rome"
        )
        page = await context.new_page()
        
        target_date = "27/02/2026"
        print(f"🕸️ Navigating for date: {target_date}")
        
        # This method should internally call self._save_session()
        ids = await bot.resolve_all_dynamic_ids(page, ticket_type=0, target_date=target_date)
        
        if ids:
            print(f"✅ Found {len(ids)} IDs.")
            if os.path.exists(SESSION_FILE):
                print(f"✅ Session File Created! Size: {os.path.getsize(SESSION_FILE)} bytes")
            else:
                 print(f"❌ Session File MISSING at {SESSION_FILE}")
        else:
            print("❌ No IDs found.")

if __name__ == "__main__":
    asyncio.run(main())
