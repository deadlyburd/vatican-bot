#!/usr/bin/env python3
"""Fix Master sheet colors — proper rule order."""
from crm_intelligence.parsers.sheet_parser import SheetParser
from customer_care.config.bot_config import config

p = SheetParser(sheet_id=config.crm.sheet_id, credentials_file=config.crm.service_account_file)
p.connect()
master = p._sheet.worksheet("Master")
sid = master._properties["sheetId"]

# Clear all rules
master.spreadsheet.batch_update({"requests": [
    {"clearConditionalFormatRules": {"sheetId": sid}}
]})
print("Cleared old rules")

# Add rules - order matters! Last matching rule wins.
# Rule 0: YELLOW for missing info (but NOT cancelled rows, NOT complete rows)
# Rule 1-2: RED for cancelled
# Rule 3: GREEN for confirmed (overrides yellow)

# Google Sheets applies rules in order — LAST matching rule WINS.
# So put YELLOW first (weakest), then GREEN, then RED (strongest).
rules = [
    # 1. YELLOW = Missing info (applied first, overridden by green/red below)
    {"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": sid}],
        "booleanRule": {
            "condition": {"type": "TEXT_NOT_CONTAINS", "values": [{"userEnteredValue": "Complete"}]},
            "format": {"backgroundColor": {"red": 1.0, "green": 0.94, "blue": 0.7}}
        }}, "index": 0}},
    # 2. GREEN = CONFIRMED (overrides yellow)
    {"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": sid}],
        "booleanRule": {
            "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "CONFIRMED"}]},
            "format": {"backgroundColor": {"red": 0.82, "green": 0.98, "blue": 0.82}}
        }}, "index": 1}},
    # 3. RED = CANCELLED (overrides both yellow and green)
    {"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": sid}],
        "booleanRule": {
            "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "CANCELLED"}]},
            "format": {"backgroundColor": {"red": 0.98, "green": 0.78, "blue": 0.78}}
        }}, "index": 2}},
    # 4. RED = CANCELED (alternate spelling)
    {"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": sid}],
        "booleanRule": {
            "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "CANCELED"}]},
            "format": {"backgroundColor": {"red": 0.98, "green": 0.78, "blue": 0.78}}
        }}, "index": 3}},
]

master.spreadsheet.batch_update({"requests": rules})
print("Done!")
print("🟢 Green = CONFIRMED")
print("🔴 Red = CANCELLED")
print("🟡 Yellow = Missing info (only if not CONFIRMED/CANCELLED)")
print("Refresh your sheet now.")
