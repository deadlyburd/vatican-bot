#!/usr/bin/env python3
"""Fix Master sheet — re-do with proper headers and descending dates."""
import time
from datetime import datetime

def log(msg): print(f"[{datetime.now():%H:%M:%S}] {msg}")

def fix():
    from crm_intelligence.parsers.sheet_parser import SheetParser
    from customer_care.config.bot_config import config
    import gspread
    from google.oauth2.service_account import Credentials

    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(config.crm.service_account_file, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(config.crm.sheet_id)

    # Delete any existing Master sheets, create fresh
    log("Removing old Master...")
    for name in ['Master', '📊 Master']:
        try:
            old = sheet.worksheet(name)
            sheet.del_worksheet(old)
            time.sleep(2)
        except: pass

    master = sheet.add_worksheet('📊 Master', 3000, 15)
    time.sleep(2)

    # Headers — Product first, then key details
    headers = ['Product', 'Date', 'Time', 'Pax', 'Customer', 'Booking ID',
               'Status', 'Confirmation', 'Payment Link', 'Platform']
    master.update([headers], 'A1')
    time.sleep(1)

    # Format headers
    master.format('A1:J1', {
        'backgroundColor': {'red': 0.15, 'green': 0.3, 'blue': 0.7},
        'textFormat': {'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}, 'bold': True, 'fontSize': 11},
    })
    master.freeze(1, 0)
    time.sleep(1)

    # Read Activity_Lines — filter to recent + upcoming only
    log("Reading & filtering...")
    ws = sheet.worksheet('Activity_Lines')
    records = ws.get_all_records()

    from datetime import date as dt, timedelta
    today = dt.today()
    cutoff = today - timedelta(days=90)  # Last 3 months

    def parse_date(d):
        try: return dt.fromisoformat(str(d))
        except: return None

    # Filter: keep recent (last 90 days) + all upcoming
    filtered = []
    for r in records:
        d = parse_date(r.get('activityDate',''))
        if d and d >= cutoff:
            filtered.append(r)

    # Sort by date ascending (upcoming first)
    filtered.sort(key=lambda r: parse_date(r.get('activityDate','')) or dt(2000,1,1))

    # Split: upcoming vs past
    upcoming = [r for r in filtered if parse_date(r.get('activityDate','')) and parse_date(r.get('activityDate','')) >= today]
    past = [r for r in filtered if parse_date(r.get('activityDate','')) and parse_date(r.get('activityDate','')) < today]
    log(f"  Upcoming: {len(upcoming)}, Recent past: {len(past)}, Total: {len(filtered)}")

    # Batch write — upcoming first, then recent past
    batch = []
    row = 2
    total = 0
    time.sleep(2)

    for r in upcoming + past:
        if not any(str(r.get(k,'')).strip() for k in r): continue
        status = str(r.get('status', '') or '').upper()
        batch.append([
            str(r.get('productTitle', '') or '')[:80],
            str(r.get('activityDate', '') or ''),
            str(r.get('startTime', '') or ''),
            str(r.get('totalParticipants', '') or ''),
            str(r.get('customerName', '') or ''),
            str(r.get('bookingId', '') or ''),
            status,
            str(r.get('confirmationCode', '') or r.get('productConfirmationCode', '') or ''),
            '',  # payment link placeholder
            'Bokun/Viator',
        ])
        total += 1

        if len(batch) >= 50:
            master.update(batch, f'A{row}')
            row += len(batch)
            batch = []
            time.sleep(2.5)

    if batch:
        master.update(batch, f'A{row}')
        total += len(batch)

    log(f"  Written {total} rows")

    # Color-code using conditional formatting (efficient, no per-row API calls)
    log("  Adding conditional colors...")
    time.sleep(2)
    try:
        master.batch_update({'requests': [
            # Green for CONFIRMED
            {'addConditionalFormatRule': {'rule': {
                'ranges': [{'sheetId': master.id, 'startRowIndex': 1, 'endRowIndex': total + 2}],
                'booleanRule': {
                    'condition': {'type': 'TEXT_CONTAINS', 'values': [{'userEnteredValue': 'CONFIRMED'}]},
                    'format': {'backgroundColor': {'red': 0.85, 'green': 1.0, 'blue': 0.85}}
                }
            }}},
            # Red for CANCELLED
            {'addConditionalFormatRule': {'rule': {
                'ranges': [{'sheetId': master.id, 'startRowIndex': 1, 'endRowIndex': total + 2}],
                'booleanRule': {
                    'condition': {'type': 'TEXT_CONTAINS', 'values': [{'userEnteredValue': 'CANCELLED'}]},
                    'format': {'backgroundColor': {'red': 1.0, 'green': 0.85, 'blue': 0.85}}
                }
            }}},
        ]})
    except Exception as e:
        log(f"  Color error (non-critical): {e}")

    # Column widths
    try:
        requests = [
            {'updateDimensionProperties': {'range': {'sheetId': master.id, 'dimension': 'COLUMNS', 'startIndex': 0, 'endIndex': 1}, 'properties': {'pixelSize': 350}, 'fields': 'pixelSize'}},  # Product
            {'updateDimensionProperties': {'range': {'sheetId': master.id, 'dimension': 'COLUMNS', 'startIndex': 1, 'endIndex': 2}, 'properties': {'pixelSize': 90}, 'fields': 'pixelSize'}},   # Date
            {'updateDimensionProperties': {'range': {'sheetId': master.id, 'dimension': 'COLUMNS', 'startIndex': 4, 'endIndex': 5}, 'properties': {'pixelSize': 150}, 'fields': 'pixelSize'}},  # Customer
        ]
        master.batch_update({'requests': requests})
    except: pass

    log(f"\n✅ Master rebuilt!")
    log(f"📅 {total} bookings (upcoming + last 90 days)")
    log(f"🟢 Green = CONFIRMED | 🔴 Red = CANCELLED")
    log(f"🔗 https://docs.google.com/spreadsheets/d/{config.crm.sheet_id}/edit")

if __name__ == '__main__':
    fix()
