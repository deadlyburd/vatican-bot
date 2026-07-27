"""
Django Management Command: run_customer_care_bot
=================================================
Runs the tourist customer care Telegram bot.
Integrates with Django for CRM data access.

Usage:
    python manage.py run_customer_care_bot
"""

import os
import logging
import asyncio

from django.core.management.base import BaseCommand
from django.conf import settings

from customer_care.bot.tourist_care_bot import TouristCareBot
from crm_intelligence.sync.crm_sync import crm_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run the tourist customer care Telegram bot'

    def add_arguments(self, parser):
        parser.add_argument(
            '--webhook',
            action='store_true',
            help='Run in webhook mode instead of polling',
        )
        parser.add_argument(
            '--no-crm',
            action='store_true',
            help='Skip CRM data loading',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🏛️ Starting Roma Assistant - Customer Care Bot'))

        # Initialize CRM sync
        if not options['no_crm']:
            try:
                sheet_id = os.getenv('GOOGLE_SHEET_ID', '1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg')
                creds_file = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE', 'google_credentials.json')

                crm_service.initialize(
                    sheet_id=sheet_id,
                    credentials_file=creds_file,
                    refresh_interval=300,
                )
                self.stdout.write(self.style.SUCCESS('✅ CRM sync initialized'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️ CRM init failed: {e}'))
                self.stdout.write(self.style.WARNING('Bot will run without CRM data'))

        # Create and run bot
        bot = TouristCareBot()

        if options['webhook']:
            webhook_url = os.getenv('TELEGRAM_WEBHOOK_URL', '')
            if not webhook_url:
                self.stdout.write(self.style.ERROR('TELEGRAM_WEBHOOK_URL not set'))
                return
            self.stdout.write(self.style.SUCCESS(f'Running in webhook mode: {webhook_url}'))
            application = bot.get_application()
            asyncio.run(bot.run_webhook(application, webhook_url))
        else:
            self.stdout.write(self.style.SUCCESS('Running in polling mode'))
            self.stdout.write(self.style.SUCCESS('Bot is ready! Send /start to @RomaAssistantBot'))
            bot.run()
