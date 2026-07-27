"""
Customer Care Bot - Main Entry Point
======================================
Run the tourist care Telegram bot standalone or integrated with Django.
"""

import os
import sys
import logging
import django

# Setup Django if running from project root
if os.path.exists(os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'manage.py')):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    try:
        django.setup()
    except Exception:
        pass

from customer_care.bot.tourist_care_bot import TouristCareBot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run the customer care bot."""
    bot = TouristCareBot()

    # Check if webhook mode or polling mode
    webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL", "")

    if webhook_url:
        logger.info(f"Starting in webhook mode: {webhook_url}")
        import asyncio
        application = bot.get_application()
        asyncio.run(bot.run_webhook(application, webhook_url))
    else:
        logger.info("Starting in polling mode")
        bot.run()


if __name__ == "__main__":
    main()
