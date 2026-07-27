#!/usr/bin/env python3
"""Write Master sheet — headers first, then data in batches."""
import time
from datetime import date as dt, timedelta

def log(msg): print(f"[{dt.today():%H:%M}] {msg}")

def write():
    from crm_intelligence.parsers.sheet_parser import SheetParser
    from customer_care.config.bot_config import config

    p = SheetParser(sheet_id=config.crm.sheet_id, credentials_file=config.crm.service_account_file)
    p.connect()

    # Delete old Master
    for name in ['Master', '📊 Master']:
        try:
            p._sheet.del_worksheet(p._sheet.worksheet(name))
            time.sleep(2)
        except: pass

    # Create fresh Master
    master = p._sheet.add_worksheet('Master', 2000, 10)
    time.sleep(2)

    # ── STEP 1: Write headers FIRST ──
    headers = ['Product', 'Date', 'Time', 'Pax', 'Customer', 'Booking ID',
               'Status', 'Confirmation', 'Payment Link', 'Platform']
    master.update([headers], 'A1')
    log("Headers written")

    # Format + freeze
    master.format('A1:J1', {
        'backgroundColor': {'red': 0.15, 'green': 0.3, 'blue': 0.7},
        'textFormat': {'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}, 'bold': True},
    })
    master.freeze(1, 0)
    log("Headers formatted")
    time.sleep(2)

    # ── STEP 2: Prepare data ──
    act_ws = p._sheet.worksheet('Activity_Lines')
    records = act_ws.get_all_records()

    today = dt.today()
    cutoff = today - timedelta(days=90)

    def parse_date(d):
        try: return dt.fromisoformat(str(d))
        except: return None

    filtered = [r for r in records if parse_date(r.get('activityDate','')) and parse_date(r.get('activityDate','')) >= cutoff]
    filtered.sort(key=lambda r: parse_date(r.get('activityDate','')) or dt(2000,1,1))

    upcoming = [r for r in filtered if parse_date(r.get('activityDate','')) and parse_date(r.get('activityDate','')) >= today]
    recent = [r for r in filtered if parse_date(r.get('activityDate','')) and parse_date(r.get('activityDate','')) < today]

    all_data = upcoming + recent
    log(f"Data: {len(upcoming)} upcoming + {len(recent)} recent = {len(all_data)}")

    # ── STEP 3: Write data in batches ──
    batch = []
    row = 2
    total = 0

    for r in all_data:
        if not any(str(r.get(k,'')).strip() for k in r): continue
        batch.append([
            str(r.get('productTitle', '') or '')[:80],
            str(r.get('activityDate', '') or ''),
            str(r.get('startTime', '') or ''),
            str(r.get('totalParticipants', '') or ''),
            str(r.get('customerName', '') or ''),
            str(r.get('bookingId', '') or ''),
            str(r.get('status', '') or ''),
            str(r.get('confirmationCode', '') or r.get('productConfirmationCode', '') or ''),
            '',
            'Bokun/Viator',
        ])
        total += 1

        if len(batch) >= 50:
            try:
                master.update(batch, f'A{row}')
                log(f"  ✓ Rows {row}-{row+len(batch)-1} written ({total} total)")
                row += len(batch)
                batch = []
                time.sleep(3)  # Respect rate limit
            except Exception as e:
                log(f"  ✗ Error at row {row}: {e}")
                time.sleep(10)
                try:
                    master.update(batch, f'A{row}')
                    log(f"  ✓ Retry OK at row {row}")
                    row += len(batch)
                    batch = []
                except Exception as e2:
                    log(f"  ✗ Retry failed: {e2}")
                    break

    # Write final batch
    if batch:
        try:
            master.update(batch, f'A{row}')
            log(f"  ✓ Final batch: rows {row}-{row+len(batch)-1}")
        except Exception as e:
            log(f"  ✗ Final batch error: {e}")

    log(f"\n✅ Done! Master sheet at row {row}")
    log(f"🔗 https://docs.google.com/spreadsheets/d/{config.crm.sheet_id}/edit")

if __name__ == '__main__':
    write()
