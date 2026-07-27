"""
Telegram notifications for admin alerts and booking confirmations.

Sends formatted Markdown messages to admin Telegram chat(s).
Uses the Telegram Bot API directly via HTTP — no framework needed.
"""

import logging
from datetime import datetime
from typing import List

import requests

from agent.config import config

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


# ── Core Send ───────────────────────────────────────────────────────────────

def send_message(chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
    """
    Send a Telegram message to a specific chat ID.

    Returns True on success, False on failure.
    """
    url = f"{TELEGRAM_API}/bot{config.telegram_bot_token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return True
        logger.error("Telegram send failed: %d %s", resp.status_code, resp.text[:200])
        return False
    except requests.RequestException as e:
        logger.error("Telegram send error: %s", e)
        return False


def notify_admins(text: str, parse_mode: str = "Markdown") -> bool:
    """Send a message to all configured admin Telegram IDs."""
    if not config.admin_telegram_ids:
        logger.warning("No admin Telegram IDs configured — notification skipped")
        return False

    success = True
    for admin_id in config.admin_telegram_ids:
        if not send_message(admin_id, text, parse_mode):
            success = False
    return success


# ── Formatted Notifications ─────────────────────────────────────────────────

def notify_booking_success(
    date: str,
    time: str,
    first_name: str,
    last_name: str,
    visitors: int,
    epay_url: str,
    booking_id: str = "",
) -> bool:
    """Send a booking success notification to admins."""
    now = datetime.now().strftime("%H:%M:%S")
    text = (
        f"🎫 *Booking Complete!*\n\n"
        f"📅 *Date:* {date}\n"
        f"🕐 *Time:* {time}\n"
        f"👤 *Customer:* {first_name} {last_name}\n"
        f"👥 *Visitors:* {visitors}\n"
        f"📦 *Booking ID:* `{booking_id}`\n\n"
        f"💳 *Payment Link:*\n`{epay_url}`\n\n"
        f"🕒 _{now}_"
    )
    return notify_admins(text)


def notify_booking_failed(
    date: str,
    time: str,
    first_name: str,
    last_name: str,
    error: str,
) -> bool:
    """Send a booking failure notification."""
    now = datetime.now().strftime("%H:%M:%S")
    text = (
        f"❌ *Booking Failed*\n\n"
        f"📅 {date} at {time}\n"
        f"👤 {first_name} {last_name}\n\n"
        f"*Error:* {error}\n\n"
        f"🕒 _{now}_"
    )
    return notify_admins(text)


def notify_no_slots(
    date: str,
    first_name: str,
    last_name: str,
    visitors: int,
) -> bool:
    """Notify admins that no slots were found for a booking."""
    text = (
        f"🔍 *No Slots Found*\n\n"
        f"📅 {date}\n"
        f"👤 {first_name} {last_name}\n"
        f"👥 {visitors} visitors\n\n"
        f"Will retry on next pipeline cycle."
    )
    return notify_admins(text)


def notify_pipeline_summary(
    total_checked: int,
    booked: int,
    no_slots: int,
    failed: int,
    errors: List[str] | None = None,
) -> bool:
    """Send a pipeline cycle summary to admins."""
    now = datetime.now().strftime("%H:%M:%S")
    text = (
        f"📊 *Pipeline Cycle Complete*\n\n"
        f"🔍 Checked: {total_checked}\n"
        f"✅ Booked: {booked}\n"
        f"🔎 No slots: {no_slots}\n"
        f"❌ Failed: {failed}\n"
    )
    if errors:
        text += f"\n⚠️ Errors:\n"
        for e in errors[:5]:
            text += f"  • {e[:100]}\n"
    text += f"\n🕒 _{now}_"
    return notify_admins(text)


def notify_startup() -> bool:
    """Send a startup notification — confirms the bot is running."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = (
        f"🤖 *Vatican Bot Started*\n\n"
        f"Pipeline is running.\n"
        f"Checking every {config.pipeline_interval_seconds // 60} minutes.\n\n"
        f"🕒 _{now}_"
    )
    return notify_admins(text)


def notify_error(context: str, error: str) -> bool:
    """Send a generic error notification."""
    now = datetime.now().strftime("%H:%M:%S")
    text = (
        f"⚠️ *Error*\n\n"
        f"*Context:* {context}\n"
        f"*Error:* {error}\n\n"
        f"🕒 _{now}_"
    )
    return notify_admins(text)
