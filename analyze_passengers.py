#!/usr/bin/env python3
"""Analyze Passengers sheet for gaps + rebuild Master with phone + all rows."""
import time, re
from datetime import date as dt, timedelta
from collections import defaultdict
from crm_intelligence.parsers.sheet_parser import SheetParser
from customer_care.config.bot_config import config

p = SheetParser(sheet_id=config.crm.sheet_id, credentials_file=config.crm.service_account_file)
p.connect()
sheet = p._sheet

# ── ANALYZE PASSENGERS ──
pass_ws = sheet.worksheet("Passengers")
pass_data = pass_ws.get_all_values()
pass_headers = pass_data[0]
pass_rows = pass_data[1:]
total = len(pass_rows)

# Find column indices
bid_c = pass_headers.index("bookingId") if "bookingId" in pass_headers else 0
fn_c = pass_headers.index("firstName") if "firstName" in pass_headers else 1
ln_c = pass_headers.index("lastName") if "lastName" in pass_headers else 2
# Look for phone/email columns
phone_c = None; email_c = None
for i, h in enumerate(pass_headers):
    hl = str(h).lower()
    if "phone" in hl or "mobile" in hl or "telefono" in hl: phone_c = i
    if "email" in hl or "mail" in hl: email_c = i

# Count gaps
no_name = 0; no_phone = 0; no_email = 0; empty_rows = 0
bids_no_name = defaultdict(int)
all_rows_for_master = []

for r in pass_rows:
    if not any(c.strip() for c in r):
        empty_rows += 1
        continue

    first = str(r[fn_c]).strip() if len(r) > fn_c else ""
    last = str(r[ln_c]).strip() if len(r) > ln_c else ""
    bid = str(r[bid_c]).strip() if len(r) > bid_c else ""
    phone = str(r[phone_c]).strip() if phone_c and len(r) > phone_c else ""
    email = str(r[email_c]).strip() if email_c and len(r) > email_c else ""

    if not first and not last: no_name += 1
    if not phone: no_phone += 1
    if not email: no_email += 1
    if bid and not first and not last: bids_no_name[bid] += 1

    all_rows_for_master.append({
        "bid": bid, "first": first, "last": last,
        "phone": phone, "email": email,
    })

print(f"📊 Passengers Analysis:")
print(f"  Total: {total}")
print(f"  Empty rows: {empty_rows}")
print(f"  Without name: {no_name} ({no_name*100//total if total else 0}%)")
print(f"  Without phone: {no_phone} ({no_phone*100//total if total else 0}%)")
print(f"  Without email: {no_email} ({no_email*100//total if total else 0}%)")
print(f"  Booking IDs without names: {len(bids_no_name)}")
for bid, count in list(bids_no_name.items())[:5]:
    print(f"    {bid}: {count} passengers unnamed")

# ── REBUILD MASTER WITH PHONE + ALL ROWS ──
print(f"\n📊 Rebuilding Master with phone numbers + all rows...")

act_ws = sheet.worksheet("Activity_Lines")
act_data = act_ws.get_all_values()
act_headers = act_data[0]
acols = {h.lower(): i for i, h in enumerate(act_headers)}

today = dt.today()
cutoff = today - timedelta(days=90)

def parse_date(d):
    try: return dt.fromisoformat(str(d).strip())
    except: return None

filtered = []
for r in act_data[1:]:
    d = parse_date(str(r[acols.get("activitydate", 1)] or "")) if len(r) > acols.get("activitydate", 1) else None
    if d and d >= cutoff:
        filtered.append(r)

# Sort newest first, then by Booking ID
filtered.sort(key=lambda r: str(r[acols.get("bookingid", 0)] if len(r) > acols.get("bookingid", 0) else ""))
filtered.sort(key=lambda r: parse_date(str(r[acols.get("activitydate", 1)] or "") if len(r) > 1 else "") or dt(2000,1,1), reverse=True)

# Build passenger lookup
pax_lookup = {}
for pr in all_rows_for_master:
    bid = pr["bid"]
    if bid not in pax_lookup: pax_lookup[bid] = []
    pax_lookup[bid].append(pr)

# Age lookup from Passengers
age_col = None
for i, h in enumerate(pass_headers):
    if any(w in str(h).lower() for w in ["age", "birth", "dateofbirth"]):
        age_col = i; break
age_map = {}
if age_col:
    for pr in pass_rows:
        if len(pr) > max(bid_c, fn_c, ln_c, age_col):
            bid = str(pr[bid_c]).strip()
            name = (str(pr[fn_c]) + "_" + str(pr[ln_c])).strip().lower()
            age_v = str(pr[age_col] or "").strip()
            age_map[bid + "|" + name] = age_v

# Also read phone from Bookings sheet
booking_phone = {}
try:
    book_ws = sheet.worksheet("Bookings")
    book_data = book_ws.get_all_values()
    book_headers = book_data[0]
    book_bid_c = book_headers.index("bookingId") if "bookingId" in book_headers else 0
    book_ph_c = None
    for i, h in enumerate(book_headers):
        if "customerphone" in str(h).lower() or "phone" in str(h).lower():
            book_ph_c = i; break
    if book_ph_c is not None:
        for br in book_data[1:]:
            if len(br) > max(book_bid_c, book_ph_c):
                booking_phone[str(br[book_bid_c]).strip()] = str(br[book_ph_c]).strip()
    print(f"Phone from Bookings: {len(booking_phone)} records")
except Exception as e:
    print(f"Bookings phone error: {e}")

# Build Master rows
headers = [["Date", "Time", "Product", "Pax", "First Name", "Last Name",
            "Booking ID", "Status", "Confirmation", "Phone", "Payment Link",
            "Missing", "Type"]]

for r in filtered:
    bid_idx = acols.get("bookingid", 0)
    if len(r) <= bid_idx: continue
    bid = str(r[bid_idx]).strip()
    if not bid: continue

    pax = int(str(r[acols.get("totalparticipants", 4)] or 1)) if len(r) > 4 else 1
    main_name = str(r[acols.get("customername", 5)] or "").strip() if len(r) > 5 else ""
    status = str(r[acols.get("status", 6)] or "").strip() if len(r) > 6 else ""
    conf = str(r[acols.get("confirmationcode", acols.get("productconfirmationcode", 7))] or "").strip() if len(r) > 7 else ""
    datev = str(r[acols.get("activitydate", 1)] or "").strip() if len(r) > 1 else ""
    timev = str(r[acols.get("starttime", 2)] or "").strip() if len(r) > 2 else ""
    prod = str(r[acols.get("producttitle", 3)] or "")[:80] if len(r) > 3 else ""

    # Get passenger data (including phone/email from Passengers)
    pax_data = pax_lookup.get(bid, [])
    if not pax_data:
        parts = main_name.split()
        pax_data = [{"first": parts[0] if parts else "Unknown", "last": " ".join(parts[1:]) if len(parts)>1 else "",
                     "phone": "", "email": ""}]

    for pi, pd in enumerate(pax_data[:max(pax, 1)]):
        fname = pd.get("first", "")
        lname = pd.get("last", "")
        phone = pd.get("phone", "")

        # Missing check
        missing = []
        if not fname and not lname: missing.append("Name")
        if not phone: missing.append("Phone")
        if not pd.get("email"): missing.append("Email")
        missing_str = ", ".join(missing) if missing else "OK"

        # Type (Adult/Child)
        age_key = bid + "|" + fname.lower() + "_" + lname.lower()
        age_info = age_map.get(age_key, "")
        pax_type = "Adult"
        if age_info:
            try:
                age = int(re.sub(r"[^0-9]", "", age_info))
                if age < 7: pax_type = "Infant (free)"
                elif age < 18: pax_type = "Child (reduced)"
                elif age <= 25: pax_type = "Student (reduced)"
            except: pass

        # Get phone from Bookings sheet too
        bk_phone = booking_phone.get(bid, "")
        final_phone = phone or bk_phone or ""

        rows.append([datev, timev, prod, str(pax), fname, lname, bid, status, conf, final_phone, "", missing_str, pax_type])

print(f"Building {len(rows)-1} rows with phone numbers...")

# Delete old + create new
for name in ["Master"]:
    try: sheet.del_worksheet(sheet.worksheet(name)); time.sleep(2)
    except: pass

master = sheet.add_worksheet("Master", len(rows) + 100, 13)
time.sleep(2)
master.update(rows, "A1", value_input_option="RAW")
print(f"Written {len(rows)} rows")

# Format headers
time.sleep(3)
master.format("A1:M1", {
    "backgroundColor": {"red": 0.85, "green": 0.95, "blue": 0.85},
    "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}, "bold": True},
})
master.freeze(1, 0)

# Conditional formatting
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
]})

print(f"\n✅ Master rebuilt!")
print(f"Rows: {len(rows)-1} | Includes ALL passengers (even with blanks)")
print(f"Phone column added | Missing column shows gaps")
print(f"🔗 https://docs.google.com/spreadsheets/d/{config.crm.sheet_id}/edit")
