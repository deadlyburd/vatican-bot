#!/usr/bin/env python3
"""Check Google Sheets connection + analyze data."""
import os, json
from datetime import date, datetime, timedelta

cred_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "/app/google_credentials.json")
sheet_id = os.getenv("GOOGLE_SHEET_ID", "1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg")

print(f"Sheet ID: {sheet_id}")
print(f"Credentials: {cred_file} (exists: {os.path.exists(cred_file)})")

from crm_intelligence.parsers.sheet_parser import SheetParser
from customer_care.config.bot_config import config

parser = SheetParser(sheet_id=sheet_id, credentials_file=cred_file)
parser.connect()
sheet = parser._sheet

print(f"\n✅ Connected: {sheet.title}")
print(f"\n📊 WORKSHEETS:")
for ws in sheet.worksheets():
    print(f"  • {ws.title} — {ws.row_count} rows x {ws.col_count} cols")

# Analyze Activity_Lines
activity_ws = None
for ws in sheet.worksheets():
    if "activity" in ws.title.lower():
        activity_ws = ws
        break

if activity_ws:
    headers = activity_ws.row_values(1)
    print(f"\n📋 Activity_Lines — {len(headers)} columns")
    print(f"  Headers: {headers[:20]}")

    records = activity_ws.get_all_records()
    vatican = colosseum = upcoming = urgent = 0
    dates = set()
    today = date.today()

    for r in records:
        title = str(r.get("productTitle", "")).lower()
        if any(w in title for w in ["vatican","sistine","vaticani","musei"]):
            vatican += 1
        if any(w in title for w in ["colosseum","colosseo"]):
            colosseum += 1
        d = str(r.get("activityDate", ""))
        if d:
            dates.add(d)
            try:
                dt = datetime.strptime(d, "%Y-%m-%d").date()
                if dt >= today:
                    upcoming += 1
                    if dt <= today + timedelta(days=3):
                        urgent += 1
            except: pass

    print(f"\n  📊 Summary:")
    print(f"  • Total records: {len(records)}")
    print(f"  • Vatican: {vatican}")
    print(f"  • Colosseum: {colosseum}")
    print(f"  • Date range: {min(dates)} to {max(dates)}")
    print(f"  • Upcoming: {upcoming}")
    print(f"  • Urgent (≤3d): {urgent}")

    # Sample recent bookings
    print(f"\n  📅 Recent upcoming Vatican bookings:")
    vat_upcoming = []
    for r in records:
        d = str(r.get("activityDate", ""))
        title = str(r.get("productTitle", "")).lower()
        if any(w in title for w in ["vatican","sistine","vaticani","musei"]):
            try:
                dt = datetime.strptime(d, "%Y-%m-%d").date()
                if dt >= today:
                    vat_upcoming.append((d, r.get("productTitle","")[:50], r.get("total_participants","?")))
            except: pass
    vat_upcoming.sort()
    for d, t, p in vat_upcoming[:10]:
        print(f"    {d}: {t} ({p}pax)")
else:
    print("Activity sheet not found!")

# Test writability
print(f"\n✏️ EDIT TEST:")
try:
    ws = sheet.worksheets()[0]
    col = ws.col_count
    ws.update_cell(1, col, "hydra_test_write")
    ws.update_cell(1, col, "")
    print(f"  ✅ Sheet is WRITABLE")
except Exception as e:
    print(f"  ❌ Not writable: {e}")
