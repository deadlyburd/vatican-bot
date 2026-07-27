#!/usr/bin/env python3
"""
MASTER SHEET AUTO-SYNC — keeps Master in sync with Activity_Lines + Passengers
Runs every 5 minutes. Appends new bookings, updates existing ones.
"""
import time, logging, os
from datetime import date as dt, timedelta
from collections import defaultdict
from crm_intelligence.parsers.sheet_parser import SheetParser
from customer_care.config.bot_config import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS = os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")


class MasterSync:
    def __init__(self):
        self.parser = SheetParser(sheet_id=config.crm.sheet_id,
                                  credentials_file=config.crm.service_account_file)
        self._last_sync = None
        self._synced_bids = set()

    def sync(self):
        """Full sync: check for new bookings, update existing ones."""
        self.parser.connect()
        sheet = self.parser._sheet

        # 1. Read current Master state
        try:
            master = sheet.worksheet("Master")
            master_data = master.get_all_values()
            master_bids = set()
            for row in master_data[1:]:  # skip header
                if len(row) > 6 and row[6].strip():
                    master_bids.add(row[6].strip())
            logger.info(f"Master: {len(master_bids)} booking IDs")
        except Exception:
            logger.info("Master sheet not found — run rebuild_master.py first")
            return

        # 2. Read Activity_Lines for new/updated bookings (filtered to 90 days)
        act_ws = sheet.worksheet("Activity_Lines")
        act_data = act_ws.get_all_values()
        act_headers = act_data[0]
        acols = {h.lower(): i for i, h in enumerate(act_headers)}

        today = dt.today()
        cutoff = today - timedelta(days=90)

        def parse_date(d):
            try: return dt.fromisoformat(str(d).strip())
            except: return None

        new_rows = []
        updated_bids = set()
        total_checked = 0

        for row in act_data[1:]:
            if len(row) <= acols.get("bookingid", 0): continue
            bid = str(row[acols["bookingid"]]).strip()
            if not bid: continue

            # Filter by date - only recent 90 days + upcoming
            d = parse_date(str(row[acols.get("activitydate", 1)] or ""))
            if not d or d < cutoff:
                continue
            total_checked += 1

            # Check if this is newer than what's in Master
            status = str(row[acols.get("status", 5)] or "").strip()
            conf = str(row[acols.get("confirmationcode", acols.get("productconfirmationcode", 6))] or "").strip()

            if bid not in master_bids:
                new_rows.append(row)
                master_bids.add(bid)
            else:
                # Check if status changed
                for mr in master_data[1:]:
                    if len(mr) > 6 and mr[6].strip() == bid:
                        old_status = mr[7].strip() if len(mr) > 7 else ""
                        if old_status != status:
                            updated_bids.add(bid)
                        break

        # 3. Read Passengers for new rows
        if new_rows:
            pass_ws = sheet.worksheet("Passengers")
            pass_data = pass_ws.get_all_values()
            pass_headers = pass_data[0]
            pax_map = defaultdict(list)
            bid_c = pass_headers.index("bookingId") if "bookingId" in pass_headers else 0
            fn_c = pass_headers.index("firstName") if "firstName" in pass_headers else 1
            ln_c = pass_headers.index("lastName") if "lastName" in pass_headers else 2

            for pr in pass_data[1:]:
                if len(pr) > max(bid_c, fn_c, ln_c):
                    pbid = str(pr[bid_c]).strip()
                    name = (str(pr[fn_c]) + " " + str(pr[ln_c])).strip()
                    if pbid and name: pax_map[pbid].append(name)

            # Build new rows for Master
            append_rows = []
            for nr in new_rows:
                bid = str(nr[acols["bookingid"]]).strip()
                datev = str(nr[acols.get("activitydate", 1)] or "").strip()
                timev = str(nr[acols.get("starttime", 2)] or "").strip()
                prod = str(nr[acols.get("producttitle", 3)] or "")[:80]
                pax = str(nr[acols.get("totalparticipants", 4)] or "1")
                main_name = str(nr[acols.get("customername", 5)] or "").strip()
                status = str(nr[acols.get("status", 6)] or "").strip()
                conf = str(nr[acols.get("confirmationcode", acols.get("productconfirmationcode", 7))] or "").strip()

                pax_names = pax_map.get(bid, [])
                if not pax_names:
                    parts = main_name.split()
                    pax_names = [main_name] if main_name else ["Unknown"]

                for pname in pax_names[:max(int(pax or 1), 1)]:
                    parts = pname.strip().split()
                    fname = parts[0] if parts else ""
                    lname = " ".join(parts[1:]) if len(parts) > 1 else ""
                    append_rows.append([datev, timev, prod, pax, fname, lname, bid, status, conf, "", "OK", "Bokun/Viator"])

            if append_rows:
                try:
                    # Find last empty row in Master
                    last_row = len(master_data) + 1
                    master.update(append_rows, f"A{last_row}", value_input_option="RAW")
                    logger.info(f"✅ Added {len(append_rows)} new rows to Master")
                except Exception as e:
                    logger.error(f"Failed to append: {e}")

        # 4. Update changed statuses
        if updated_bids:
            for mr_idx, mr in enumerate(master_data[1:], start=2):
                bid = mr[6].strip() if len(mr) > 6 else ""
                if bid in updated_bids:
                    # Find new status from Activity_Lines
                    for nr in act_data[1:]:
                        if len(nr) <= acols.get("bookingid", 0): continue
                        if str(nr[acols["bookingid"]]).strip() == bid:
                            new_status = str(nr[acols.get("status", 6)] or "").strip()
                            master.update([[new_status]], f"H{mr_idx}", value_input_option="RAW")
                            break
            logger.info(f"✅ Updated {len(updated_bids)} statuses")

        # Log summary
        logger.info(f"Sync done: {len(new_rows)} new (from {total_checked} recent), {len(updated_bids)} updated")

    def notify_admin(self, msg):
        for aid in ADMIN_IDS:
            a = aid.strip()
            if a and TELEGRAM_TOKEN:
                import requests
                try:
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                  json={"chat_id": a, "text": msg}, timeout=5)
                except: pass

    def run(self, interval=300):
        """Run sync every N seconds."""
        logger.info(f"🚀 Master Sync starting (every {interval}s)")
        self.notify_admin("🔄 *Master Sync Active* — auto-updating every 5 minutes")
        while True:
            try:
                self.sync()
            except Exception as e:
                logger.error(f"Sync error: {e}")
            time.sleep(interval)


if __name__ == "__main__":
    sync = MasterSync()
    sync.run()
