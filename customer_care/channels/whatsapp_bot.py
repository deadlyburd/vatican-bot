"""
WhatsApp Customer Care Bot
===========================
Multi-language tourist support via WhatsApp Business Cloud API.
Handles booking lookups, Rome info, support tickets in EN, IT, ES, FR, DE.

Uses Meta WhatsApp Cloud API (graph.facebook.com)
"""

import os
import json
import logging
import re
from typing import Dict, Optional, Any
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

# ── WhatsApp API Config ──────────────────────────────────────────────
WHATSAPP_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_API_VERSION = "v22.0"
WHATSAPP_API_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_ID}"

# ── Translations (same structure as Telegram bot) ────────────────────
I18N = {
    "en": {
        "welcome": "🏛️ Welcome to Roma Assistant!\n\nI'm here to help you with your Rome and Vatican bookings. Reply with:\n\n1️⃣ *My Bookings* — view your bookings\n2️⃣ *Support* — get help\n3️⃣ *Rome Info* — tourist information",
        "enter_email": "📧 Please enter your email address to look up your bookings:",
        "booking_not_found": "❌ No bookings found for this email. Please check and try again, or type *Support* to talk to our team.",
        "booking_found": "✅ Found *{count}* booking(s):\n\n{list}",
        "booking_detail": "📋 *{product}*\n📅 {date} at {time}\n👥 {pax} participants\n📊 {status}\n🎫 {code}",
        "support_intro": "💬 *How can we help?*\n\nReply with your question or describe your issue. Our team will respond within 2 hours (9am-6pm Rome time).",
        "support_created": "✅ Support ticket *#{ticket_id}* created!\n\nWe'll get back to you within 2 hours during business hours.\n\nFor urgent issues call: +39 06 6988",
        "rome_info": "🏛️ *Rome Tourist Info*\n\nReply with a number:\n1️⃣ Vatican tips\n2️⃣ Transport & metro\n3️⃣ Food & dining\n4️⃣ Weather tips\n5️⃣ Dress code\n6️⃣ Emergency numbers",
        "vatican_info": "🏛️ *Vatican Museums*\n\n• Dress code: shoulders & knees covered\n• Best time: 8-9am or after 3pm\n• Meeting point: Viale Vaticano 100\n• Skip-the-line tickets strongly recommended\n\nNeed a ticket? Reply with *Bookings*",
        "transport_info": "🚇 *Rome Transport*\n\n• Metro: 5:30-23:30 (Fri/Sat until 1:30)\n• Day pass: €7\n• 48h pass: €12.50\n• Bus 64/40: Termini to Vatican\n• Taxi: ~€10-15 within center\n\nDownload the *Moovit* app for live routes.",
        "food_info": "🍝 *Rome Food Tips*\n\n• Avoid restaurants next to big tourist spots\n• Look for 'trattoria' not 'ristorante'\n• Try: carbonara, amatriciana, cacio e pepe\n• Pizza al taglio = by the slice, great for lunch\n• Gelato tip: avoid neon-colored displays!",
        "weather_info": "🌤️ *Rome Weather*\n\nSummer (Jun-Aug): 28-35°C, sunny\nSpring (Mar-May): 15-24°C, pleasant\nFall (Sep-Nov): 14-26°C, occasional rain\nWinter (Dec-Feb): 3-13°C, wet spells\n\nBring water in summer — free 'nasoni' fountains everywhere!",
        "dress_code": "👗 *Dress Code for Churches*\n\n• Shoulders covered\n• Knees covered\n• No shorts or mini skirts\n• No sleeveless tops\n\n💡 Carry a scarf in your bag!",
        "emergency": "🆘 *Emergency Numbers*\n\n• 112 — EU Emergency\n• 113 — Police\n• 118 — Medical\n• +39 06 6988 — Vatican info\n\nYour embassy: check before traveling.",
        "language_changed": "✅ Language set to English!",
        "unknown": "I didn't understand. Reply with:\n*Bookings* | *Support* | *Rome Info*",
        "goodbye": "👋 Arrivederci! Have a wonderful time in Rome! 🏛️",
        "menu_bookings": "📋 My Bookings",
        "menu_support": "💬 Support",
        "menu_info": "ℹ️ Rome Info",
        "menu_language": "🌐 Language",
        "language_prompt": "🌐 *Select your language:*\n\nReply: EN | IT | ES | FR | DE",
    },
    "it": {
        "welcome": "🏛️ Benvenuto a Roma Assistant!\n\nSono qui per aiutarti con le tue prenotazioni. Rispondi con:\n\n1️⃣ *Prenotazioni* — vedi le tue prenotazioni\n2️⃣ *Assistenza* — ricevi aiuto\n3️⃣ *Info Roma* — informazioni turistiche",
        "enter_email": "📧 Inserisci la tua email per cercare le prenotazioni:",
        "booking_not_found": "❌ Nessuna prenotazione trovata. Controlla l'email e riprova, o scrivi *Assistenza*.",
        "booking_found": "✅ Trovate *{count}* prenotazioni:\n\n{list}",
        "booking_detail": "📋 *{product}*\n📅 {date} alle {time}\n👥 {pax} partecipanti\n📊 {status}\n🎫 {code}",
        "support_intro": "💬 *Come possiamo aiutarti?*\n\nRispondi con la tua domanda. Risponderemo entro 2 ore (9-18 ora di Roma).",
        "support_created": "✅ Ticket di assistenza *#{ticket_id}* creato!\n\nTi risponderemo entro 2 ore.\n\nPer urgenze chiama: +39 06 6988",
        "rome_info": "🏛️ *Info Turistiche Roma*\n\nRispondi con un numero:\n1️⃣ Consigli Vaticano\n2️⃣ Trasporti\n3️⃣ Cibo e ristoranti\n4️⃣ Meteo\n5️⃣ Codice abbigliamento\n6️⃣ Numeri emergenza",
        "vatican_info": "🏛️ *Musei Vaticani*\n\n• Abbigliamento: spalle e ginocchia coperte\n• Orario migliore: 8-9 o dopo le 15\n• Ingresso: Viale Vaticano 100\n• Biglietti salta-fila raccomandati",
        "transport_info": "🚇 *Trasporti Roma*\n\n• Metro: 5:30-23:30 (Ven/Sab fino 1:30)\n• Giornaliero: €7\n• 48 ore: €12.50\n• Bus 64/40: Termini-Vaticano\n• Taxi: ~€10-15 in centro\n\nScarica app *Moovit* per percorsi live.",
        "food_info": "🍝 *Consigli Cibo Roma*\n\n• Evita ristoranti accanto ai monumenti\n• Cerca 'trattoria' non 'ristorante'\n• Prova: carbonara, amatriciana, cacio e pepe\n• Pizza al taglio = economica e veloce\n• Gelato: evita i colori fluorescenti!",
        "language_changed": "✅ Lingua impostata su Italiano!",
        "unknown": "Non ho capito. Rispondi:\n*Prenotazioni* | *Assistenza* | *Info Roma*",
        "menu_bookings": "📋 Prenotazioni",
        "menu_support": "💬 Assistenza",
        "menu_info": "ℹ️ Info Roma",
        "menu_language": "🌐 Lingua",
        "language_prompt": "🌐 *Seleziona la lingua:*\n\nRispondi: EN | IT | ES | FR | DE",
    },
    "es": {
        "welcome": "🏛️ ¡Bienvenido a Roma Assistant!\n\nEstoy aquí para ayudarte con tus reservas. Responde:\n\n1️⃣ *Reservas* — ver tus reservas\n2️⃣ *Ayuda* — soporte\n3️⃣ *Info Roma* — información turística",
        "enter_email": "📧 Ingresa tu email para buscar tus reservas:",
        "booking_not_found": "❌ No se encontraron reservas. Revisa el email o escribe *Ayuda*.",
        "booking_found": "✅ *{count}* reserva(s) encontrada(s):\n\n{list}",
        "booking_detail": "📋 *{product}*\n📅 {date} a las {time}\n👥 {pax} participantes\n📊 {status}\n🎫 {code}",
        "support_intro": "💬 *¿Cómo podemos ayudarte?*\n\nResponde con tu pregunta. Responderemos en 2 horas (9-18 hora Roma).",
        "support_created": "✅ Ticket de soporte *#{ticket_id}* creado.\n\nResponderemos en 2 horas.\n\nUrgencias: +39 06 6988",
        "rome_info": "🏛️ *Info Turística Roma*\n\nResponde con un número:\n1️⃣ Tips Vaticano\n2️⃣ Transporte\n3️⃣ Comida\n4️⃣ Clima\n5️⃣ Código de vestimenta\n6️⃣ Emergencias",
        "language_changed": "✅ ¡Idioma cambiado a Español!",
        "unknown": "No entendí. Responde: *Reservas* | *Ayuda* | *Info Roma*",
        "menu_bookings": "📋 Reservas",
        "menu_support": "💬 Ayuda",
        "menu_info": "ℹ️ Info Roma",
        "menu_language": "🌐 Idioma",
        "language_prompt": "🌐 *Selecciona tu idioma:*\n\nResponde: EN | IT | ES | FR | DE",
    },
    "fr": {
        "welcome": "🏛️ Bienvenue sur Roma Assistant!\n\nJe suis là pour vous aider. Répondez:\n\n1️⃣ *Réservations* — vos réservations\n2️⃣ *Support* — aide\n3️⃣ *Info Rome* — informations touristiques",
        "enter_email": "📧 Entrez votre email pour rechercher vos réservations:",
        "booking_not_found": "❌ Aucune réservation trouvée. Vérifiez l'email ou tapez *Support*.",
        "booking_found": "✅ *{count}* réservation(s) trouvée(s):\n\n{list}",
        "booking_detail": "📋 *{product}*\n📅 {date} à {time}\n👥 {pax} participants\n📊 {status}\n🎫 {code}",
        "support_intro": "💬 *Comment pouvons-nous vous aider?*\n\nDécrivez votre problème. Réponse sous 2 heures (9h-18h heure de Rome).",
        "support_created": "✅ Ticket *#{ticket_id}* créé!\n\nRéponse sous 2 heures.\n\nUrgences: +39 06 6988",
        "language_changed": "✅ Langue changée en Français!",
        "unknown": "Je n'ai pas compris. Répondez: *Réservations* | *Support* | *Info Rome*",
        "menu_bookings": "📋 Réservations",
        "menu_support": "💬 Support",
        "menu_info": "ℹ️ Info Rome",
        "menu_language": "🌐 Langue",
        "language_prompt": "🌐 *Choisissez votre langue:*\n\nRépondez: EN | IT | ES | FR | DE",
    },
    "de": {
        "welcome": "🏛️ Willkommen bei Roma Assistant!\n\nIch helfe Ihnen bei Ihren Buchungen. Antworten Sie:\n\n1️⃣ *Buchungen* — Ihre Buchungen\n2️⃣ *Support* — Hilfe\n3️⃣ *Rom Info* — Touristeninfo",
        "enter_email": "📧 Geben Sie Ihre E-Mail ein, um Buchungen zu finden:",
        "booking_not_found": "❌ Keine Buchungen gefunden. Überprüfen Sie die E-Mail oder tippen Sie *Support*.",
        "booking_found": "✅ *{count}* Buchung(en) gefunden:\n\n{list}",
        "booking_detail": "📋 *{product}*\n📅 {date} um {time}\n👥 {pax} Teilnehmer\n📊 {status}\n🎫 {code}",
        "support_intro": "💬 *Wie können wir helfen?*\n\nBeschreiben Sie Ihr Problem. Antwort innerhalb 2 Stunden (9-18 Uhr Rom).",
        "support_created": "✅ Ticket *#{ticket_id}* erstellt!\n\nAntwort innerhalb 2 Stunden.\n\nNotfälle: +39 06 6988",
        "language_changed": "✅ Sprache auf Deutsch geändert!",
        "unknown": "Nicht verstanden. Antworten Sie: *Buchungen* | *Support* | *Rom Info*",
        "menu_bookings": "📋 Buchungen",
        "menu_support": "💬 Support",
        "menu_info": "ℹ️ Rom Info",
        "menu_language": "🌐 Sprache",
        "language_prompt": "🌐 *Wählen Sie Ihre Sprache:*\n\nAntworten: EN | IT | ES | FR | DE",
    },
}

# ── Conversation States ──────────────────────────────────────────────
class WhatsAppState:
    MAIN_MENU = "main_menu"
    AWAITING_EMAIL = "awaiting_email"
    AWAITING_SUPPORT = "awaiting_support"
    AWAITING_ROME_INFO = "awaiting_rome_info"
    AWAITING_LANGUAGE = "awaiting_language"

# In-memory session store (replace with Redis in production)
_sessions: Dict[str, Dict] = {}


class WhatsAppBot:
    """Multi-language tourist customer care bot via WhatsApp."""

    def __init__(self, parser=None, analyzer=None):
        self._parser = parser
        self._analyzer = analyzer

    @property
    def parser(self):
        if self._parser is None:
            from crm_intelligence.parsers.sheet_parser import SheetParser
            from customer_care.config.bot_config import config
            self._parser = SheetParser(
                sheet_id=config.crm.sheet_id,
                credentials_file=config.crm.service_account_file,
            )
        return self._parser

    @property
    def analyzer(self):
        if self._analyzer is None:
            from crm_intelligence.ai.crm_analyzer import CRMAnalyzer
            self._analyzer = CRMAnalyzer([], [], [], [])
        return self._analyzer

    # ── Session Management ──────────────────────────────────────────
    def _get_session(self, phone: str) -> Dict:
        if phone not in _sessions:
            _sessions[phone] = {
                "state": WhatsAppState.MAIN_MENU,
                "lang": "en",
                "email": None,
            }
        return _sessions[phone]

    def _t(self, phone: str, key: str) -> str:
        """Get translated string for user's language."""
        session = self._get_session(phone)
        lang = session.get("lang", "en")
        lang_dict = I18N.get(lang, I18N["en"])
        return lang_dict.get(key, I18N["en"].get(key, key))

    # ── Message Processing ──────────────────────────────────────────
    def process_message(self, phone: str, text: str) -> str:
        """Process incoming WhatsApp message and return response."""
        if not text:
            return self._t(phone, "unknown")

        text = text.strip()
        session = self._get_session(phone)
        state = session.get("state", WhatsAppState.MAIN_MENU)
        text_lower = text.lower()

        # ── Global commands (work from any state) ──────────────────
        if text_lower in ("language", "lingua", "idioma", "langue", "sprache", "🌐 language"):
            session["state"] = WhatsAppState.AWAITING_LANGUAGE
            return self._t(phone, "language_prompt")

        # Language selection
        if text_lower in ("en", "english"):
            session["lang"] = "en"
            session["state"] = WhatsAppState.MAIN_MENU
            return self._t(phone, "language_changed") + "\n\n" + self._t(phone, "welcome")

        if text_lower in ("it", "italiano", "italian"):
            session["lang"] = "it"
            session["state"] = WhatsAppState.MAIN_MENU
            return I18N["it"]["language_changed"] + "\n\n" + I18N["it"]["welcome"]

        if text_lower in ("es", "español", "spanish"):
            session["lang"] = "es"
            session["state"] = WhatsAppState.MAIN_MENU
            return I18N["es"]["language_changed"] + "\n\n" + I18N["es"]["welcome"]

        if text_lower in ("fr", "français", "french"):
            session["lang"] = "fr"
            session["state"] = WhatsAppState.MAIN_MENU
            return I18N["fr"]["language_changed"] + "\n\n" + I18N["fr"]["welcome"]

        if text_lower in ("de", "deutsch", "german"):
            session["lang"] = "de"
            session["state"] = WhatsAppState.MAIN_MENU
            return I18N["de"]["language_changed"] + "\n\n" + I18N["de"]["welcome"]

        # Main menu / back
        if text_lower in ("menu", "back", "home", "indietro", "inicio"):
            session["state"] = WhatsAppState.MAIN_MENU
            return self._t(phone, "welcome")

        # ── State Machine ──────────────────────────────────────────
        if state == WhatsAppState.AWAITING_EMAIL:
            return self._handle_email_lookup(phone, text)

        if state == WhatsAppState.AWAITING_SUPPORT:
            return self._handle_support(phone, text)

        if state == WhatsAppState.AWAITING_ROME_INFO:
            return self._handle_rome_info(phone, text)

        if state == WhatsAppState.AWAITING_LANGUAGE:
            return self._handle_language(phone, text)

        # ── Main Menu ──────────────────────────────────────────────
        return self._handle_main_menu(phone, text)

    def _handle_main_menu(self, phone: str, text: str) -> str:
        """Handle main menu options."""
        text_lower = text.lower()
        session = self._get_session(phone)

        # Bookings
        if any(w in text_lower for w in ("bookings", "prenotazioni", "reservas", "réservations", "buchungen", "1", "📋", "booking", "prenotazione")):
            session["state"] = WhatsAppState.AWAITING_EMAIL
            return self._t(phone, "enter_email")

        # Support
        if any(w in text_lower for w in ("support", "assistenza", "ayuda", "aide", "hilfe", "2", "💬", "help", "aiuto")):
            session["state"] = WhatsAppState.AWAITING_SUPPORT
            return self._t(phone, "support_intro")

        # Rome Info
        if any(w in text_lower for w in ("info", "rome", "roma", "rom", "3", "ℹ️", "information", "informazioni", "información")):
            session["state"] = WhatsAppState.AWAITING_ROME_INFO
            return self._t(phone, "rome_info")

        # Greetings
        if text_lower in ("hi", "hello", "ciao", "hola", "bonjour", "hallo", "hey", "buongiorno", "buonasera"):
            return self._t(phone, "welcome")

        # Unknown
        return self._t(phone, "unknown")

    def _handle_email_lookup(self, phone: str, text: str) -> str:
        """Look up bookings by email."""
        session = self._get_session(phone)
        email = text.strip().lower()

        if "@" not in email or "." not in email:
            return f"❌ {self._t(phone, 'enter_email')}"

        session["email"] = email
        session["state"] = WhatsAppState.MAIN_MENU

        try:
            self.parser.connect()
            bookings_data = self.parser.parse_bookings(limit=500)

            # Filter by email
            matching = [
                b for b in bookings_data
                if b.customer and b.customer.email and b.customer.email.lower() == email
            ]

            if not matching:
                return self._t(phone, "booking_not_found")

            # Get activities for these bookings
            matching_ids = {b.booking_id for b in matching}
            all_activities = self.parser.parse_activity_lines(limit=2000)
            activities = [a for a in all_activities if a.booking_id in matching_ids]

            lines = []
            for activity in activities[:10]:
                lines.append(self._t(phone, "booking_detail").format(
                    product=activity.product_title[:50],
                    date=activity.activity_date or "N/A",
                    time=activity.startTime or "N/A",
                    pax=activity.total_participants or "?",
                    status=activity.status or "N/A",
                    code=activity.product_confirmation_code or "N/A",
                ))

            return self._t(phone, "booking_found").format(
                count=len(matching),
                list="\n\n".join(lines) if lines else "No upcoming activities found."
            )

        except Exception as e:
            logger.error(f"CRM lookup error: {e}")
            return "❌ Unable to look up bookings right now. Please try again or type *Support* for help."

    def _handle_support(self, phone: str, text: str) -> str:
        """Handle support request."""
        import random
        ticket_id = random.randint(10000, 99999)
        session = self._get_session(phone)
        session["state"] = WhatsAppState.MAIN_MENU

        # Log the support request
        logger.info(f"📞 Support ticket #{ticket_id} from {phone}: {text[:200]}")

        # Notify admins via Telegram if available
        try:
            admin_ids = os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
            if admin_ids and admin_ids[0]:
                from customer_care.channels.telegram_notify import notify_admins
                notify_admins(f"📞 *WhatsApp Support #{ticket_id}*\n\nFrom: `{phone}`\nEmail: {session.get('email', 'N/A')}\n\n{text[:500]}")
        except Exception:
            pass

        return self._t(phone, "support_created").format(ticket_id=ticket_id)

    def _handle_rome_info(self, phone: str, text: str) -> str:
        """Handle Rome info requests."""
        session = self._get_session(phone)
        session["state"] = WhatsAppState.MAIN_MENU
        text_lower = text.lower()

        if any(w in text_lower for w in ("1", "vatican", "vaticano")):
            return self._t(phone, "vatican_info")
        elif any(w in text_lower for w in ("2", "transport", "trasporti", "metro", "bus")):
            return self._t(phone, "transport_info")
        elif any(w in text_lower for w in ("3", "food", "cibo", "restaurant", "eat", "mangiare", "comida")):
            return self._t(phone, "food_info")
        elif any(w in text_lower for w in ("4", "weather", "meteo", "clima", "temp")):
            return self._t(phone, "weather_info")
        elif any(w in text_lower for w in ("5", "dress", "vestimenta", "abbigliamento", "code", "clothes")):
            return self._t(phone, "dress_code")
        elif any(w in text_lower for w in ("6", "emergency", "emergenza", "police", "ambulance")):
            return self._t(phone, "emergency")
        else:
            # Generic Rome answer
            return self._t(phone, "rome_info")

    def _handle_language(self, phone: str, text: str) -> str:
        """Handle language selection fallback."""
        return self._t(phone, "language_prompt")


# ── WhatsApp API Helpers ─────────────────────────────────────────────

def send_whatsapp_message(phone: str, message: str) -> Optional[Dict]:
    """Send a message via WhatsApp Cloud API."""
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        logger.error("WhatsApp credentials not configured")
        return None

    url = f"{WHATSAPP_API_URL}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "text",
        "text": {"preview_url": False, "body": message},
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        data = resp.json()
        if resp.status_code != 200 and resp.status_code != 201:
            logger.error(f"WhatsApp send error: {data}")
            return None
        return data
    except Exception as e:
        logger.error(f"WhatsApp send failed: {e}")
        return None


def mark_message_read(message_id: str) -> bool:
    """Mark a WhatsApp message as read."""
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        return False

    url = f"{WHATSAPP_API_URL}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        return resp.status_code in (200, 201)
    except Exception:
        return False


# Global bot instance
whatsapp_bot = WhatsAppBot()
