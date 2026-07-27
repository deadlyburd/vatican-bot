#!/usr/bin/env python3
"""
SMART BOOKER — reads Master sheet, groups by date+time, books with correct names & ticket types.
"""
import asyncio, time, json, random, os
from datetime import date as dt, timedelta
from collections import defaultdict
from slot_finder import SlotFinder
from book_from_recording import book  # nodriver booker

VATICAN = "https://tickets.museivaticani.va"
PROXY_USER = os.getenv("OXYLABS_USERNAME", "")
PROXY_PASS = os.getenv("OXYLABS_PASSWORD", "")
PROXY_HOST = os.getenv("OXYLABS_HOST", "isp.oxylabs.io")
PROXY_PORTS = [8001,8002,8003,8004,8005,8006,8007,8008,8009,8010,8011,8012,8013]

def log(msg): print(f"[{dt.today():%m-%d %H:%M}] {msg}")

def get_proxy():
    port = random.choice(PROXY_PORTS)
    return f"{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{port}"

def read_master_bookings():
    """Read Master sheet and group bookings by date+time."""
    from crm_intelligence.parsers.sheet_parser import SheetParser
    from customer_care.config.bot_config import config

    parser = SheetParser(sheet_id=config.crm.sheet_id, credentials_file=config.crm.service_account_file)
    parser.connect()
    master = parser._sheet.worksheet("Master")
    data = master.get_all_values()

    if len(data) < 2:
        log("Master sheet is empty!")
        return []

    headers = data[0]
    # Column indices: A=0(Date), B=1(Time), C=2(Product), D=3(Pax), E=4(First), F=5(Last),
    # G=6(BookingID), H=7(Status), I=8(Conf), J=9(Payment), K=10(Missing), L=11(Type), M=12(Platform)

    today = dt.today()
    groups = defaultdict(lambda: {"participants": [], "pax": 0, "adults": 0, "children": 0, "booking_ids": set()})

    for row in data[1:]:
        if len(row) < 12: continue
        date_str = (row[0] or "").strip()
        time_str = (row[1] or "").strip()
        fname = (row[4] or "").strip()
        lname = (row[5] or "").strip()
        pax_type = (row[11] or "Adult").strip() if len(row) > 11 else "Adult"
        status = (row[7] or "").strip() if len(row) > 7 else ""
        bid = (row[6] or "").strip() if len(row) > 6 else ""

        # Skip cancelled, skip if no name, skip past dates
        if "CANCEL" in status.upper(): continue
        if not fname or not lname: continue

        try:
            d = dt.fromisoformat(date_str)
            if d < today: continue
        except: continue

        # Skip if already has payment link
        payment = (row[9] or "").strip() if len(row) > 9 else ""
        if payment and "epay" in payment.lower(): continue

        key = f"{date_str}|{time_str}"
        groups[key]["date"] = date_str
        groups[key]["time"] = time_str
        groups[key]["participants"].append({"first": fname, "last": lname, "type": pax_type})
        groups[key]["pax"] += 1
        if "child" in pax_type.lower() or "student" in pax_type.lower() or "infant" in pax_type.lower():
            groups[key]["children"] += 1
        else:
            groups[key]["adults"] += 1
        if bid: groups[key]["booking_ids"].add(bid)

    # Sort by date
    result = []
    for key, g in sorted(groups.items(), key=lambda x: x[1].get("date", "")):
        result.append({
            "date": g["date"],
            "time": g["time"],
            "visitors": g["pax"],
            "adults": g["adults"],
            "children": g["children"],
            "participants": g["participants"],
            "booking_ids": list(g["booking_ids"]),
        })
    return result

def check_availability(date_str, visitors):
    """Check if there are enough slots for this group."""
    finder = SlotFinder()
    slots = finder.find_slots(date_str, visitors, use_cache=False)
    if not slots:
        return None
    return slots[0]  # Best slot

async def smart_book(group):
    """Book a group with correct participant names and ticket types."""
    log(f"Booking: {group['date']} {group['time']} — {group['visitors']}v ({group['adults']}A + {group['children']}C)")

    # Check availability for this group size
    slot_info = check_availability(group["date"], group["visitors"])
    if not slot_info:
        log(f"  ❌ No slots for {group['date']} ({group['visitors']}v)")
        return {"success": False, "error": "no slots"}

    log(f"  Slot found: {slot_info.slot_time} ({len(slot_info)} available)")

    # Prepare slot for booker
    slot = {
        "date": slot_info.date,
        "slot_time": slot_info.slot_time,
        "slot_id": slot_info.slot_id,
        "ticket_id": slot_info.ticket_id,
        "visitors": group["visitors"],
    }

    # Build participant list with correct names
    participants = []
    for p in group["participants"]:
        participants.append({
            "first_name": p["first"],
            "last_name": p["last"],
            "type": p["type"],
        })

    # Set CRM data in the booker
    import book_from_recording as br
    first_p = group["participants"][0]
    buyer = {
        "surname": first_p["last"],
        "name": first_p["first"],
        "email": "booking@hydrabot.it",
        "phone": "your-phone-number",
        "city": "Roma",
    }
    # Format participants for booker
    participants = [
        {"first_name": p["first"], "last_name": p["last"], "type": p.get("type", "Adult")}
        for p in group["participants"]
    ]
    br.set_crm_data(buyer=buyer, participants=participants)

    result = await book(slot)
    return result

async def run_smart_booking():
    """Main: read Master → group by date → book each group."""
    groups = read_master_bookings()
    if not groups:
        log("No upcoming bookings found in Master.")
        return

    log(f"📋 Found {len(groups)} booking groups (grouped by date+time):")
    for g in groups[:10]:
        names = ", ".join(f"{p['first']} {p['last']} ({p['type']})" for p in g["participants"][:3])
        log(f"  {g['date']} {g['time']} — {g['visitors']}v ({g['adults']}A + {g['children']}C): {names}")

    # Book each group
    results = []
    for g in groups[:5]:  # Limit to 5 groups per run
        result = await smart_book(g)
        results.append({"group": g, "result": result})
        if result.get("success"):
            log(f"  ✅ BOOKED: {result.get('epay_url', '')[:80]}")
        else:
            log(f"  ❌ Failed: {result.get('error', 'unknown')}")
        time.sleep(5)  # Cool down between bookings

    return results

if __name__ == "__main__":
    asyncio.run(run_smart_booking())
