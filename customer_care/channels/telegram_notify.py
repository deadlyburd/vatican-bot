"""
Telegram Notification Helper
=============================
Sends admin notifications about support tickets, CRM alerts, etc.
Used by WhatsApp and Email channels to notify admins on Telegram.
"""

import os
import logging
import asyncio

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS = os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")


def _send_sync(chat_id: str, message: str) -> bool:
    """Send a Telegram message synchronously using requests."""
    import requests
    if not BOT_TOKEN:
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id.strip(),
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"Telegram notify failed: {e}")
        return False


def notify_admins(message: str) -> bool:
    """Send a notification to all admin Telegram IDs."""
    success = False
    for admin_id in ADMIN_IDS:
        if admin_id.strip():
            if _send_sync(admin_id.strip(), message):
                success = True
    return success


def notify_new_booking(booking_info: dict):
    """Notify admins about a new booking."""
    msg = (
        f"🎉 *New Booking Confirmed!*\n\n"
        f"📋 {booking_info.get('product', 'N/A')}\n"
        f"📅 {booking_info.get('date', 'N/A')} at {booking_info.get('time', 'N/A')}\n"
        f"👥 {booking_info.get('visitors', '?')} visitors\n"
        f"🎫 {booking_info.get('confirmation', 'N/A')}\n"
        f"💰 {booking_info.get('price', 'N/A')} EUR"
    )
    notify_admins(msg)


def notify_snipe_status(monitor_id: int, status: str, details: dict = None):
    """Notify admins about snipe status changes."""
    emoji = {"searching": "🔍", "found": "✅", "holding": "🔒", "booked": "🎉", "error": "❌"}.get(status, "📢")
    msg = f"{emoji} *Monitor #{monitor_id}: {status.upper()}*"
    if details:
        msg += f"\n\n```\n{details}\n```"
    notify_admins(msg)


def notify_crm_alert(alert_type: str, message: str):
    """Send CRM alert to admins."""
    msg = f"📊 *CRM Alert: {alert_type}*\n\n{message}"
    notify_admins(msg)
