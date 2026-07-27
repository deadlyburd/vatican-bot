import asyncio
import json
import os
import logging
from curl_cffi.requests import AsyncSession

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SESSION_FILE = "vatican_session.json"

async def verify_languages():
    if not os.path.exists(SESSION_FILE):
        logger.error(f"❌ Session file {SESSION_FILE} not found. Run the bot first.")
        return

    with open(SESSION_FILE, 'r') as f:
        session_data = json.load(f)

    cookies = session_data.get("cookies", [])
    ids_cache = session_data.get("ids_cache", {})

    if not cookies or not ids_cache:
        logger.error("❌ Session cache is empty.")
        return

    # Convert cookies to dict
    cookie_dict = {c['name']: c['value'] for c in cookies}

    # Find a Guided Tour ID
    guided_id = None
    guided_name = None
    test_date = None

    for date, items in ids_cache.items():
        for item in items:
            name = item['name']
            # Look for "Guidat" (Italian) or "Guided" (English)
            if "uidat" in name or "uided" in name: 
                guided_id = item['id']
                guided_name = name
                test_date = date
                break
        if guided_id:
            break
    
    if not guided_id:
        logger.warning("⚠️ No Guided Tour found in cache. Listing available items to check:")
        for date, items in list(ids_cache.items())[:1]:
            for item in items:
                logger.info(f" - {item['name']} (ID: {item['id']})")
        logger.warning("Cannot test language logic without a Guided Tour ID.")
        return

    logger.info(f"🧪 Testing Content for: {guided_name} (ID: {guided_id}) on {test_date}")

    # Languages to test (User said 3 letters)
    languages = ["ITA", "ENG", "FRA", "DEU", "SPA"]
    
    # Prepare Date
    if "-" in test_date:
        parts = test_date.split("-")
        api_date = f"{parts[2]}/{parts[1]}/{parts[0]}" # YYYY-MM-DD -> DD/MM/YYYY
    else:
        api_date = test_date

    async with AsyncSession(verify=False, impersonate="chrome120") as s:
        s.cookies.update(cookie_dict)
        s.headers.update({
            "Referer": "https://tickets.museivaticani.va/"
        })

        for lang in languages:
            url = f"https://tickets.museivaticani.va/api/visit/timeavail?lang={lang}&visitTypeId={guided_id}&visitorNum=2&visitDate={api_date}"
            try:
                resp = await s.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    slots = [t['time'] for t in data.get('timetable', []) if t['availability'] != 'SOLD_OUT']
                    logger.info(f"   [{lang.upper()}] Status: {resp.status_code} | Slots Found: {len(slots)}")
                    if len(slots) > 0:
                        logger.info(f"      Slots: {slots[:3]}...")
                else:
                    logger.error(f"   [{lang.upper()}] Failed: Status {resp.status_code}")
            except Exception as e:
                logger.error(f"   [{lang.upper()}] Error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_languages())
