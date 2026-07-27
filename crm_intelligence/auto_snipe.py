"""
CRM AUTO-SNIPE ENGINE
======================
Reads Google Sheets CRM → finds Vatican bookings needing tickets →
auto-creates snipe tasks → writes payment links back to sheet →
notifies admin on Telegram.

This is the autonomous operations brain for the travel agency.
"""

import os
import json
import logging
import threading
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
BACKEND = os.getenv("SERVER_BASE_URL", BACKEND_URL)
if not BACKEND.startswith("http"):
    BACKEND = f"http://{BACKEND}"

CRM_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS = os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")

# Vatican visitor limits
DEFAULT_VATICAN_VISITORS = 4
DEFAULT_VATICAN_TIME_SLOT = "09:00"


@dataclass
class SnipeTarget:
    """A booking that needs Vatican tickets auto-sniped."""
    booking_id: str
    customer_name: str
    customer_email: str
    activity_date: str          # YYYY-MM-DD
    visitors: int
    product_title: str
    confirmation_code: str
    priority: int = 5           # 1=highest, 10=lowest
    status: str = "pending"     # pending, sniping, success, failed
    payment_link: str = ""
    hold_id: int = 0
    notes: str = ""

    @property
    def date_obj(self) -> date:
        try:
            return datetime.strptime(self.activity_date, "%Y-%m-%d").date()
        except ValueError:
            # Try DD/MM/YYYY
            try:
                return datetime.strptime(self.activity_date, "%d/%m/%Y").date()
            except ValueError:
                return date.today()

    @property
    def days_until(self) -> int:
        return (self.date_obj - date.today()).days


class CRMAutoSnipeService:
    """
    Autonomous snipe engine.

    1. Reads CRM for upcoming Vatican bookings
    2. Creates snipe tasks via backend API
    3. Monitors snipe results
    4. Writes payment links back to Google Sheets
    5. Notifies admin on Telegram
    """

    def __init__(self):
        self._parser = None
        self._sheet = None
        self._running = False
        self._targets: Dict[str, SnipeTarget] = {}
        self._lock = threading.Lock()

    @property
    def parser(self):
        if self._parser is None:
            from crm_intelligence.parsers.sheet_parser import SheetParser
            from customer_care.config.bot_config import config
            self._parser = SheetParser(
                sheet_id=CRM_SHEET_ID,
                credentials_file=config.crm.service_account_file,
            )
        return self._parser

    # ── CRM Reading ──────────────────────────────────────────────────

    def scan_crm_for_targets(self) -> List[SnipeTarget]:
        """
        Scan CRM Activity_Lines for Vatican bookings that need tickets.

        Filters:
        - Activity date is in the future
        - Product is Vatican-related
        - Status is CONFIRMED (not cancelled)
        - No existing payment link / not already sniped
        """
        targets = []
        try:
            self.parser.connect()
            activities = self.parser.parse_activity_lines(limit=3000)
            today = date.today()

            for a in activities:
                # Parse date
                try:
                    a_date = datetime.strptime(a.activity_date, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    try:
                        a_date = datetime.strptime(a.activity_date, "%d/%m/%Y").date()
                    except (ValueError, TypeError):
                        continue

                # Skip past dates
                if a_date < today:
                    continue

                # Only Vatican
                title_lower = (a.product_title or "").lower()
                is_vatican = any(w in title_lower for w in (
                    "vatican", "sistine", "vaticani", "musei", "papal",
                    "st peter", "basilica", "vaticano"
                ))

                if not is_vatican:
                    continue

                # Only active bookings
                if a.status and a.status.upper() in ("CANCELLED", "CANCELED", "NO_SHOW"):
                    continue

                # Check if we already have this
                key = f"{a.booking_id}_{a.activity_date}"
                if key in self._targets:
                    existing = self._targets[key]
                    if existing.status in ("success", "sniping"):
                        continue

                # Priority: closer dates = higher priority
                days_until = (a_date - today).days
                if days_until <= 3:
                    priority = 1
                elif days_until <= 7:
                    priority = 2
                elif days_until <= 14:
                    priority = 3
                elif days_until <= 30:
                    priority = 5
                else:
                    priority = 8

                target = SnipeTarget(
                    booking_id=a.booking_id,
                    customer_name=getattr(a, 'customer_name', '') or '',
                    customer_email='',  # Will be enriched from bookings
                    activity_date=a.activity_date,
                    visitors=a.total_participants or DEFAULT_VATICAN_VISITORS,
                    product_title=a.product_title,
                    confirmation_code=a.product_confirmation_code or a.confirmation_code or '',
                    priority=priority,
                )

                targets.append(target)
                self._targets[key] = target

            # Enrich with customer emails from bookings
            try:
                bookings = self.parser.parse_bookings(limit=500)
                booking_map = {b.booking_id: b for b in bookings}
                for target in targets:
                    b = booking_map.get(target.booking_id)
                    if b and b.customer and b.customer.email:
                        target.customer_email = b.customer.email
            except Exception as e:
                logger.warning(f"Could not enrich customer emails: {e}")

            logger.info(f"🔍 CRM scan: {len(targets)} Vatican targets found")
            return sorted(targets, key=lambda t: t.priority)

        except Exception as e:
            logger.error(f"CRM scan failed: {e}")
            return []

    # ── Snipe Execution (via Extension Bridge) ─────────────────────

    def create_extension_snipe(self, target: SnipeTarget) -> Optional[str]:
        """
        Check availability via SlotFinder, then create extension booking command.
        Returns command_id if successful.
        """
        try:
            from slot_finder import SlotFinder

            finder = SlotFinder()
            slots = finder.find_slots(
                target.activity_date,
                max(1, target.visitors),
                use_cache=False,
            )

            if not slots:
                logger.info(f"No slots available for {target.activity_date}")
                return None

            slot = slots[0]  # Best slot (afternoon preferred)

            # Build profile
            name_parts = (target.customer_name or "Cliente Vaticano").split()
            profile = {
                "first_name": name_parts[0],
                "last_name": " ".join(name_parts[1:]) if len(name_parts) > 1 else "Vaticano",
                "email": target.customer_email or "cliente@email.it",
                "phone": "3331234567",
                "city": "ROMA",
            }
            participants = [
                {"first_name": f"Visitatore{i+1}", "last_name": f"Cognome{i+1}"}
                for i in range(max(1, target.visitors))
            ]

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

            logger.info(
                f"⚡ Extension snipe created: cmd={cmd_id} — "
                f"{target.activity_date} {slot.time} — {target.customer_name}"
            )
            return cmd_id

        except ImportError as e:
            logger.warning(f"Extension bridge not available: {e}")
            return None
        except Exception as e:
            logger.error(f"Extension snipe error: {e}")
            return None

    # ── CRM Write-Back ───────────────────────────────────────────────

    def write_payment_link_to_sheet(
        self,
        booking_id: str,
        activity_date: str,
        payment_link: str,
        confirmation: str = "",
    ) -> bool:
        """
        Write the payment link back to the Google Sheet.
        Updates the Activity_Lines row with payment info.
        """
        try:
            self.parser.connect()
            sheet = self.parser._sheet

            # Find the Activity_Lines worksheet
            activity_sheet = None
            for ws in sheet.worksheets():
                if "activity" in ws.title.lower() or "line" in ws.title.lower():
                    activity_sheet = ws
                    break

            if not activity_sheet:
                logger.error("Activity_Lines worksheet not found")
                return False

            # Get all records
            records = activity_sheet.get_all_records()
            headers = activity_sheet.row_values(1)

            # Find payment/notes columns
            payment_col = None
            notes_col = None
            for i, h in enumerate(headers):
                hl = str(h).lower()
                if "payment" in hl and ("link" in hl or "url" in hl):
                    payment_col = i + 1
                if "note" in hl and payment_col is None:
                    notes_col = i + 1

            # If no payment column, use notes
            if payment_col is None:
                payment_col = notes_col

            if payment_col is None:
                # Add a payment_link column
                payment_col = len(headers) + 1
                activity_sheet.update_cell(1, payment_col, "payment_link")

            # Find the matching row
            for row_idx, record in enumerate(records, start=2):
                rid = str(record.get("bookingId", record.get("BookingId", "")))
                rdate = str(record.get("activityDate", record.get("ActivityDate", "")))

                if rid == booking_id and rdate == activity_date:
                    # Write payment link
                    activity_sheet.update_cell(row_idx, payment_col, payment_link)
                    if confirmation:
                        # Also write confirmation
                        conf_col = None
                        for i, h in enumerate(headers):
                            if "confirmation" in str(h).lower():
                                conf_col = i + 1
                                break
                        if conf_col:
                            activity_sheet.update_cell(row_idx, conf_col, confirmation)

                    logger.info(f"📝 Wrote payment link to sheet: {booking_id} → {payment_link[:60]}...")
                    return True

            logger.warning(f"Row not found for booking {booking_id} on {activity_date}")
            return False

        except Exception as e:
            logger.error(f"Sheet write failed: {e}")
            return False

    # ── Notification ─────────────────────────────────────────────────

    def notify_admin(self, message: str, parse_mode: str = "Markdown"):
        """Send notification to admin Telegram."""
        for admin_id in ADMIN_IDS:
            aid = admin_id.strip()
            if not aid:
                continue
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                requests.post(url, json={
                    "chat_id": aid,
                    "text": message,
                    "parse_mode": parse_mode,
                }, timeout=10)
            except Exception:
                pass

    def notify_snipe_success(self, target: SnipeTarget, payment_link: str, hold_id: int):
        """Notify admin about successful auto-snipe."""
        msg = (
            f"🎉 *Auto-Snipe Success!*\n\n"
            f"📋 {target.product_title[:60]}\n"
            f"📅 {target.activity_date}\n"
            f"👥 {target.visitors} visitors\n"
            f"👤 {target.customer_name}\n"
            f"📧 {target.customer_email}\n"
            f"🔒 Hold #{hold_id}\n\n"
            f"💳 [Payment Link]({payment_link})\n\n"
            f"_Auto-sniped from CRM_"
        )
        self.notify_admin(msg)

    def notify_daily_digest(self):
        """Send daily summary of operations."""
        today = date.today()
        tomorrow = today + timedelta(days=1)

        # Scan for urgent targets
        targets = self.scan_crm_for_targets()
        urgent = [t for t in targets if t.days_until <= 3]
        upcoming = [t for t in targets if 3 < t.days_until <= 14]

        msg = f"📊 *Daily Digest — {today.strftime('%d %b %Y')}*\n\n"

        if urgent:
            msg += f"🔴 *Urgent (≤3 days): {len(urgent)}*\n"
            for t in urgent[:5]:
                msg += f"  • {t.activity_date} — {t.customer_name or '?'} ({t.visitors}v) — {t.product_title[:40]}\n"
            msg += "\n"

        if upcoming:
            msg += f"🟡 *Upcoming (4-14 days): {len(upcoming)}*\n"
            for t in upcoming[:5]:
                msg += f"  • {t.activity_date} — {t.customer_name or '?'} ({t.visitors}v)\n"
            msg += "\n"

        # Check for dispatched commands
        dispatched = [t for t in targets if t.status == "sniping"]
        if dispatched:
            msg += f"🚀 *Dispatched to Extension: {len(dispatched)}*\n"
            for t in dispatched[:5]:
                msg += f"  • {t.activity_date} — {t.customer_name or '?'} ({t.visitors}v)\n"

        if not urgent and not upcoming and not dispatched:
            msg += "✨ No pending targets."

        self.notify_admin(msg)

    # ── Main Loop ────────────────────────────────────────────────────

    def run_once(self):
        """Single cycle: scan CRM → find slots → create extension commands."""
        logger.info("🔄 Auto-snipe cycle starting...")

        # 1. Scan CRM for targets
        targets = self.scan_crm_for_targets()

        # 2. Filter: targets within 30 days, priority 1-5, not already sniping
        auto_targets = [
            t for t in targets
            if t.days_until <= 30 and t.priority <= 5 and t.status == "pending"
        ]

        # 3. For each target, check slots via API and create extension commands
        new_snipes = 0
        for target in auto_targets[:10]:  # Max 10 per cycle
            cmd_id = self.create_extension_snipe(target)
            if cmd_id:
                target.status = "sniping"
                new_snipes += 1

                # Notify admin for urgent bookings
                if target.priority <= 2:
                    self.notify_admin(
                        f"🎯 *Urgent Snipe Dispatched*\n\n"
                        f"📅 {target.activity_date}\n"
                        f"👥 {target.visitors} visitors\n"
                        f"👤 {target.customer_name}\n"
                        f"📋 {target.product_title[:60]}\n\n"
                        f"_Extension will book automatically_"
                    )
            time.sleep(1)  # Rate limit between slot checks

        if new_snipes:
            logger.info(f"⚡ Dispatched {new_snipes} extension booking commands")

        logger.info(f"✅ Auto-snipe cycle complete: {new_snipes} new commands dispatched")

    def run_loop(self, interval_seconds: int = 300):
        """Run continuously with given interval (default 5 min)."""
        self._running = True
        logger.info(f"🚀 CRM Auto-Snipe Service starting (interval: {interval_seconds}s)")

        while self._running:
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"Auto-snipe cycle error: {e}")

            # Sleep in chunks for clean shutdown
            for _ in range(interval_seconds):
                if not self._running:
                    break
                time.sleep(1)

    def stop(self):
        """Stop the service."""
        self._running = False
        logger.info("CRM Auto-Snipe Service stopped")


# ── Celery Task Wrapper ──────────────────────────────────────────────

def run_auto_snipe_cycle():
    """Celery task: run one auto-snipe cycle."""
    service = CRMAutoSnipeService()
    service.run_once()


def run_daily_digest():
    """Celery task: send daily digest to admin."""
    service = CRMAutoSnipeService()
    service.notify_daily_digest()


# Global instance
auto_snipe_service = CRMAutoSnipeService()
