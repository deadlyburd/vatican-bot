"""
Tourist Customer Care Telegram Bot
====================================
A full-featured Telegram bot for tourists visiting Rome and Italy.
Handles booking lookups, modifications, cancellations, FAQs,
and provides personalized recommendations.

Uses AI (Claude) for natural conversation and CRM data for personalization.
"""

import os
import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, date
from datetime import timezone as dt_timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
from telegram.constants import ParseMode

from customer_care.config.bot_config import config
from crm_intelligence.parsers.sheet_parser import SheetParser
from crm_intelligence.ai.crm_analyzer import CRMAnalyzer

logger = logging.getLogger(__name__)

# Conversation states
(
    STATE_MAIN_MENU,
    STATE_BOOKING_LOOKUP,
    STATE_BOOKING_ACTION,
    STATE_SUPPORT_TOPIC,
    STATE_SUPPORT_MESSAGE,
    STATE_CANCEL_CONFIRM,
    STATE_GENERAL_CHAT,
    STATE_LANGUAGE_SELECT,
) = range(8)

# Language support
LANGUAGES = {
    "en": "English",
    "it": "Italiano",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "pt": "Português",
    "zh": "中文",
    "ja": "日本語",
}

# Translations for common phrases
I18N = {
    "en": {
        "welcome": "🏛️ Welcome to Roma Assistant!\n\nI'm here to help you with your Rome and Vatican bookings. What can I do for you today?",
        "menu_bookings": "📋 My Bookings",
        "menu_support": "💬 Get Support",
        "menu_info": "ℹ️ Rome Info",
        "menu_language": "🌐 Language",
        "menu_help": "❓ Help",
        "enter_email": "📧 Please enter your email address to look up your bookings:",
        "booking_found": "✅ Found {count} booking(s) for {name}:",
        "booking_not_found": "❌ No bookings found for this email. Please check and try again.",
        "select_booking": "Select a booking to view details or take action:",
        "booking_details": "📋 Booking Details\n\n{product}\n📅 Date: {date}\n⏰ Time: {time}\n👥 Participants: {participants}\n📊 Status: {status}\n🎫 Confirmation: {confirmation}",
        "action_cancel": "❌ Cancel Booking",
        "action_modify": "✏️ Modify Booking",
        "action_receipt": "🧾 Get Receipt",
        "action_back": "⬅️ Back",
        "cancel_confirm": "⚠️ Are you sure you want to cancel booking {confirmation}?\n\n{product}\n📅 {date} at {time}\n\nThis action cannot be undone.",
        "cancel_success": "✅ Booking {confirmation} has been cancelled. You should receive a confirmation email shortly.",
        "cancel_failed": "❌ Unable to cancel booking. Please contact support.",
        "support_prompt": "What do you need help with?\n\nChoose a topic or just type your question:",
        "support_ticket_created": "✅ Support ticket created!\n\nTicket: #{ticket_id}\n\nOur team will respond within 2 hours during business hours (9:00-18:00 Rome time).",
        "rome_info": "🏛️ Rome Tourist Information\n\nWhat would you like to know about?",
        "unknown_command": "I didn't understand that. Try /help to see what I can do.",
        "language_select": "🌐 Select your language / Seleziona la tua lingua:",
        "language_changed": "✅ Language changed to English!",
        "goodbye": "👋 Arrivederci! Have a wonderful time in Rome!",
        "help_text": "🏛️ *Roma Assistant - Help*\n\n*Commands:*\n/start - Main menu\n/bookings - View your bookings\n/support - Get help\n/info - Rome tourist info\n/language - Change language\n/help - Show this help\n\n*I can help you with:*\n• 📋 View booking details\n• ❌ Cancel bookings\n• ✏️ Modify bookings\n• 🧾 Get receipts\n• 💬 Answer questions about Rome\n• 🏛️ Vatican dress code & tips\n• 🚇 Transport information\n• 🍝 Restaurant recommendations\n\n*During business hours (9-18 Rome time):*\nOur team typically responds within 15 minutes\n\n*Emergency:* Call +39 06 6988 (Vatican info)",
    },
    "it": {
        "welcome": "🏛️ Benvenuto su Roma Assistant!\n\nSono qui per aiutarti con le tue prenotazioni a Roma e Vaticano. Cosa posso fare per te?",
        "menu_bookings": "📋 Le Mie Prenotazioni",
        "menu_support": "💬 Assistenza",
        "menu_info": "ℹ️ Info Roma",
        "menu_language": "🌐 Lingua",
        "menu_help": "❓ Aiuto",
        "enter_email": "📧 Inserisci la tua email per cercare le prenotazioni:",
        "booking_found": "✅ Trovate {count} prenotazione/i per {name}:",
        "booking_not_found": "❌ Nessuna prenotazione trovata. Riprova.",
        "select_booking": "Seleziona una prenotazione:",
        "booking_details": "📋 Dettagli Prenotazione\n\n{product}\n📅 Data: {date}\n⏰ Ora: {time}\n👥 Partecipanti: {participants}\n📊 Stato: {status}\n🎫 Conferma: {confirmation}",
        "action_cancel": "❌ Cancella",
        "action_modify": "✏️ Modifica",
        "action_receipt": "🧾 Ricevuta",
        "action_back": "⬅️ Indietro",
        "cancel_confirm": "⚠️ Sicuro di voler cancellare {confirmation}?\n\n{product}\n📅 {date} alle {time}",
        "cancel_success": "✅ Prenotazione cancellata. Riceverai una conferma via email.",
        "cancel_failed": "❌ Impossibile cancellare. Contatta l'assistenza.",
        "support_prompt": "Di cosa hai bisogno?",
        "support_ticket_created": "✅ Ticket creato! #{ticket_id}\n\nRisponderemo entro 2 ore (orario 9-18 Roma).",
        "rome_info": "🏛️ Informazioni Turistiche Roma",
        "unknown_command": "Non ho capito. Prova /help per vedere cosa posso fare.",
        "language_select": "🌐 Seleziona la tua lingua:",
        "language_changed": "✅ Lingua cambiata in Italiano!",
        "goodbye": "👋 Arrivederci! Buon soggiorno a Roma!",
        "help_text": "🏛️ *Roma Assistant - Aiuto*\n\n*Comandi:*\n/start - Menu principale\n/bookings - Le mie prenotazioni\n/support - Assistenza\n/info - Info Roma\n/language - Lingua\n/help - Aiuto",
    },
}


class TouristCareBot:
    """Main customer care bot for tourists."""

    def __init__(self):
        self.config = config
        self.parser = SheetParser(
            sheet_id=config.crm.sheet_id,
            credentials_file=config.crm.service_account_file
        )
        self.analyzer = None
        self._crm_loaded = False
        self._user_languages: Dict[int, str] = {}  # chat_id -> lang

    def _t(self, key: str, lang: str = "en") -> str:
        """Get translated string."""
        lang_dict = I18N.get(lang, I18N["en"])
        return lang_dict.get(key, I18N["en"].get(key, key))

    def _get_lang(self, update: Update) -> str:
        """Get user's language preference."""
        chat_id = update.effective_chat.id
        return self._user_languages.get(chat_id, "en")

    def _ensure_crm_loaded(self):
        """Lazy-load CRM data."""
        if self._crm_loaded:
            return
        try:
            self.parser.connect()
            bookings = self.parser.parse_bookings(limit=200)
            activities = self.parser.parse_activity_lines(limit=500)
            passengers = self.parser.parse_passengers(limit=1000)
            products = self.parser.parse_products()

            # Convert to dicts for analyzer
            bookings_dict = [
                {
                    "bookingId": b.booking_id,
                    "customerEmail": b.customer.email if b.customer else "",
                    "customerFirstName": b.customer.first_name if b.customer else "",
                    "customerLastName": b.customer.last_name if b.customer else "",
                    "status": b.status.value,
                    "channelTitle": b.channel_title.value if hasattr(b.channel_title, 'value') else str(b.channel_title),
                    "paymentType": b.payment_type,
                }
                for b in bookings
            ]
            activities_dict = [
                {
                    "bookingId": a.booking_id,
                    "productTitle": a.product_title,
                    "activityDate": a.activity_date,
                    "startTime": a.startTime,
                    "totalParticipants": a.total_participants,
                    "status": a.status,
                    "productConfirmationCode": a.product_confirmation_code,
                }
                for a in activities
            ]

            self.analyzer = CRMAnalyzer(bookings_dict, activities_dict, [], [])
            self._crm_loaded = True
            logger.info(f"CRM loaded: {len(bookings)} bookings, {len(activities)} activities, {len(products)} products")
        except Exception as e:
            logger.error(f"Failed to load CRM: {e}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        lang = self._get_lang(update)
        user = update.effective_user

        # Check if returning user (Telegram doesn't provide email, so CRM lookup by name/username)
        self._ensure_crm_loaded()
        if self.analyzer:
            try:
                info = self.analyzer.get_useful_info_for_bot("")
            except Exception:
                info = {"found": False}
            if info.get("found"):
                welcome_text = f"🏛️ Welcome back, {info['name']}!\n\n"
                if info.get("is_vip"):
                    welcome_text += "💎 Thank you for being a valued customer!\n\n"
                if info.get("upcoming_bookings"):
                    welcome_text += f"📋 You have {len(info['upcoming_bookings'])} upcoming booking(s).\n\n"
                welcome_text += "What can I help you with today?"
            else:
                welcome_text = self._t("welcome", lang)
        else:
            welcome_text = self._t("welcome", lang)

        keyboard = [
            [InlineKeyboardButton(self._t("menu_bookings", lang), callback_data="menu_bookings")],
            [InlineKeyboardButton(self._t("menu_support", lang), callback_data="menu_support")],
            [InlineKeyboardButton(self._t("menu_info", lang), callback_data="menu_info")],
            [
                InlineKeyboardButton(self._t("menu_language", lang), callback_data="menu_language"),
                InlineKeyboardButton(self._t("menu_help", lang), callback_data="menu_help"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        return STATE_MAIN_MENU

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        lang = self._get_lang(update)
        await update.message.reply_text(
            self._t("help_text", lang),
            parse_mode=ParseMode.MARKDOWN
        )

    async def bookings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /bookings command - direct to booking lookup."""
        lang = self._get_lang(update)
        await update.message.reply_text(self._t("enter_email", lang))
        return STATE_BOOKING_LOOKUP

    async def support_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /support command."""
        lang = self._get_lang(update)
        keyboard = [
            [InlineKeyboardButton("🎫 Ticket Issue", callback_data="support_ticket")],
            [InlineKeyboardButton("❌ Cancellation", callback_data="support_cancel")],
            [InlineKeyboardButton("💰 Refund", callback_data="support_refund")],
            [InlineKeyboardButton("📍 Meeting Point", callback_data="support_meeting")],
            [InlineKeyboardButton("👗 Dress Code", callback_data="support_dresscode")],
            [InlineKeyboardButton("❓ Other Question", callback_data="support_other")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            self._t("support_prompt", lang),
            reply_markup=reply_markup
        )
        return STATE_SUPPORT_TOPIC

    async def info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /info command - Rome tourist info."""
        lang = self._get_lang(update)
        keyboard = [
            [InlineKeyboardButton("🏛️ Vatican Museums", callback_data="info_vatican")],
            [InlineKeyboardButton("🏟️ Colosseum", callback_data="info_colosseum")],
            [InlineKeyboardButton("🚇 Transport", callback_data="info_transport")],
            [InlineKeyboardButton("🍝 Food & Dining", callback_data="info_food")],
            [InlineKeyboardButton("🌤️ Weather", callback_data="info_weather")],
            [InlineKeyboardButton("🏨 Hotels & Areas", callback_data="info_hotels")],
            [InlineKeyboardButton("💡 Tips & Tricks", callback_data="info_tips")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            self._t("rome_info", lang),
            reply_markup=reply_markup
        )

    async def language_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /language command."""
        lang = self._get_lang(update)
        keyboard = [
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton("🇮🇹 Italiano", callback_data="lang_it")],
            [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
            [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
            [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            self._t("language_select", lang),
            reply_markup=reply_markup
        )
        return STATE_LANGUAGE_SELECT

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks."""
        query = update.callback_query
        await query.answer()
        lang = self._get_lang(update)
        data = query.data

        if data == "menu_bookings":
            await query.edit_message_text(self._t("enter_email", lang))
            return STATE_BOOKING_LOOKUP

        elif data == "menu_support":
            keyboard = [
                [InlineKeyboardButton("🎫 Ticket Issue", callback_data="support_ticket")],
                [InlineKeyboardButton("❌ Cancellation", callback_data="support_cancel")],
                [InlineKeyboardButton("💰 Refund", callback_data="support_refund")],
                [InlineKeyboardButton("📍 Meeting Point", callback_data="support_meeting")],
                [InlineKeyboardButton("👗 Dress Code", callback_data="support_dresscode")],
                [InlineKeyboardButton("❓ Other Question", callback_data="support_other")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(self._t("support_prompt", lang), reply_markup=reply_markup)
            return STATE_SUPPORT_TOPIC

        elif data == "menu_info":
            await self.info_command(update, context)
            return STATE_MAIN_MENU

        elif data == "menu_language":
            keyboard = [
                [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
                [InlineKeyboardButton("🇮🇹 Italiano", callback_data="lang_it")],
                [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
                [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(self._t("language_select", lang), reply_markup=reply_markup)
            return STATE_LANGUAGE_SELECT

        elif data == "menu_help":
            await query.edit_message_text(
                self._t("help_text", lang),
                parse_mode=ParseMode.MARKDOWN
            )
            return STATE_MAIN_MENU

        elif data.startswith("lang_"):
            new_lang = data.replace("lang_", "")
            self._user_languages[update.effective_chat.id] = new_lang
            await query.edit_message_text(
                self._t("language_changed", new_lang),
                reply_markup=None
            )
            # Show main menu in new language
            keyboard = [
                [InlineKeyboardButton(self._t("menu_bookings", new_lang), callback_data="menu_bookings")],
                [InlineKeyboardButton(self._t("menu_support", new_lang), callback_data="menu_support")],
                [InlineKeyboardButton(self._t("menu_info", new_lang), callback_data="menu_info")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=self._t("welcome", new_lang),
                reply_markup=reply_markup
            )
            return STATE_MAIN_MENU

        elif data == "support_dresscode":
            facts = config.tourist_context.rome_facts
            text = f"👗 *Vatican Dress Code*\n\n{facts['vatican_dress_code']}\n\n"
            text += "💡 *Tip:* Carry a scarf or light shawl in your bag. "
            text += "If you're wearing shorts, you'll be denied entry.\n\n"
            text += f"🌅 *Best Time:* {facts['vatican_best_time']}"
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
            return STATE_MAIN_MENU

        elif data == "support_ticket":
            await query.edit_message_text(
                "🎫 Please describe your ticket issue.\n\n"
                "Include:\n"
                "• Your confirmation code\n"
                "• The problem you're experiencing\n"
                "• Any error messages\n\n"
                "Type your message below:",
            )
            return STATE_SUPPORT_MESSAGE

        elif data == "action_back":
            return await self.start(update, context)

        # Unknown callback
        await query.edit_message_text(self._t("unknown_command", lang))
        return STATE_MAIN_MENU

    async def handle_email_lookup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle email input for booking lookup."""
        lang = self._get_lang(update)
        email = update.message.text.strip().lower()

        if "@" not in email:
            await update.message.reply_text("❌ Please enter a valid email address.")
            return STATE_BOOKING_LOOKUP

        self._ensure_crm_loaded()

        if not self.analyzer:
            await update.message.reply_text("⚠️ System temporarily unavailable. Please try again later.")
            return STATE_MAIN_MENU

        # Look up customer info
        info = self.analyzer.get_useful_info_for_bot(email)

        if not info.get("found") or not info.get("upcoming_bookings"):
            # Try to find any booking
            customer = self.parser.get_customer_by_email(email)
            if not customer:
                await update.message.reply_text(
                    self._t("booking_not_found", lang) + "\n\n" +
                    "💡 *Tip:* Make sure you use the same email from your booking confirmation.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return STATE_BOOKING_LOOKUP

            # Found customer but no upcoming
            await update.message.reply_text(
                f"👋 Hello {customer['first_name']}! We found your account but no upcoming bookings.\n\n"
                f"If you have a booking issue, please use /support to contact us.",
            )
            return STATE_MAIN_MENU

        # Show upcoming bookings
        bookings = info["upcoming_bookings"]
        text = self._t("booking_found", lang).format(count=len(bookings), name=info["name"]) + "\n\n"

        if info.get("is_vip"):
            text += "💎 VIP Customer\n\n"

        keyboard = []
        for i, b in enumerate(bookings[:10]):
            vatican_emoji = "🏛️" if b.get("is_vatican") else "🏟️" if b.get("is_colosseum") else "🎫"
            text += f"{i+1}. {vatican_emoji} {b['date']} at {b['time']} ({b['participants']} pax)\n"
            text += f"   _{b['product'][:60]}_\n\n"
            keyboard.append([InlineKeyboardButton(
                f"{vatican_emoji} {b['date']} {b['time']}",
                callback_data=f"booking_{b['confirmation']}"
            )])

        keyboard.append([InlineKeyboardButton(self._t("action_back", lang), callback_data="action_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return STATE_BOOKING_ACTION

    async def handle_support_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle support message from user."""
        lang = self._get_lang(update)
        message = update.message.text
        user = update.effective_user

        # Create ticket ID
        ticket_id = f"TKT-{datetime.now().strftime('%Y%m%d')}-{user.id % 10000:04d}"

        # Log the ticket
        logger.info(f"Support ticket {ticket_id} from {user.first_name} ({user.id}): {message[:200]}")

        # Notify admin
        try:
            admin_text = (
                f"🎫 *New Support Ticket*\n\n"
                f"Ticket: #{ticket_id}\n"
                f"From: {user.first_name} {user.last_name or ''}\n"
                f"Username: @{user.username or 'N/A'}\n"
                f"Chat ID: {user.id}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC\n\n"
                f"Message:\n{message}"
            )
            for admin_id in config.channels.admin_telegram_ids:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=admin_text,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")

        await update.message.reply_text(
            self._t("support_ticket_created", lang).format(ticket_id=ticket_id),
            parse_mode=ParseMode.MARKDOWN
        )
        return STATE_MAIN_MENU

    async def handle_free_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle free text messages — AI-powered responses."""
        lang = self._get_lang(update)
        text = update.message.text.lower()

        # Simple keyword-based responses (can be enhanced with AI)
        if any(word in text for word in ["hello", "hi", "ciao", "buongiorno", "hey"]):
            await update.message.reply_text(self._t("welcome", lang))
            return STATE_MAIN_MENU

        if any(word in text for word in ["dress code", "what to wear", "clothing"]):
            facts = config.tourist_context.rome_facts
            await update.message.reply_text(
                f"👗 *Vatican Dress Code*\n\n{facts['vatican_dress_code']}\n\n"
                f"💡 Carry a scarf as backup!",
                parse_mode=ParseMode.MARKDOWN
            )
            return STATE_MAIN_MENU

        if any(word in text for word in ["transport", "metro", "bus", "how to get"]):
            facts = config.tourist_context.rome_facts
            await update.message.reply_text(
                f"🚇 *Rome Transport*\n\n{facts['rome_transport']}\n\n"
                f"Download the 'Moovit' app for real-time transit info.",
                parse_mode=ParseMode.MARKDOWN
            )
            return STATE_MAIN_MENU

        if any(word in text for word in ["weather", "temperature", "rain", "sun"]):
            await update.message.reply_text(
                "🌤️ *Rome Weather*\n\n"
                "I can't check live weather yet, but here are general tips:\n\n"
                "☀️ *Jun-Aug:* Hot (30-35°C). Bring water, hat, sunscreen.\n"
                "🌸 *Apr-May, Sep-Oct:* Best weather (20-25°C).\n"
                "🌧️ *Nov-Mar:* Cool (8-15°C). Bring a jacket.\n\n"
                "Check weather.com for the latest forecast!",
                parse_mode=ParseMode.MARKDOWN
            )
            return STATE_MAIN_MENU

        if any(word in text for word in ["restaurant", "food", "eat", "dinner", "lunch"]):
            await update.message.reply_text(
                "🍝 *Rome Food Tips*\n\n"
                "Must-try dishes:\n"
                "• 🍝 Cacio e Pepe — classic Roman pasta\n"
                "• 🍕 Pizza al Taglio — Roman-style pizza by the slice\n"
                "• 🧀 Supplì — fried rice balls\n"
                "• 🍦 Gelato — artisan gelato from small shops\n"
                "• ☕ Espresso — standing at the bar (cheaper!)\n\n"
                "💡 *Tip:* Avoid restaurants right next to major tourist sites. "
                "Walk 2-3 blocks away for better food and prices!\n\n"
                "Areas for great food: Trastevere, Testaccio, Monti",
                parse_mode=ParseMode.MARKDOWN
            )
            return STATE_MAIN_MENU

        if any(word in text for word in ["thank", "grazie", "thanks"]):
            await update.message.reply_text(
                "😊 You're welcome! Is there anything else I can help you with?"
            )
            return STATE_MAIN_MENU

        if any(word in text for word in ["bye", "goodbye", "arrivederci", "ciao"]):
            await update.message.reply_text(self._t("goodbye", lang))
            return STATE_MAIN_MENU

        # Default: show menu
        await update.message.reply_text(
            self._t("unknown_command", lang) + "\n\n" + self._t("help_text", lang),
            parse_mode=ParseMode.MARKDOWN
        )
        return STATE_MAIN_MENU

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cancel command."""
        lang = self._get_lang(update)
        await update.message.reply_text(self._t("goodbye", lang))
        return ConversationHandler.END

    def get_application(self) -> Application:
        """Build and return the Telegram bot application."""
        application = Application.builder().token(self.config.channels.telegram_bot_token).build()

        # Conversation handler
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("start", self.start),
                CommandHandler("bookings", self.bookings_command),
                CommandHandler("support", self.support_command),
                CommandHandler("info", self.info_command),
                CommandHandler("language", self.language_command),
                CommandHandler("help", self.help_command),
            ],
            states={
                STATE_MAIN_MENU: [
                    CallbackQueryHandler(self.handle_callback),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_free_text),
                ],
                STATE_BOOKING_LOOKUP: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_email_lookup),
                ],
                STATE_BOOKING_ACTION: [
                    CallbackQueryHandler(self.handle_callback),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_free_text),
                ],
                STATE_SUPPORT_TOPIC: [
                    CallbackQueryHandler(self.handle_callback),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_support_message),
                ],
                STATE_SUPPORT_MESSAGE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_support_message),
                ],
                STATE_LANGUAGE_SELECT: [
                    CallbackQueryHandler(self.handle_callback),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", self.cancel_command),
                CommandHandler("start", self.start),
                CommandHandler("help", self.help_command),
            ],
        )

        application.add_handler(conv_handler)

        # Set bot commands
        application.bot.set_my_commands([
            BotCommand("start", "Main menu"),
            BotCommand("bookings", "View your bookings"),
            BotCommand("support", "Get help"),
            BotCommand("info", "Rome tourist info"),
            BotCommand("language", "Change language"),
            BotCommand("help", "Show help"),
        ])

        return application

    def run(self):
        """Run the bot (polling mode)."""
        application = self.get_application()
        logger.info("🏛️ Roma Assistant bot starting...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def run_webhook(self, application: Application, webhook_url: str):
        """Run the bot in webhook mode."""
        await application.initialize()
        await application.start()
        await application.bot.set_webhook(webhook_url)
        logger.info(f"🏛️ Roma Assistant bot started with webhook: {webhook_url}")
