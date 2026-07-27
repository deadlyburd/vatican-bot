import asyncio
import time
import os
import sys
import json

# Ensure imports work
sys.path.append('/app')
sys.path.append('/app/worker_vatican')

try:
    from worker_vatican.hydra_monitor import HydraBot, SESSION_FILE
except ImportError:
    from hydra_monitor import HydraBot, SESSION_FILE
    
try:
    from curl_cffi.requests import AsyncSession
except:
    print("❌ curl_cffi missing")

async def measure_speed():
    print("⚡ HEADLESS SPEED TEST (DEBUG)")
    print("="*60)
    
    bot = HydraBot(use_proxies=True)
    
    if not bot.session_cache.get("cookies"):
         print("❌ No cookies in cache.")
         return

    ids_cache = bot.session_cache.get("ids_cache", {})
    if not ids_cache:
         print("❌ No IDs in cache.")
         return

    date = list(ids_cache.keys())[0]
    t_id = ids_cache[date][0]['id']
    t_name = ids_cache[date][0]['name']
    
    print(f"🎯 Testing with ID: {t_id} ({t_name}) for Date: {date}")
    
    # Date conversion
    parts = date.split("-")
    api_date = f"{parts[2]}/{parts[1]}/{parts[0]}"
    
    # 3 Visitors because Standard Tickets default to 3 in my logic
    url = f"https://tickets.museivaticani.va/api/visit/timeavail?lang=it&visitTypeId={t_id}&visitorNum=3&visitDate={api_date}"
    
    print(f"🚀 GET {url}")
    
    cookie_dict = {c['name']: c['value'] for c in bot.session_cache['cookies']}
    print(f"🍪 Sending {len(cookie_dict)} cookies: {list(cookie_dict.keys())}")
    
    t0 = time.time()
    async with AsyncSession(verify=False, impersonate="chrome120") as s:
        s.cookies.update(cookie_dict)
        s.headers.update({
            "Referer": "https://tickets.museivaticani.va/",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        })
        
        resp = await s.get(url)
        t1 = time.time()
        
        print(f"📥 Status: {resp.status_code}")
        print(f"⏱️ Time: {(t1-t0)*1000:.2f} ms")
        print(f"📄 Body: {resp.text[:500]}...") # Print first 500 chars

        if resp.status_code == 200 and "timetable" in resp.text:
            print("✅ SUCCESS! Headless Check Works.")
        else:
            print("❌ FAILURE. Response unexpected.")

if __name__ == "__main__":
    asyncio.run(measure_speed())
