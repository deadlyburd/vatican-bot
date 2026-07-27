import os
import logging
import json
from django.utils import timezone
from telegram import Bot
import asyncio
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)

class CustomerCareAgent:
    """
    Agent responsible for customer outreach and Human-in-the-Loop (HITL) communication.
    """

    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.admin_chat_id = os.getenv('ADMIN_TELEGRAM_IDS', '').split(',')[0]
        self.bot = Bot(token=self.bot_token) if self.bot_token else None

    async def send_missing_info_request(self, task):
        """
        Sends a request to the customer for missing information.
        Currently supports:
        1. Internal Log (Database)
        2. Admin Alert (Telegram)
        3. [WIP] Email (SMTP)
        """
        summary = task.missing_info or "Various details"
        
        # 1. Draft the message (AI-assisted style)
        message = (
            f"Dear {task.customer_name},\n\n"
            f"We are preparing your Vatican ticket booking (#{task.booking_id}), but we are missing some required information:\n"
            f"⚠️ {summary}\n\n"
            f"Please reply to this email with the missing details so we can finalize your reservation.\n\n"
            f"Thank you,\nVatican Booking Team"
        )

        # 2. Record the outreach in the log
        log_entry = {
            "timestamp": timezone.now().isoformat(),
            "action": "outreach_sent",
            "channel": "email_mock",
            "recipient": task.customer_email,
            "message_preview": message[:100] + "..."
        }
        
        if not task.contact_log:
            task.contact_log = []
        task.contact_log.append(log_entry)
        task.save(update_fields=['contact_log'])

        # 3. Notify Admin via Telegram
        if self.bot and self.admin_chat_id:
            try:
                admin_alert = (
                    f"📢 *Customer Outreach Sent*\n"
                    f"Task: #{task.id} ({task.booking_id})\n"
                    f"Customer: {task.customer_name}\n"
                    f"Reason: {summary}\n"
                    f"Status: Awaiting reply..."
                )
                await self.bot.send_message(
                    chat_id=self.admin_chat_id,
                    text=admin_alert,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send admin alert: {e}")

        logger.info(f"Outreach sent for Task #{task.id}")
        return True

# Singleton
_care_agent = None
def get_customer_care():
    global _care_agent
    if _care_agent is None:
        _care_agent = CustomerCareAgent()
    return _care_agent
