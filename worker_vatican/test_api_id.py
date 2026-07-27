import requests
import json
from datetime import datetime

# ID scraped previously (e.g., Standard Entry or similar)
# From vatican_tickets.json: "1750097398" (Standard Entry / PRENOTA)
TEST_ID = "1750097398" 
TEST_DATE = "19/02/2026" # Far future to ensure calendar is open/empty
VISIT_LANG = "" # Empty for Standard
LANG = "en"

url = "https://tickets.museivaticani.va/api/visit/timeavail"

params = {
    "lang": LANG,
    "visitLang": VISIT_LANG,
    "visitTypeId": TEST_ID,
    "visitorNum": "2",
    "visitDate": TEST_DATE
}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://tickets.museivaticani.va/"
}

print(f"🚀 Testing API with ID: {TEST_ID}")
print(f"📅 Date: {TEST_DATE}")
print(f"🔗 URL: {url}")

try:
    response = requests.get(url, params=params, headers=headers, timeout=10)
    print(f"📡 Status Code: {response.status_code}")
    print(f"📦 Response: {response.text[:500]}...")
    
    if response.status_code == 200:
        data = response.json()
        print("✅ API Success! ID appears valid/stable.")
    else:
        print("❌ API Failed. ID might be dynamic/expired.")
        
except Exception as e:
    print(f"🔥 Error: {e}")
