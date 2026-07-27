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

        cycle_queued = 0
        cycle_no_slots = 0
        cycle_errors = []

        # 2. Check slots for each booking → queue task if slot found
        for i, booking in enumerate(to_process):
            logger.info(
                "[%d/%d] Checking: %s %s — %s (%dv)",
                i + 1, len(to_process),
                booking.first_name, booking.last_name,
                booking.date, booking.pax,
            )

            visitors = booking.pax if booking.pax > 0 else 2
            slots = self.finder.find_slots(booking.date, visitors, use_cache=False)

            if not slots:
                logger.info("  → No slots for %s", booking.date)
                notify_no_slots(booking.date, booking.first_name, booking.last_name, visitors)
                cycle_no_slots += 1
                continue

            slot = slots[0]
            logger.info("  → Slot found: %s %s — queuing for local worker", slot.date, slot.time)

            # Write task to Booking_Queue (picked up by local worker)
            try:
                task_row = self.sheets.create_booking_task(
                    booking_id=booking.booking_id,
                    date=slot.date,
                    time=slot.time,
                    visitors=visitors,
                    customer_name=f"{booking.first_name} {booking.last_name}",
                    ticket_id=slot.ticket_id,
                    slot_id=slot.slot_id,
                )
                self.sheets.write_status(booking, "QUEUED")
                cycle_queued += 1
                logger.info("  → ✅ Queued (row %d in Booking_Queue)", task_row)
            except Exception as e:
                cycle_errors.append(str(e))
                logger.error("  → Failed to queue: %s", e)

        # 3. Report
        self.stats["total_checked"] += len(to_process)
        self.stats["total_booked"] += cycle_queued
        self.stats["total_no_slots"] += cycle_no_slots

        elapsed = time.time() - cycle_start
        logger.info(
            "Cycle %d complete in %.1fs: %d queued, %d no-slots",
            c, elapsed, cycle_queued, cycle_no_slots,
        )

        if cycle_queued > 0:
            notify_pipeline_summary(
                total_checked=len(to_process),
                booked=cycle_queued,
                no_slots=cycle_no_slots,
                failed=0,
                errors=cycle_errors,
            )

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
