import json
import requests
import sys
import os

# Configure
COOKIES_FILE = "/app/vatican_cookies.json"
# Use a known valid ID from your previous scan (e.g., Tag 3 Standard)
# ID: 1685199261 (Musei Vaticani - Biglietti d'ingresso) from previous log
TICKET_ID = "1685199261" 
DATE = "27/02/2026"
VISITORS = 2

def ping_api():
    print(f"\n📡 PINGING API WITH SAVED COOKIES")
    print("="*60)
    
    if not os.path.exists(COOKIES_FILE):
        print(f"❌ Cookie file not found: {COOKIES_FILE}")
        print("   Run 'python get_cookies.py' first!")
        return

    # 1. Load Cookies
    with open(COOKIES_FILE, 'r') as f:
        cookie_list = json.load(f)
        
    session = requests.Session()
    
    # 2. Apply Cookies to Session
    print(f"🍪 Loading {len(cookie_list)} cookies...")
    for c in cookie_list:
        session.cookies.set(c['name'], c['value'], domain=c['domain'])
        
    # 3. Headers (Mimic Browser)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://tickets.museivaticani.va/"
    })
    
    # 4. Request
    url = f"https://tickets.museivaticani.va/api/visit/timeavail?lang=it&visitTypeId={TICKET_ID}&visitorNum={VISITORS}&visitDate={DATE}"
    print(f"🚀 GET {url}")
    
    try:
        response = session.get(url, timeout=10)
        
        print(f"📥 Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            slots = data.get("timetable", [])
            print(f"✅ SUCCESS! API Response received.")
            if slots:
                available = [t['time'] for t in slots if t['availability'] != 'SOLD_OUT']
                print(f"   🎉 Available Slots: {available}")
            else:
                print(f"   ❌ No slots available (or sold out).")
        else:
            print(f"❌ Failed. Response: {response.text[:200]}")
            
    except Exception as e:
        print(f"💥 Request Failed: {e}")

if __name__ == "__main__":
    ping_api()
