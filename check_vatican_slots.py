#!/usr/bin/env python3
"""Check Vatican real slots using ACTUAL working parameters from lightning_snipe.py"""
import requests
import json
from datetime import date, timedelta

BASE = "https://tickets.museivaticani.va"
H_XHR = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE}/",
    "Origin": BASE,
}

session = requests.Session()
session.headers.update(H_XHR)

today = date.today()
visitors = 4
target_date = None
target_slot = None

# Check next 30 days for slots
for days_ahead in range(0, 30):
    check_date = today + timedelta(days=days_ahead)
    date_str = check_date.strftime("%d/%m/%Y")

    if days_ahead == 0:
        print(f"=== CHECKING VATICAN SLOTS (next 30 days) ===\n")

    # Step 1: Search
    r = session.get(f"{BASE}/api/search/resultPerTag", params={
        "lang": "it", "visitorNum": str(visitors), "visitDate": date_str,
        "area": "1", "who": "", "page": "0", "tag": "MV-Biglietti"
    }, timeout=10)

    if r.status_code != 200:
        if days_ahead == 0:
            print(f"Search API: {r.status_code}")
        continue

    data = r.json()
    visits = data.get("visits", [])

    # Find the Vatican Museums entry
    tid = None
    for v in visits:
        name = v.get("name", "").lower()
        if "musei vaticani" in name and "ingresso" in name:
            tid = v.get("id")
            break

    if not tid:
        if days_ahead == 0:
            print("Could not find Vatican Museums in visits")
        continue

    # Step 2: Timeavail
    r2 = session.get(f"{BASE}/api/visit/timeavail", params={
        "lang": "it", "visitLang": "", "visitTypeId": str(tid),
        "visitorNum": str(visitors), "visitDate": date_str,
    }, timeout=10)

    if r2.status_code != 200:
        continue

    timetable = r2.json().get("timetable", [])
    for sl in timetable:
        avail = sl.get("availability", "")
        if avail not in ("SOLD_OUT", "NOT_ALLOWED"):
            slot_id = sl.get("id", "")
            slot_time = sl.get("time", "")
            price_info = sl.get("price", {})
            if isinstance(price_info, dict):
                total = price_info.get("total", "")
            else:
                total = str(price_info)

            if not target_slot:
                target_date = date_str
                target_slot = {"slot_id": str(slot_id), "time": slot_time, "price": str(total), "tid": str(tid)}
                print(f"🎯 {date_str} {slot_time} | slot={slot_id} | €{total} | tid={tid}")

            # Just show first 12 available
            if days_ahead < 12 or avail not in ("SOLD_OUT", "NOT_ALLOWED"):
                pass  # continue scanning silently for best date

if target_slot:
    print(f"\n✅ FOUND: {target_date} at {target_slot['time']} | slot_id={target_slot['slot_id']} | €{target_slot['price']}")
    print(f"   ticket_type_id={target_slot['tid']} | {visitors} visitors")

    # Save for snipe
    with open("/root/vatican-bot/target_slot.json", "w") as f:
        json.dump({
            "date": target_date,
            "time": target_slot["time"],
            "slot_id": target_slot["slot_id"],
            "ticket_type_id": target_slot["tid"],
            "visitors": visitors,
        }, f)
    print("   Saved to /root/vatican-bot/target_slot.json")
else:
    print("\n⚠️ No available slots found in the next 30 days.")
