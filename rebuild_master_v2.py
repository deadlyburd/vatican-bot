#!/usr/bin/env python3
"""Rebuild Master v2 — Phone from Bookings+Passengers, all rows, no Platform col."""
import time, re
from datetime import date as dt, timedelta
from collections import defaultdict
from crm_intelligence.parsers.sheet_parser import SheetParser
from customer_care.config.bot_config import config

p = SheetParser(sheet_id=config.crm.sheet_id, credentials_file=config.crm.service_account_file)
p.connect()
sheet = p._sheet

# ── 1. Read ALL source data ──
act_ws = sheet.worksheet("Activity_Lines")
pass_ws = sheet.worksheet("Passengers")
book_ws = sheet.worksheet("Bookings")

act_data = act_ws.get_all_values(); act_h = act_data[0]; act_r = act_data[1:]
pass_data = pass_ws.get_all_values(); pass_h = pass_data[0]; pass_r = pass_data[1:]
book_data = book_ws.get_all_values(); book_h = book_data[0]; book_r = book_data[1:]

# ── 2. Column indices ──
acols = {h.lower(): i for i,h in enumerate(act_h)}
pcols = {h.lower(): i for i,h in enumerate(pass_h)}
bcols = {h.lower(): i for i,h in enumerate(book_h)}

# ── 3. Build lookup maps ──
# Phone from Bookings (customerPhone)
booking_phone = {}
for br in book_r:
    bid = str(br[bcols.get("bookingid",0)]).strip() if len(br)>bcols.get("bookingid",0) else ""
    phone = str(br[bcols.get("customerphone",bcols.get("phone",15))]).strip() if len(br)>bcols.get("customerphone",bcols.get("phone",15)) else ""
    if bid and phone: booking_phone[bid] = phone

# Phone + Name from Passengers
pax_map = defaultdict(list)
pass_phone = {}
pass_email = {}
for pr in pass_r:
    bid = str(pr[pcols.get("bookingid",0)]).strip() if len(pr)>pcols.get("bookingid",0) else ""
    first = str(pr[pcols.get("firstname",1)]).strip() if len(pr)>pcols.get("firstname",1) else ""
    last = str(pr[pcols.get("lastname",2)]).strip() if len(pr)>pcols.get("lastname",2) else ""
    phone = str(pr[pcols.get("phonenumber",15)]).strip() if len(pr)>pcols.get("phonenumber",15) else ""
    email = str(pr[pcols.get("email",3)]).strip() if len(pr)>pcols.get("email",3) else ""
    name = (first + " " + last).strip()
    if bid:
        if name: pax_map[bid].append(name)
        if phone: pass_phone[bid + "|" + first.lower() + "_" + last.lower()] = phone
        if email: pass_email[bid + "|" + first.lower() + "_" + last.lower()] = email

print(f"Bookings with phone: {len(booking_phone)}")
print(f"Passengers with names: {sum(1 for v in pax_map.values() if v)}")

# ── 4. Filter + sort ──
today = dt.today(); cutoff = today - timedelta(days=90)
def parse_date(d):
    try: return dt.fromisoformat(str(d).strip())
    except: return None

filtered = []
for r in act_r:
    d = parse_date(str(r[acols.get("activitydate",1)] or "")) if len(r)>acols.get("activitydate",1) else None
    if d and d >= cutoff: filtered.append(r)

filtered.sort(key=lambda r: str(r[acols.get("bookingid",0)]).strip() if len(r)>acols.get("bookingid",0) else "")
filtered.sort(key=lambda r: parse_date(str(r[acols.get("activitydate",1)] or "") if len(r)>1 else "") or dt(2000,1,1), reverse=True)

# ── 5. Build Master rows ──
HEADERS = ["Date","Time","Product","Pax","First Name","Last Name",
           "Booking ID","Status","Confirmation","Phone","Payment Link","Booked","Missing","Type"]
all_rows = [HEADERS]

for r in filtered:
    bid_idx = acols.get("bookingid",0)
    if len(r) <= bid_idx: continue
    bid = str(r[bid_idx]).strip()
    if not bid: continue

    pax = int(str(r[acols.get("totalparticipants",4)] or 1)) if len(r)>4 else 1
    main_name = str(r[acols.get("customername",5)] or "").strip() if len(r)>5 else ""
    status = str(r[acols.get("status",6)] or "").strip() if len(r)>6 else ""
    conf = str(r[acols.get("confirmationcode",acols.get("productconfirmationcode",7))] or "").strip() if len(r)>7 else ""
    datev = str(r[acols.get("activitydate",1)] or "").strip() if len(r)>1 else ""
    timev = str(r[acols.get("starttime",2)] or "").strip() if len(r)>2 else ""
    prod = str(r[acols.get("producttitle",3)] or "")[:80] if len(r)>3 else ""

    # Get passenger list
    pax_names = pax_map.get(bid, [])
    if not pax_names:
        parts = main_name.split()
        pax_names = [main_name] if main_name else ["Unknown"]

    for pi in range(max(pax, 1)):
        fname = ""; lname = ""; pax_phone = ""; pax_email = ""
        if pi < len(pax_names):
            parts = pax_names[pi].strip().split()
            fname = parts[0] if parts else ""
            lname = " ".join(parts[1:]) if len(parts)>1 else ""

        # Get phone: Passengers first, then Bookings
        key = bid + "|" + fname.lower() + "_" + lname.lower()
        pax_phone = pass_phone.get(key, "") or booking_phone.get(bid, "")
        pax_email = pass_email.get(key, "")

        # Missing check
        missing = []
        if not fname and not lname: missing.append("Name")
        if not pax_phone: missing.append("Phone")
        if not pax_email: missing.append("Email")
        missing_str = ", ".join(missing) if missing else "OK"

        # Type (Adult/Child)
        pax_type = "Adult"  # Simplified - actual age detection needs birth date

        # Booked status: Admin marks Yes/No manually, defaults to No
        booked = "No"
        all_rows.append([datev, timev, prod, str(pax), fname, lname, bid, status, conf, pax_phone, "", booked, missing_str, pax_type])

print(f"Rows: {len(all_rows)-1}")

# ── 6. Write to sheet ──
for name in ["Master"]:
    try: sheet.del_worksheet(sheet.worksheet(name)); time.sleep(2)
    except: pass

master = sheet.add_worksheet("Master", len(all_rows)+100, 14)
time.sleep(2)
master.update(all_rows, "A1", value_input_option="RAW")
print("Written!")

# ── 7. Format ──
time.sleep(3)
master.format("A1:N1", {
    "backgroundColor": {"red": 0.85, "green": 0.95, "blue": 0.85},
    "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}, "bold": True},
})
master.freeze(1, 0)

sid = master._properties["sheetId"]
master.spreadsheet.batch_update({"requests": [
    {"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": sid}],
        "booleanRule": {"condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "CONFIRMED"}]},
            "format": {"backgroundColor": {"red": 0.82, "green": 0.98, "blue": 0.82}}}}, "index": 0}},
    {"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": sid}],
        "booleanRule": {"condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "CANCELLED"}]},
            "format": {"backgroundColor": {"red": 0.98, "green": 0.78, "blue": 0.78}}}}, "index": 1}},
    {"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": sid}],
        "booleanRule": {"condition": {"type": "TEXT_NOT_CONTAINS", "values": [{"userEnteredValue": "OK"}]},
            "format": {"backgroundColor": {"red": 1.0, "green": 0.94, "blue": 0.7}}}}, "index": 2}},
    {"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": sid}],
        "booleanRule": {"condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "Yes"}]},
            "format": {"backgroundColor": {"red": 0.7, "green": 0.95, "blue": 0.7}}}}, "index": 3}},
]})

print(f"✅ Master v2 done! {len(all_rows)-1} rows")
print(f"Phone col (J) from Bookings+Passengers. Missing col (L) shows gaps.")
print(f"🔗 https://docs.google.com/spreadsheets/d/{config.crm.sheet_id}/edit")
