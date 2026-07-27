#!/usr/bin/env python3
"""Rebuild Master sheet with passenger-level data, colors, grouping."""
import time, re
from datetime import date as dt, timedelta
from collections import defaultdict
from crm_intelligence.parsers.sheet_parser import SheetParser
from customer_care.config.bot_config import config

parser = SheetParser(sheet_id=config.crm.sheet_id, credentials_file=config.crm.service_account_file)
parser.connect()
sheet = parser._sheet

# Read ALL data in one shot
act_data = sheet.worksheet("Activity_Lines").get_all_values()
pass_data = sheet.worksheet("Passengers").get_all_values()

act_headers = act_data[0]
act_rows = act_data[1:]
pass_headers = pass_data[0]
pass_rows = pass_data[1:]

# Index passenger data by booking ID
bid_col_p = pass_headers.index("bookingId") if "bookingId" in pass_headers else 0
fn_col = pass_headers.index("firstName") if "firstName" in pass_headers else 1
ln_col = pass_headers.index("lastName") if "lastName" in pass_headers else 2

# Find age/birthdate column
age_col = None
for i, h in enumerate(pass_headers):
    if any(w in str(h).lower() for w in ["age", "birth", "dateofbirth", "type", "adult"]):
        age_col = i; break

pax_map = defaultdict(list)
age_map = {}  # key: bid|first_last → age string
for pr in pass_rows:
    if len(pr) > max(bid_col_p, fn_col, ln_col):
        bid = str(pr[bid_col_p]).strip()
        name = (str(pr[fn_col]) + " " + str(pr[ln_col])).strip()
        if bid and name:
            pax_map[bid].append(name)
            age_v = str(pr[age_col] or "").strip() if age_col and len(pr) > age_col else ""
            age_map[bid + "|" + str(pr[fn_col]).strip().lower() + "_" + str(pr[ln_col]).strip().lower()] = age_v

# Index activity columns
acols = {h.lower(): i for i, h in enumerate(act_headers)}
bid_col = acols.get("bookingid", 0)
date_col = acols.get("activitydate", 1)
prod_col = acols.get("producttitle", 2)
time_col = acols.get("starttime", 3)
pax_col = acols.get("totalparticipants", 4)
name_col = acols.get("customername", 5)
status_col = acols.get("status", 6)
conf_col = acols.get("confirmationcode", acols.get("productconfirmationcode", 7))

# Filter recent + upcoming
today = dt.today()
cutoff = today - timedelta(days=90)

def parse_date(d):
    try: return dt.fromisoformat(str(d).strip())
    except: return None

filtered = []
for r in act_rows:
    if len(r) <= date_col: continue
    d = parse_date(str(r[date_col]))
    if d and d >= cutoff:
        filtered.append(r)

# Sort: newest first, then by Booking ID to group
filtered.sort(key=lambda r: str(r[bid_col] if len(r) > bid_col else ""))
filtered.sort(key=lambda r: parse_date(str(r[date_col] if len(r) > date_col else "")) or dt(2000,1,1), reverse=True)

print(f"Filtered: {len(filtered)} activities, {len(pax_map)} with passenger data")

# Build rows
headers = [["Date", "Time", "Product", "Pax", "First Name", "Last Name",
            "Booking ID", "Status", "Confirmation", "Payment Link", "Missing", "Type", "Platform"]]
rows = headers.copy()

for r in filtered:
    if len(r) <= bid_col: continue
    bid = str(r[bid_col]).strip()
    if not bid: continue

    pax = int(str(r[pax_col] or 1)) if len(r) > pax_col else 1
    main_name = str(r[name_col] or "").strip() if len(r) > name_col else ""
    status = str(r[status_col] or "").strip() if len(r) > status_col else ""
    conf = str(r[conf_col] or "").strip() if len(r) > conf_col else ""
    datev = str(r[date_col] or "").strip() if len(r) > date_col else ""
    timev = str(r[time_col] or "").strip() if len(r) > time_col else ""
    prod = str(r[prod_col] or "")[:80] if len(r) > prod_col else ""

    missing = []
    if not main_name: missing.append("Name")
    missing_str = ", ".join(missing) if missing else "OK"

    pax_names = pax_map.get(bid, [])
    if not pax_names:
        parts = main_name.split()
        pax_names = [main_name] if main_name else ["Unknown"]

    for pi, pname in enumerate(pax_names[:max(pax, 1)]):
        parts = pname.strip().split()
        fname = parts[0] if parts else ""
        lname = " ".join(parts[1:]) if len(parts) > 1 else ""
        # Determine Type based on age data
        pax_type = "Adult"
        # Check passenger age from age_map
        age_key = bid + "|" + fname.lower() + "_" + lname.lower()
        age_info = age_map.get(age_key, "")
        if age_info:
            try:
                age = int(re.sub(r"[^0-9]", "", age_info))
                if age < 7: pax_type = "Infant (free)"
                elif age < 18: pax_type = "Child (reduced)"
                elif age <= 25: pax_type = "Student (reduced)"
            except: pass

        rows.append([datev, timev, prod, str(pax), fname, lname, bid, status, conf, "", missing_str, pax_type, "Bokun/Viator"])

print(f"Building {len(rows)-1} rows...")

# Delete old + create new
for name in ["Master"]:
    try: sheet.del_worksheet(sheet.worksheet(name)); time.sleep(2)
    except: pass

master = sheet.add_worksheet("Master", len(rows) + 50, 13)
time.sleep(2)
master.update(rows, "A1", value_input_option="RAW")
print(f"Written {len(rows)} rows")
time.sleep(3)

# Format headers
master.format("A1:M1", {
    "backgroundColor": {"red": 0.85, "green": 0.95, "blue": 0.85},
    "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}, "bold": True, "fontSize": 11},
})
master.freeze(1, 0)

# Conditional formatting: Green=Confirmed, Red=Cancelled, Yellow=Missing
sid = master._properties["sheetId"]
master.spreadsheet.batch_update({"requests": [
    {"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": sid}],
        "booleanRule": {
            "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "CONFIRMED"}]},
            "format": {"backgroundColor": {"red": 0.82, "green": 0.98, "blue": 0.82}}
        }}, "index": 0}},
    {"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": sid}],
        "booleanRule": {
            "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "CANCELLED"}]},
            "format": {"backgroundColor": {"red": 0.98, "green": 0.78, "blue": 0.78}}
        }}, "index": 1}},
    {"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": sid}],
        "booleanRule": {
            "condition": {"type": "TEXT_NOT_CONTAINS", "values": [{"userEnteredValue": "OK"}]},
            "format": {"backgroundColor": {"red": 1.0, "green": 0.94, "blue": 0.7}}
        }}, "index": 2}},
]})

print("🟢 Green=Confirmed | 🔴 Red=Cancelled | 🟡 Yellow=Missing")
print("✅ Done! Each passenger on their own row, same Booking ID grouped.")
