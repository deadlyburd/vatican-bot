#!/usr/bin/env python3
"""
LIVE VATICAN SNIPE - Using exact working recap format from lightning_snipe.py
"""
import requests, json, sys, time
from datetime import date

BASE = "https://tickets.museivaticani.va"
BACKEND = "http://localhost:8000"

H_XHR = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE}/",
    "Origin": BASE,
    "Content-Type": "application/json",
}
HC = {**H_XHR, "Referer": f"{BASE}/home/checkout"}
del HC["X-Requested-With"]

TARGET_DATE = "28/07/2026"
VISITORS = 4
ADULTS = 4
CHILDREN = 0

print("=" * 60)
print("🎯 LIVE VATICAN SNIPE — July 28, 2026")
print("=" * 60)

s = requests.Session()

# Step 1: Search
print("\n1️⃣  SEARCH...")
s.headers.update(H_XHR)
r = s.get(f"{BASE}/api/search/resultPerTag", params={
    "lang": "it", "visitorNum": str(VISITORS), "visitDate": TARGET_DATE,
    "area": "1", "who": "", "page": "0", "tag": "MV-Biglietti"
}, timeout=10)
print(f"   Status: {r.status_code}")

tid = None
for v in r.json().get("visits", []):
    name = v.get("name", "").lower()
    if "musei vaticani" in name and "ingresso" in name:
        tid = v.get("id")
        print(f"   Vatican Museums id={tid} | {v.get('availability')}")
        break

if not tid:
    print("❌ Not found")
    sys.exit(1)

# Step 2: Timeavail
print("\n2️⃣  TIMEAVAIL...")
r2 = s.get(f"{BASE}/api/visit/timeavail", params={
    "lang": "it", "visitLang": "", "visitTypeId": str(tid),
    "visitorNum": str(VISITORS), "visitDate": TARGET_DATE,
}, timeout=10)
print(f"   Status: {r2.status_code}")

timetable = r2.json().get("timetable", [])
slots = [sl for sl in timetable if sl.get("availability") not in ("SOLD_OUT", "NOT_ALLOWED")]
print(f"   Available: {len(slots)}")

if not slots:
    print("❌ No slots")
    sys.exit(1)

for sl in slots[:5]:
    p = sl.get("price", {})
    total = p.get("total", "?") if isinstance(p, dict) else "?"
    print(f"   • {sl.get('time')} | id={sl.get('id')} | €{total}")

target = slots[0]
slot_id = str(target.get("id"))
slot_time = target.get("time", "17:00")

# Step 3: Recap - EXACT format from lightning_snipe.py
print(f"\n3️⃣  RECAP (slot_id={slot_id})...")

s.headers.update(HC)
recap_body = {
    "visitId": slot_id,
    "visitTypeId": int(tid),
    "visitorNum": VISITORS,
    "lang": "it",
    "tickets": [
        {"id": 60, "name": "Biglietto Intero", "price": 20, "quantity": str(ADULTS)},
        {"id": 61, "name": "Biglietto Ridotto", "price": 10, "quantity": str(CHILDREN)},
    ],
    "additionalCosts": {
        "service-0": {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": VISITORS}
    },
    "services": [
        {"id": 58, "name": "Diritti di Prevendita", "price": 5, "quantity": VISITORS}
    ]
}

print(f"   Body: {json.dumps(recap_body)}")
r3 = s.post(f"{BASE}/api/visit/recap", json=recap_body, timeout=15)
print(f"   Status: {r3.status_code}")

if r3.status_code == 200:
    recap_data = r3.json()
    recap_id = recap_data.get("recapId") or recap_data.get("id", "")
    total_price = recap_data.get("total", "")
    print(f"\n   🔒 SLOT LOCKED!")
    print(f"   recapId: {recap_id}")
    print(f"   Total: €{total_price}")

    # Save
    result = {
        "date": TARGET_DATE, "time": slot_time, "slot_id": slot_id,
        "recap_id": recap_id, "total_price": str(total_price),
        "visitors": VISITORS, "success": True,
    }
    with open("/root/vatican-bot/snipe_result.json", "w") as f:
        json.dump(result, f, indent=2)

    print("\n" + "=" * 60)
    print("🎉 LIVE SNIPE SUCCESSFUL! Slot locked for ~55min")
    print(f"   Date: {TARGET_DATE} at {slot_time}")
    print(f"   Recap ID: {recap_id}")
    print(f"   Price: €{total_price}")
    print("=" * 60)
else:
    print(f"\n❌ RECAP FAILED: {r3.status_code}")
    print(f"   {r3.text[:500]}")
