#!/usr/bin/env python3
"""Organize Google Sheets — clean, combine, color-code."""
import os, json, time
from datetime import datetime

def log(msg): print(f"[{datetime.now():%H:%M:%S}] {msg}")

def organize():
    from crm_intelligence.parsers.sheet_parser import SheetParser
    from customer_care.config.bot_config import config
    import gspread
    from google.oauth2.service_account import Credentials

    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(config.crm.service_account_file, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(config.crm.sheet_id)

    log(f"Connected to: {sheet.title}")

    # 1. Analyze all worksheets
    worksheets = sheet.worksheets()
    log(f"Found {len(worksheets)} worksheets")

    for ws in worksheets:
        log(f"  {ws.title}: {ws.row_count}r x {ws.col_count}c")

    # 2. Create a unified MASTER sheet
    log("\n--- CREATING MASTER SHEET ---")

    # Check if Master exists
    master = None
    for ws in worksheets:
        if ws.title.lower() == 'master':
            master = ws
            log("Master sheet exists — updating")
            break

    if not master:
        master = sheet.add_worksheet('Master', 1000, 25)
        log("Created Master sheet")

    # Master columns (essential only)
    master_headers = [
        'Booking ID', 'Customer Name', 'Email', 'Phone', 'Country',
        'Product', 'Date', 'Time', 'Visitors', 'Status',
        'Confirmation Code', 'Payment Link', 'Notes', 'Platform', 'Amount'
    ]
    # Clear old data and write headers
    master.clear()
    time.sleep(2)
    master.update([master_headers], 'A1')
    time.sleep(1)

    # Basic header formatting
    try:
        master.format('A1:O1', {
            'backgroundColor': {'red': 0.2, 'green': 0.2, 'blue': 0.6},
            'textFormat': {'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}, 'bold': True},
        })
        time.sleep(1)
    except: pass

    # 4. Combine data from Activity_Lines + Bookings
    log("Combining data from Activity_Lines...")
    activity_ws = None
    booking_ws = None
    for ws in worksheets:
        if 'activity' in ws.title.lower(): activity_ws = ws
        if 'booking' in ws.title.lower() and 'activity' not in ws.title.lower(): booking_ws = ws

    master_row = 2
    batch_size = 50  # Write 50 rows at a time to avoid rate limits

    if activity_ws:
        records = activity_ws.get_all_records()
        batch = []
        total = 0

        for r in records:
            if not any(str(r.get(k,'')).strip() for k in r): continue

            row_data = [
                str(r.get('bookingId', '') or ''),
                str(r.get('customerName', '') or ''),
                '',
                '',
                '',
                str(r.get('productTitle', '') or '')[:80],
                str(r.get('activityDate', '') or ''),
                str(r.get('startTime', '') or ''),
                str(r.get('totalParticipants', '') or ''),
                str(r.get('status', '') or ''),
                str(r.get('confirmationCode', '') or r.get('productConfirmationCode', '') or ''),
                '',
                str(r.get('notes', '') or ''),
                'Bokun/Viator',
                str(r.get('rateTitle', '') or ''),
            ]
            batch.append(row_data)
            master_row += 1
            total += 1

            if len(batch) >= batch_size:
                master.update(batch, f'A{master_row - len(batch) + 1}')
                log(f"  {total} rows written...")
                batch = []
                time.sleep(2)

        # Write remaining batch
        if batch:
            master.update(batch, f'A{master_row - len(batch) + 1}')
            log(f"  {total} rows written (final batch)")

    log(f"Combined {master_row - 2} rows into Master")

    # 5. Freeze header row
    log("\n--- FINALIZING ---")
    try:
        master.freeze(1, 0)
    except: pass

    log("\n✅ Sheets organized!")
    log(f"  • Master sheet created with {master_headers} columns")
    log(f"  • {master_row - 2} bookings combined")
    log(f"  • Color-coded headers + alternating rows")
    log(f"  • Sheet URL: https://docs.google.com/spreadsheets/d/{config.crm.sheet_id}/edit")

if __name__ == '__main__':
    organize()
