"""
Booking Pipeline — the main orchestrator.

Reads Google Sheets → checks Vatican API → books tickets → writes back → notifies.

Run with:
    python -m agent.cli pipeline
    python agent/pipeline.py

The pipeline runs continuously, processing sheet rows in cycles.
Each cycle:
    1. Read pending bookings from the Master sheet
    2. Check Vatican API for each booking's date
    3. If slots available, book via browser automation
    4. Write payment link back to the sheet
    5. Notify admin via Telegram
"""

import asyncio
import logging
import signal
import sys
import time
from datetime import datetime
from typing import List

from agent.config import config
from agent.notifier import (
    notify_booking_failed,
    notify_booking_success,
    notify_no_slots,
    notify_pipeline_summary,
    notify_startup,
)
from agent.sheets import Booking, get_sheets
from agent.vatican_api import Slot, get_finder

logger = logging.getLogger(__name__)


# ── Pipeline ────────────────────────────────────────────────────────────────

class Pipeline:
    """End-to-end booking pipeline."""

    def __init__(self):
        self.sheets = get_sheets()
        self.finder = get_finder()
        self.running = True
        self.stats = {
            "cycles": 0,
            "total_checked": 0,
            "total_booked": 0,
            "total_no_slots": 0,
            "total_failed": 0,
        }

    # ── Main loop ───────────────────────────────────────────────────────

    def run(self):
        """Run the pipeline continuously."""
        logger.info("=" * 60)
        logger.info("PIPELINE STARTED")
        logger.info("  Interval: %ds", config.pipeline_interval_seconds)
        logger.info("  Max per cycle: %d", config.pipeline_max_bookings_per_cycle)
        logger.info("  Proxy: %s", "enabled" if config.oxylabs_username else "DISABLED")
        logger.info("  Admins: %s", config.admin_telegram_ids)
        logger.info("=" * 60)

        # Handle graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        if config.admin_telegram_ids:
            notify_startup()

        while self.running:
            try:
                self._run_cycle()
            except Exception as e:
                logger.error("Pipeline cycle error: %s", e, exc_info=True)
                time.sleep(30)  # Brief pause before retry
            else:
                self._sleep_interval()

        logger.info("Pipeline stopped. Stats: %s", self.stats)

    def _shutdown(self, signum, frame):
        """Handle graceful shutdown."""
        logger.info("Received signal %d — shutting down after current cycle", signum)
        self.running = False

    def _sleep_interval(self):
        """Sleep for the configured interval, checking for shutdown."""
        interval = config.pipeline_interval_seconds
        for _ in range(interval):
            if not self.running:
                break
            time.sleep(1)

    # ── Cycle ───────────────────────────────────────────────────────────

    def _run_cycle(self):
        """Run a single pipeline cycle."""
        cycle_start = time.time()
        self.stats["cycles"] += 1
        c = self.stats["cycles"]
        logger.info("--- Cycle %d ---", c)

        # 1. Read pending bookings
        pending = self.sheets.get_pending_bookings()
        if not pending:
            logger.info("No pending bookings — nothing to do")
            return

        logger.info("Cycle %d: %d pending bookings", c, len(pending))

        # Limit per cycle
        to_process = pending[: config.pipeline_max_bookings_per_cycle]

        cycle_booked = 0
        cycle_no_slots = 0
        cycle_failed = 0
        cycle_errors = []

        # 2. Process each booking
        for i, booking in enumerate(to_process):
            logger.info(
                "[%d/%d] Processing: %s %s — %s (%dv)",
                i + 1, len(to_process),
                booking.first_name, booking.last_name,
                booking.date, booking.pax,
            )

            # Check slots
            visitors = booking.pax if booking.pax > 0 else 2
            slots = self.finder.find_slots(booking.date, visitors, use_cache=False)

            if not slots:
                logger.info("  → No slots available for %s", booking.date)
                notify_no_slots(booking.date, booking.first_name, booking.last_name, visitors)
                cycle_no_slots += 1
                continue

            slot = slots[0]  # Earliest available
            logger.info("  → Slot found: %s %s", slot.date, slot.time)

            # Book
            result = asyncio.run(self._book_slot(slot, booking))

            if result["success"] and result.get("epay_url"):
                # Write payment link to sheet
                self.sheets.write_payment_link(booking, result["epay_url"])
                self.sheets.write_status(booking, "BOOKED")

                # Notify
                notify_booking_success(
                    date=slot.date,
                    time=slot.time,
                    first_name=booking.first_name,
                    last_name=booking.last_name,
                    visitors=visitors,
                    epay_url=result["epay_url"],
                    booking_id=booking.booking_id,
                )
                cycle_booked += 1
                logger.info("  → ✅ BOOKED")
            else:
                notify_booking_failed(
                    date=slot.date,
                    time=slot.time,
                    first_name=booking.first_name,
                    last_name=booking.last_name,
                    error=result.get("error", "Unknown error"),
                )
                cycle_failed += 1
                cycle_errors.append(result.get("error", "Unknown"))
                logger.error("  → ❌ Failed: %s", result.get("error"))

            # Cooldown between bookings
            if i < len(to_process) - 1:
                time.sleep(config.pipeline_cooldown_seconds)

        # 3. Report
        self.stats["total_checked"] += len(to_process)
        self.stats["total_booked"] += cycle_booked
        self.stats["total_no_slots"] += cycle_no_slots
        self.stats["total_failed"] += cycle_failed

        elapsed = time.time() - cycle_start
        logger.info(
            "Cycle %d complete in %.1fs: %d booked, %d no-slots, %d failed",
            c, elapsed, cycle_booked, cycle_no_slots, cycle_failed,
        )

        if cycle_booked > 0 or cycle_failed > 0:
            notify_pipeline_summary(
                total_checked=len(to_process),
                booked=cycle_booked,
                no_slots=cycle_no_slots,
                failed=cycle_failed,
                errors=cycle_errors,
            )

    # ── Booking ─────────────────────────────────────────────────────────

    async def _book_slot(self, slot: Slot, booking: Booking) -> dict:
        """Execute a booking — isolated async call."""
        from agent.booker import BuyerInfo, Participant, VaticanBooker

        buyer = BuyerInfo(
            first_name=booking.first_name or config.buyer_default_name or "Guest",
            last_name=booking.last_name or config.buyer_default_surname or "Guest",
            email=config.buyer_default_email or "booking@example.com",
            phone=config.buyer_default_phone or "0000000000",
            city=config.buyer_default_city,
        )

        participants = [
            Participant(
                first_name=booking.first_name,
                last_name=booking.last_name,
                ticket_type="Adult",
            )
        ]
        # Add additional participants if pax > 1
        for i in range(1, slot.visitors):
            participants.append(Participant(
                first_name=f"Guest{i + 1}",
                last_name=booking.last_name,
                ticket_type="Adult",
            ))

        booker = VaticanBooker(headless=False)
        return await booker.book(slot, buyer, participants)


# ── Entry point ─────────────────────────────────────────────────────────────

def main():
    """Run the pipeline."""
    pipeline = Pipeline()
    pipeline.run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
