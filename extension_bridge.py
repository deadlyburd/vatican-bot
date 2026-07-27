#!/usr/bin/env python3
"""
EXTENSION BRIDGE — CRM → Slot Finder → Extension Commands → Sheet + Telegram
==============================================================================
1. Reads CRM bookings that need Vatican tickets
2. Uses SlotFinder (search + timeavail ONLY) to discover open slots
3. Creates commands for the Chrome extension to execute
4. Extension picks up commands, books tickets, reports results
5. Results → payment links written to CRM sheet + Telegram notification

This is the conductor. The SlotFinder is the eyes. The extension is the hands.
"""

import os
import sys
import json
import logging
import threading
import time
from typing import List, Dict, Optional
from datetime import date, datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from slot_finder import SlotFinder, AvailableSlot
from crm_intelligence.auto_snipe import CRMAutoSnipeService, SnipeTarget

logger = logging.getLogger(__name__)

# Config
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
SCAN_INTERVAL = int(os.getenv("BRIDGE_SCAN_INTERVAL", "60"))  # seconds between CRM scans
MAX_COMMANDS = int(os.getenv("BRIDGE_MAX_COMMANDS", "5"))     # max pending commands at once


class ExtensionBridge:
    """
    Bridges CRM bookings → slot discovery → extension booking commands.
    """

    def __init__(self):
        self.finder = SlotFinder()
        self.crm = CRMAutoSnipeService()
        self._running = False
        self._processed: set = set()  # booking_id keys we've already dispatched

    # ── Main Loop ──────────────────────────────────────────────────

    def run_cycle(self):
        """Single cycle: scan CRM → find slots → create extension commands."""
        try:
            # 1. Scan CRM for Vatican bookings
            targets = self.crm.scan_crm_for_targets()
            upcoming = [t for t in targets if t.days_until >= 0 and t.status == "pending"]

            if not upcoming:
                logger.debug("No pending Vatican targets in CRM")
                return

            logger.info(f"📋 {len(upcoming)} CRM targets to check")

            # 2. For each target, check if slots are available
            for target in upcoming[:10]:  # Process max 10 per cycle
                key = f"{target.booking_id}_{target.activity_date}"
                if key in self._processed:
                    continue

                # Check if slot available
                slots = self.finder.find_slots(
                    target.activity_date,
                    target.visitors,
                    use_cache=True,
                )

                if slots:
                    # Found available slots! Create extension command
                    best_slot = slots[0]  # First afternoon slot (already sorted)
                    logger.info(
                        f"🎯 Slot available: {target.activity_date} {best_slot.time} "
                        f"— creating extension command for {target.customer_name}"
                    )

                    cmd_id = self.create_command(target, best_slot)
                    if cmd_id:
                        self._processed.add(key)
                        target.status = "sniping"
                        logger.info(f"✅ Command {cmd_id} created for {key}")

                        # Notify admin
                        self.crm.notify_admin(
                            f"🔍 *Slot Found — Dispatching Extension*\n\n"
                            f"📅 {target.activity_date} at {best_slot.time}\n"
                            f"👥 {target.visitors} visitors\n"
                            f"👤 {target.customer_name}\n"
                            f"📋 {target.product_title[:60]}\n\n"
                            f"_Chrome extension will book automatically..._"
                        )
                else:
                    logger.debug(f"No slots for {target.activity_date} ({target.customer_name})")

                # Rate limit between slot checks
                time.sleep(0.5)

        except Exception as e:
            logger.error(f"Bridge cycle error: {e}")

    def create_command(self, target: SnipeTarget, slot: AvailableSlot) -> Optional[str]:
        """
        Create an extension booking command from a CRM target and available slot.
        """
        # Build profile from CRM data
        profile = {
            "first_name": target.customer_name.split()[0] if target.customer_name else "Cliente",
            "last_name": " ".join(target.customer_name.split()[1:]) if len(target.customer_name.split()) > 1 else "Vaticano",
            "email": target.customer_email or "cliente@email.it",
            "phone": "3331234567",
            "city": "ROMA",
        }

        # Build participant list
        participants = []
        for i in range(target.visitors):
            participants.append({
                "first_name": f"Visitatore{i + 1}",
                "last_name": f"Cognome{i + 1}",
            })

        try:
            # Import the view function and call it directly
            from backend.monitors.extension_views import create_extension_command

            cmd_id = create_extension_command(
                date=target.activity_date,
                visitors=max(1, target.visitors),
                time_slot=slot.time,
                ticket_id=slot.ticket_id,
                ticket_name=slot.ticket_name,
                profile=profile,
                participants=participants,
                booking_id=target.booking_id,
                customer_name=target.customer_name,
                customer_email=target.customer_email,
                priority=target.priority,
            )
            return cmd_id

        except Exception as e:
            logger.error(f"Failed to create extension command: {e}")
            return None

    # ── Manual trigger ─────────────────────────────────────────────

    def snipe_now(self, date_str: str, visitors: int = 2) -> Optional[str]:
        """
        Manual trigger: check a specific date and create command if slots available.
        Returns command ID if created.
        """
        slots = self.finder.find_slots(date_str, visitors, use_cache=False)
        if not slots:
            logger.info(f"No slots available for {date_str}")
            return None

        slot = slots[0]  # Best slot (afternoon preferred)

        # Build profile
        profile = {
            "first_name": "Marco",
            "last_name": "Rossi",
            "email": "marco.rossi@email.it",
            "phone": "3331234567",
            "city": "ROMA",
        }

        participants = [
            {"first_name": f"Visitatore{i + 1}", "last_name": f"Cognome{i + 1}"}
            for i in range(visitors)
        ]

        from backend.monitors.extension_views import create_extension_command

        cmd_id = create_extension_command(
            date=date_str,
            visitors=visitors,
            time_slot=slot.time,
            ticket_id=slot.ticket_id,
            ticket_name=slot.ticket_name,
            profile=profile,
            participants=participants,
        )

        logger.info(f"🎯 Manual snipe: {date_str} {slot.time} → cmd={cmd_id}")
        return cmd_id

    # ── Lifecycle ──────────────────────────────────────────────────

    def start(self, interval: int = None):
        """Start the bridge loop."""
        if interval is None:
            interval = SCAN_INTERVAL

        self._running = True
        logger.info(f"🚀 Extension Bridge starting (scan every {interval}s)")

        while self._running:
            try:
                self.run_cycle()
            except Exception as e:
                logger.error(f"Bridge cycle error: {e}")

            for _ in range(interval):
                if not self._running:
                    break
                time.sleep(1)

    def stop(self):
        """Stop the bridge."""
        self._running = False
        logger.info("Extension Bridge stopped")


# ── Global instance ──────────────────────────────────────────────────

bridge = ExtensionBridge()


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )

    if len(sys.argv) > 1:
        # Manual snipe mode
        date_str = sys.argv[1]
        visitors = int(sys.argv[2]) if len(sys.argv) > 2 else 2
        print(f"\n🎯 Manual Snipe: {date_str} | {visitors} visitors\n")

        cmd_id = bridge.snipe_now(date_str, visitors)
        if cmd_id:
            print(f"✅ Command created: {cmd_id}")
            print(f"   Extension will pick it up within 5 seconds")
        else:
            print(f"❌ No slots available for {date_str}")
    else:
        # Continuous bridge mode
        print("\n🌉 Extension Bridge — Continuous Mode")
        print(f"   Scanning CRM every {SCAN_INTERVAL}s")
        print(f"   Max {MAX_COMMANDS} pending commands\n")
        bridge.start()
