#!/usr/bin/env python3
"""
AUTOMATED BOOKING PIPELINE — runs on server
1. Every 5 min: scan CRM for Vatican bookings
2. If found: check for available slots via API
3. Create booking commands → local machine picks up
4. Local machine books → pushes epay back → sheet updated + Telegram
"""
import os, sys, time, json, logging, requests
from datetime import datetime, date, timedelta
from crm_intelligence.auto_snipe import CRMAutoSnipeService
from slot_finder import SlotFinder

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

BACKEND = os.getenv("SERVER_BASE_URL", "http://backend:8000")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS = os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if os.getenv("ADMIN_TELEGRAM_IDS") else []
SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

def notify_telegram(msg):
    for aid in ADMIN_IDS:
        a = aid.strip()
        if a and TELEGRAM_TOKEN:
            try:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={"chat_id": a, "text": msg, "parse_mode": "Markdown"}, timeout=10)
            except: pass

def run_cycle():
    """Single pipeline cycle."""
    try:
        crm = CRMAutoSnipeService()
        finder = SlotFinder()

        # 1. Scan CRM
        targets = crm.scan_crm_for_targets()
        pending = [t for t in targets if t.status == "pending" and t.days_until >= 0]
        if not pending:
            logger.debug("No pending Vatican targets")
            return

        urgent = [t for t in pending if t.days_until <= 3]
        # Only notify once per batch of urgent bookings (not every cycle)
        if urgent and not hasattr(run_cycle, '_last_urgent_count'):
            run_cycle._last_urgent_count = 0
        if urgent and len(urgent) != run_cycle._last_urgent_count:
            notify_telegram(f"🔴 *{len(urgent)} Urgent Vatican Bookings* — checking slots...")
            run_cycle._last_urgent_count = len(urgent)

        # 2. For each target, check slots + create commands
        for target in pending[:10]:
            logger.info(f"Checking: {target.activity_date} ({target.visitors}v) — {target.customer_name}")
            slots = finder.find_slots(target.activity_date, target.visitors, use_cache=False)
            if slots:
                s = slots[0]
                logger.info(f"  ✅ SLOT: {target.activity_date} {s.time}")

                # Create extension command for local booker
                from backend.monitors.extension_views import create_extension_command
                cmd_id = create_extension_command(
                    date=target.activity_date, visitors=target.visitors,
                    time_slot=s.time, ticket_id=s.ticket_id, ticket_name=s.ticket_name,
                    booking_id=target.booking_id, customer_name=target.customer_name,
                    customer_email=target.customer_email,
                )
                logger.info(f"  Command: {cmd_id}")
                target.status = "sniping"

                notify_telegram(
                    f"🎯 *Slot Found!*\n📅 {target.activity_date} {s.time}\n"
                    f"👥 {target.visitors}v | 👤 {target.customer_name}\n"
                    f"⏳ _Waiting for local booker to execute..._"
                )
            else:
                logger.info(f"  ❌ No slots for {target.activity_date}")
            time.sleep(1)

    except Exception as e:
        logger.error(f"Pipeline error: {e}")

if __name__ == "__main__":
    logger.info("🚀 Auto-Pipeline starting (CRM scan every 5 min)")
    notify_telegram("🟢 *Auto-Pipeline Active*\nScanning CRM every 5 minutes for Vatican bookings.")
    while True:
        try:
            run_cycle()
        except Exception as e:
            logger.error(f"Cycle error: {e}")
        time.sleep(300)  # 5 minutes
