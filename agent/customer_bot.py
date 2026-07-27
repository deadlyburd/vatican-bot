"""
Customer-facing Telegram bot for tourist inquiries.

Features:
    /start  — welcome message with options
    /status — look up booking by ID, email, or name
    /help   — FAQ about Vatican tickets
    /contact — escalate to human admin
    Natural language queries — answered via Claude AI (if configured)

Run with:
    python -m agent.cli customer-bot
"""

import logging
from datetime import datetime
from typing import Optional

from agent.config import config
from agent.notifier import send_message, notify_admins
from agent.sheets import Booking, get_sheets

logger = logging.getLogger(__name__)

# Try to import python-telegram-bot
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        CallbackQueryHandler,
        ConversationHandler,
        ContextTypes,
        filters,
    )
    PTB_AVAILABLE = True
except ImportError:
    PTB_AVAILABLE = False
    logger.warning("python-telegram-bot not installed. Install with: pip install python-telegram-bot")


# ── Conversation States ─────────────────────────────────────────────────────

(
    MAIN_MENU,
    BOOKING_LOOKUP,
    SUPPORT_MESSAGE,
    GENERAL_CHAT,
) = range(4)


# ── Bot ─────────────────────────────────────────────────────────────────────

class CustomerBot:
    """Tourist-facing Telegram bot for booking inquiries."""

    def __init__(self):
        if not PTB_AVAILABLE:
            raise ImportError("python-telegram-bot is required. pip install python-telegram-bot")

        self.sheets = get_sheets()
        self.app: Application | None = None

        # FAQ responses (no AI needed for these)
        self.faq = {
            "dress code": "👗 There is a strict dress code at the Vatican: shoulders and knees must be covered. No shorts, miniskirts, or sleeveless tops.",
            "transport": "🚇 The closest metro stop is Ottaviano (Line A). Buses 49, 32, 81, and 982 also stop near the museums.",
            "food": "🍕 There's a cafeteria inside the museums and many restaurants in the surrounding Prati neighborhood.",
            "photo": "📸 Photography is allowed in most areas (no flash). No photos in the Sistine Chapel.",
            "bag": "🎒 Large bags and backpacks must be checked at the cloakroom. Small bags are fine.",
            "wheelchair": "♿ The Vatican Museums are wheelchair accessible. Free admission for visitors with disabilities and their companion.",
            "ticket": "🎫 Standard entry is €17 + €4 booking fee. Reduced tickets (€8) for ages 6-18 and students under 26 with ID.",
            "hours": "🕐 Open Monday-Saturday 9:00-18:00 (last entry 16:00). Closed Sundays except the last Sunday of each month (free entry, 9:00-14:00).",
            "booking": "📅 Tickets are released 60 days in advance and sell out quickly. We recommend booking as early as possible.",
        }

    # ── Command Handlers ─────────────────────────────────────────────────

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        keyboard = [
            [InlineKeyboardButton("🔍 Check Booking Status", callback_data="lookup")],
            [InlineKeyboardButton("ℹ️ Vatican Info & FAQ", callback_data="faq")],
            [InlineKeyboardButton("📞 Contact Support", callback_data="support")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"🇻🇦 *Benvenuti! Welcome to {config.bot_name}*\n\n"
            f"I can help you with:\n"
            f"• Checking your Vatican ticket booking status\n"
            f"• Answering questions about visiting the Vatican\n"
            f"• Contacting our support team\n\n"
            f"Choose an option below or just type your question!",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
        return MAIN_MENU

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        text = "📖 *Help*\n\n"
        text += "*Commands:*\n"
        text += "/start — Main menu\n"
        text += "/status — Check booking status\n"
        text += "/help — This help message\n"
        text += "/contact — Reach our support team\n\n"
        text += "*Frequently Asked:*\n"
        for topic in self.faq:
            text += f"• {topic.title()}\n"
        text += "\nJust type your question — I'll do my best to answer!"

        await update.message.reply_text(text, parse_mode="Markdown")
        return MAIN_MENU

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status — look up booking."""
        await update.message.reply_text(
            "🔍 *Booking Lookup*\n\n"
            "Please send me your:\n"
            "• Booking ID, or\n"
            "• Email address, or\n"
            "• Full name\n\n"
            "I'll check our system for your booking status.",
            parse_mode="Markdown",
        )
        return BOOKING_LOOKUP

    async def contact_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /contact — escalate to admin."""
        await update.message.reply_text(
            "📞 *Contact Support*\n\n"
            "Please describe your issue and we'll get back to you.\n"
            "You can also email us directly.",
            parse_mode="Markdown",
        )
        return SUPPORT_MESSAGE

    # ── Callback Handlers ────────────────────────────────────────────────

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button presses."""
        query = update.callback_query
        await query.answer()
        data = query.data

        if data == "lookup":
            await query.edit_message_text(
                "🔍 *Booking Lookup*\n\n"
                "Send me your Booking ID, email address, or full name, "
                "and I'll check your booking status.",
                parse_mode="Markdown",
            )
            return BOOKING_LOOKUP

        elif data == "faq":
            faq_text = "ℹ️ *Frequently Asked Questions*\n\n"
            for topic, answer in self.faq.items():
                faq_text += f"*{topic.title()}*: {answer[:100]}...\n\n"
            keyboard = [[InlineKeyboardButton("« Back", callback_data="back")]]
            await query.edit_message_text(
                faq_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return MAIN_MENU

        elif data == "support":
            await query.edit_message_text(
                "📞 *Contact Support*\n\n"
                "Please describe your issue below and our team will help you.",
                parse_mode="Markdown",
            )
            return SUPPORT_MESSAGE

        elif data == "back":
            return await self._show_main_menu(query)

    # ── Message Handlers ─────────────────────────────────────────────────

    async def handle_booking_lookup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Search for booking by ID, email, or name."""
        query_text = update.message.text.strip()

        # Try booking ID first
        booking = self.sheets.lookup_booking(query_text)
        if booking:
            return await self._show_booking(update, booking)

        # Try email
        if "@" in query_text:
            bookings = self.sheets.lookup_by_email(query_text)
            if bookings:
                return await self._show_booking_list(update, bookings)

        await update.message.reply_text(
            "❌ *Booking Not Found*\n\n"
            f"I couldn't find a booking matching '{query_text}'.\n\n"
            "Please check the ID/email and try again, or type /contact for support.",
            parse_mode="Markdown",
        )
        return MAIN_MENU

    async def handle_support_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Forward support request to admin."""
        user = update.message.from_user
        msg = update.message.text

        # Notify admins
        admin_text = (
            f"📞 *Support Request*\n\n"
            f"*From:* {user.first_name} {user.last_name or ''}\n"
            f"*Username:* @{user.username or 'N/A'}\n"
            f"*User ID:* `{user.id}`\n\n"
            f"*Message:*\n{msg}"
        )
        notify_admins(admin_text)

        await update.message.reply_text(
            "✅ *Message Sent!*\n\n"
            "Our support team has been notified and will get back to you soon.\n\n"
            "You can also reach us directly via email.",
            parse_mode="Markdown",
        )
        return MAIN_MENU

    async def handle_free_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle natural language queries — check FAQ first, then use Claude if available."""
        query = update.message.text.strip().lower()

        # Check FAQ keywords
        for keyword, answer in self.faq.items():
            if keyword in query:
                await update.message.reply_text(answer)
                return MAIN_MENU

        # Try Claude if configured
        if config.anthropic_api_key:
            try:
                reply = self._ask_claude(query)
                await update.message.reply_text(reply, parse_mode="Markdown")
            except Exception as e:
                logger.error("Claude query failed: %s", e)
                await update.message.reply_text(
                    "I'm not sure about that. Try /help for common questions, "
                    "or /contact to reach our support team.",
                )
        else:
            await update.message.reply_text(
                "I'm not sure about that. Try:\n"
                "• /help for common questions\n"
                "• /status to check your booking\n"
                "• /contact for support",
            )

        return MAIN_MENU

    # ── Helpers ──────────────────────────────────────────────────────────

    async def _show_booking(self, update: Update, booking: Booking):
        """Display a single booking's status."""
        status_emoji = "✅" if booking.has_payment_link else "⏳"
        text = (
            f"{status_emoji} *Booking Status*\n\n"
            f"📅 *Date:* {booking.date}\n"
            f"🕐 *Time:* {booking.time}\n"
            f"🎫 *Product:* {booking.product}\n"
            f"👤 *Name:* {booking.first_name} {booking.last_name}\n"
            f"📦 *ID:* `{booking.booking_id}`\n"
            f"📊 *Status:* {booking.status or 'Pending'}\n"
        )
        if booking.has_payment_link:
            text += f"\n💳 *Payment Link:*\n`{booking.payment_link}`"
        else:
            text += "\n⏳ Your tickets are being processed. We'll send the payment link once booked."

        await update.message.reply_text(text, parse_mode="Markdown")
        return MAIN_MENU

    async def _show_booking_list(self, update: Update, bookings: list[Booking]):
        """Display a list of bookings for an email."""
        text = f"📋 *Found {len(bookings)} booking(s)*\n\n"
        for b in bookings[:5]:
            status = "✅" if b.has_payment_link else "⏳"
            text += f"{status} {b.date} — {b.product} ({b.first_name} {b.last_name})\n"

        if len(bookings) > 5:
            text += f"\n... and {len(bookings) - 5} more."

        text += "\nReply with a Booking ID for details."
        await update.message.reply_text(text, parse_mode="Markdown")
        return MAIN_MENU

    async def _show_main_menu(self, query):
        """Return to main menu."""
        keyboard = [
            [InlineKeyboardButton("🔍 Check Booking Status", callback_data="lookup")],
            [InlineKeyboardButton("ℹ️ Vatican Info & FAQ", callback_data="faq")],
            [InlineKeyboardButton("📞 Contact Support", callback_data="support")],
        ]
        await query.edit_message_text(
            "🇻🇦 *Main Menu*\nWhat can I help you with?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return MAIN_MENU

    def _ask_claude(self, query: str) -> str:
        """Query Claude for a helpful response about the Vatican."""
        import anthropic

        client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=(
                "You are Roma Assistant, a helpful Vatican Museums concierge. "
                "Answer tourist questions about visiting the Vatican: tickets, dress code, "
                "hours, transportation, accessibility, and general tips. "
                "Keep answers concise (2-3 sentences max). Be friendly and helpful. "
                "If you don't know something, suggest contacting support."
            ),
            messages=[{"role": "user", "content": query}],
        )
        return message.content[0].text

    # ── Run ──────────────────────────────────────────────────────────────

    def build_app(self) -> Application:
        """Build the Telegram application with all handlers."""
        app = Application.builder().token(config.telegram_bot_token).build()

        # Conversation handler
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("start", self.start),
                CommandHandler("help", self.help_command),
                CommandHandler("status", self.status_command),
                CommandHandler("contact", self.contact_command),
            ],
            states={
                MAIN_MENU: [
                    CallbackQueryHandler(self.handle_callback),
                    CommandHandler("start", self.start),
                    CommandHandler("help", self.help_command),
                    CommandHandler("status", self.status_command),
                    CommandHandler("contact", self.contact_command),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_free_text),
                ],
                BOOKING_LOOKUP: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_booking_lookup),
                    CommandHandler("start", self.start),
                ],
                SUPPORT_MESSAGE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_support_message),
                    CommandHandler("start", self.start),
                ],
            },
            fallbacks=[CommandHandler("start", self.start)],
        )

        app.add_handler(conv_handler)
        return app

    def run_polling(self):
        """Run the bot with polling (for development)."""
        logger.info("Starting customer bot in polling mode...")
        self.app = self.build_app()
        self.app.run_polling()

    async def run_webhook(self, webhook_url: str):
        """Run the bot with webhook (for production)."""
        logger.info("Starting customer bot in webhook mode: %s", webhook_url)
        self.app = self.build_app()
        await self.app.initialize()
        await self.app.bot.set_webhook(webhook_url)
        # The app needs to be served via a web framework (FastAPI, Flask, etc.)
        # For docker-compose, we use polling mode by default
        logger.info("Webhook set. Use a web framework to serve the app.")


# ── Entry point ─────────────────────────────────────────────────────────────

def main():
    """Run the customer bot."""
    bot = CustomerBot()
    bot.run_polling()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
