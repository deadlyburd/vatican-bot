#!/usr/bin/env python3
"""Find first available Vatican slot in August+ for extension test."""
import requests, json
from datetime import date, timedelta

BASE = "https://tickets.museivaticani.va"
H = {
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE}/",
    "Origin": BASE,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

s = requests.Session()
s.headers.update(H)

# Check August 2026 dates
dates_to_try = [
    "03/08/2026", "05/08/2026", "06/08/2026", "10/08/2026",
    "12/08/2026", "17/08/2026", "19/08/2026", "24/08/2026",
    "26/08/2026", "31/08/2026", "02/09/2026", "07/09/2026",
]

print("Scanning August-September for available Vatican slots:\n")

for ds in dates_to_try:
    r = s.get(f"{BASE}/api/search/resultPerTag", params={
        "lang": "it", "visitorNum": "2", "visitDate": ds,
        "area": "1", "who": "", "page": "0", "tag": "MV-Biglietti"
    }, timeout=10)

    if r.status_code != 200:
        continue

    tid = None
    for v in r.json().get("visits", []):
        n = v.get("name", "").lower()
        if "musei vaticani" in n and "ingresso" in n:
            avail = v.get("availability", "")
            tid = v.get("id")
            if avail not in ("SOLD_OUT", "NOT_ALLOWED"):
                # Found a date with availability - check time slots
                r2 = s.get(f"{BASE}/api/visit/timeavail", params={
                    "lang": "it", "visitTypeId": str(tid),
                    "visitorNum": "2", "visitDate": ds,
                }, timeout=10)

                if r2.status_code == 200:
                    data = r2.json()
                    timetable = data.get("timetable", []) if isinstance(data, dict) else []
                    open_slots = [sl for sl in timetable if sl.get("availability") not in ("SOLD_OUT", "NOT_ALLOWED")]

                    if open_slots:
                        sl = open_slots[0]
                        print(f"🎯 {ds} | {sl.get('time')} | slot_id={sl.get('id')} | tid={tid} | {len(open_slots)} slots total")

                        # Save for extension
                        result = {
                            "date": ds, "time": sl.get("time"),
                            "slot_id": str(sl.get("id")),
                            "ticket_type_id": str(tid),
                            "visitors": 2,
                            "total_slots": len(open_slots),
                        }
                        with open("/root/vatican-bot/extension_target.json", "w") as f:
                            json.dump(result, f, indent=2)
                        print(json.dumps(result, indent=2))
                        exit(0)
                    else:
                        print(f"  {ds} → AVAILABLE at search but no time slots")
                else:
                    print(f"  {ds} → timeavail returned {r2.status_code}")
            else:
                print(f"  {ds} → {avail}")
            break

print("\nNo August+ slots with time slots found. July 28 is the earliest.")
