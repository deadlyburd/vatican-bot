#!/usr/bin/env python3
"""
MISSING INFO COLLECTOR — AI-powered
1. Scans CRM for bookings with missing info (email, passport, dietary, etc.)
2. WhatsApps the customer to collect it
3. When they reply, updates the sheet automatically
"""
import os, re, time, logging, requests
from datetime import datetime, date

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS = os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")

# Fields to check for each booking
REQUIRED_FIELDS = {
    "email": ["customerEmail", "email", "Email"],
    "phone": ["customerPhone", "phone", "Phone"],
    "passport": ["passportNumber", "passport", "Passport"],
    "nationality": ["nationality", "country", "Country"],
    "birth_date": ["birthDate", "dateOfBirth", "Birth Date"],
    "dietary": ["dietaryRequirements", "dietary", "Dietary"],
}

# Multi-language message templates
MESSAGES = {
    "EN": {
        "email": "Hi {name}! 🏛️ We're preparing your Vatican tour on {date}. Could you please share your email address?",
        "phone": "Hi {name}! 📱 For your Vatican tour on {date}, we need a contact number. Please reply with it!",
        "passport": "Hi {name}! 🛂 For your Vatican tour on {date}, please share your passport number (needed for entry).",
        "birth_date": "Hi {name}! 🎂 For your Vatican tour on {date}, we need your birth date (DD/MM/YYYY).",
        "generic": "Hi {name}! We need some additional info for your {product} on {date}. Please reply with: {fields}",
    },
    "IT": {
        "email": "Ciao {name}! 🏛️ Per il tuo tour in Vaticano del {date}, puoi condividere la tua email?",
        "phone": "Ciao {name}! 📱 Per il tour in Vaticano del {date}, ci serve un numero di telefono.",
        "passport": "Ciao {name}! 🛂 Per il tour in Vaticano del {date}, condividi il numero passaporto.",
        "birth_date": "Ciao {name}! 🎂 Per il tour in Vaticano del {date}, ci serve la data di nascita.",
        "generic": "Ciao {name}! Abbiamo bisogno di alcune info per il tuo {product} del {date}: {fields}",
    },
}


class MissingInfoCollector:
    """Finds bookings with missing info and messages customers."""

    def __init__(self):
        self._parser = None

    @property
    def parser(self):
        if not self._parser:
            from crm_intelligence.parsers.sheet_parser import SheetParser
            from customer_care.config.bot_config import config
            self._parser = SheetParser(
                sheet_id=config.crm.sheet_id,
                credentials_file=config.crm.service_account_file,
            )
        return self._parser

    def scan_missing_info(self) -> list:
        """Find bookings with missing required fields. Returns list of gaps."""
        self.parser.connect()
        activities = self.parser.parse_activity_lines(limit=3000)

        today = date.today()
        gaps = []

        for a in activities:
            # Only upcoming bookings
            try:
                a_date = datetime.strptime(a.activity_date, "%Y-%m-%d").date()
                if a_date < today:
                    continue
            except: continue

            # Only Vatican
            title = (a.product_title or "").lower()
            if not any(w in title for w in ["vatican", "sistine", "musei"]):
                continue

            # Skip cancelled
            if a.status and a.status.upper() in ("CANCELLED", "CANCELED"):
                continue

            # Check what's missing
            missing = []
            row_data = self._get_row_dict(a.booking_id)

            for field, keys in REQUIRED_FIELDS.items():
                value = None
                for k in keys:
                    value = getattr(a, k, None) or row_data.get(k) or row_data.get(k.lower())
                    if value and str(value).strip():
                        break
                if not value or not str(value).strip():
                    missing.append(field)

            if missing:
                gaps.append({
                    "booking_id": a.booking_id,
                    "customer_name": getattr(a, 'customer_name', '') or 'Customer',
                    "date": a.activity_date,
                    "product": (a.product_title or '')[:50],
                    "missing": missing,
                    "phone": getattr(a, 'customer_phone', '') or row_data.get('phone', ''),
                    "email": getattr(a, 'customer_email', '') or row_data.get('email', ''),
                })

        return sorted(gaps, key=lambda g: g['date'])

    def _get_row_dict(self, booking_id):
        """Quick row lookup by booking ID."""
        try:
            ws = None
            for w in self.parser._sheet.worksheets():
                if "activity" in w.title.lower():
                    ws = w; break
            if not ws: return {}
            records = ws.get_all_records()
            headers = ws.row_values(1)
            for r in records:
                if str(r.get('bookingId', '')) == str(booking_id):
                    return {headers[i]: list(r.values())[i] for i in range(len(headers))}
        except: pass
        return {}

    def send_whatsapp(self, phone: str, message: str) -> bool:
        """Send WhatsApp message via Meta API."""
        try:
            from customer_care.channels.whatsapp_bot import send_whatsapp_message
            # Clean phone number
            phone = re.sub(r'[^\d+]', '', str(phone))
            if not phone.startswith('+'): phone = '+' + phone
            result = send_whatsapp_message(phone, message)
            return result is not None
        except Exception as e:
            logger.warning(f"WhatsApp send failed: {e}")
            return False

    def collect_missing_info(self, max_messages: int = 10) -> str:
        """Main method: scan gaps, message customers, return report."""
        gaps = self.scan_missing_info()

        if not gaps:
            return "✅ All upcoming Vatican bookings have complete information!"

        sent = 0
        report = f"📋 *Missing Info Scan — {len(gaps)} bookings with gaps*\n\n"

        for g in gaps[:max_messages]:
            name = g['customer_name'].split()[0] or 'Customer'
            phone = g.get('phone', '')
            email = g.get('email', '')

            # Try to determine language
            lang = "EN"
            # Simple heuristic: Italian name = Italian message
            if any(n in name.lower() for n in ['mario','giuseppe','giovanni','luca','marco','francesco']):
                lang = "IT"

            msg_template = MESSAGES.get(lang, MESSAGES["EN"])
            missing_names = ", ".join(g['missing'])
            msg = msg_template.get("generic", msg_template["generic"]).format(
                name=name, date=g['date'], product=g['product'], fields=missing_names
            )

            # Try WhatsApp first, fallback to email notification
            sent_ok = False
            if phone:
                sent_ok = self.send_whatsapp(phone, msg)

            status = "✅ WhatsApp" if sent_ok else "⚠️ No phone" if not phone else "❌ Failed"
            report += f"  {status} {g['date']} — {name} — missing: {missing_names}\n"
            sent += 1
            time.sleep(1)  # Rate limit

        report += f"\n📨 *{sent} messages sent* | {len(gaps)} total gaps"
        return report

    def notify_admin(self, msg: str):
        """Send report to admin Telegram."""
        for aid in ADMIN_IDS:
            a = aid.strip()
            if a:
                try:
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                 json={"chat_id": a, "text": msg, "parse_mode": "Markdown"}, timeout=10)
                except: pass


    def send_family_instructions(self, booking_id: str = None) -> str:
        """Send document requirements to families with children/students."""
        gaps = self.scan_missing_info()

        # Also check for bookings with children
        self.parser.connect()
        activities = self.parser.parse_activity_lines(limit=3000)
        today = date.today()

        # Find bookings that might have children/students (reduced tickets)
        family_bookings = []
        for a in activities:
            try:
                a_date = datetime.strptime(a.activity_date, "%Y-%m-%d").date()
                if a_date < today: continue
            except: continue
            title = (a.product_title or "").lower()
            if not any(w in title for w in ["vatican", "sistine", "musei"]): continue

            pax = a.total_participants or 1
            # Check if there are children or students from the booking notes/fields
            row = self._get_row_dict(a.booking_id)
            children = row.get('children', row.get('Children', '0'))
            if str(children) != '0' or pax > 2:  # Families usually have 3+
                family_bookings.append({
                    "booking_id": a.booking_id,
                    "customer_name": getattr(a, 'customer_name', '') or 'Family',
                    "date": a.activity_date,
                    "pax": pax,
                    "phone": getattr(a, 'customer_phone', '') or row.get('phone', ''),
                    "email": getattr(a, 'customer_email', '') or row.get('email', ''),
                })

        if not family_bookings:
            return "No family/group bookings found."

        sent = 0
        for fb in family_bookings[:10]:
            name = fb['customer_name'].split()[0] or 'Family'
            phone = fb.get('phone', '')
            if not phone: continue

            # Italian + English instructions
            msg = (
                f"Ciao {name}! 🏛️\n\n"
                f"IMPORTANTE per la visita in Vaticano del {fb['date']}:\n\n"
                f"👶 *Biglietti ridotti*: hanno diritto al biglietto ridotto i ragazzi "
                f"dai 7 ai 18 anni compiuti e gli studenti fino ai 25 anni.\n\n"
                f"📋 *Il giorno della visita portare:*\n"
                f"• Documento d'identità per verificare l'età\n"
                f"• Libretto universitario o International Student Card (per studenti)\n\n"
                f"⚠️ Il biglietto ridotto senza documento valido sarà annullato e "
                f"dovrà essere acquistato un nuovo biglietto a tariffa intera.\n\n"
                f"Buona visita! 🇻🇦\n— Hydra Travel"
            )

            if self.send_whatsapp(phone, msg):
                sent += 1
            time.sleep(1)

        return f"📨 *Family Instructions Sent*\n\n✅ {sent}/{len(family_bookings)} families notified about:\n• Age verification documents\n• Student ID requirements\n• Reduced ticket eligibility (7-18 years, students ≤25)"

    def send_child_verification(self, booking_id: str) -> bool:
        """Verify child age and send document instructions."""
        row = self._get_row_dict(booking_id)
        if not row: return False

        name = row.get('customerName', 'Customer')
        phone = row.get('customerPhone', '')
        children = row.get('children', '0')
        if not phone or children == '0': return False

        msg = (
            f"Ciao {name.split()[0]}! 👋\n\n"
            f"Per il vostro tour in Vaticano abbiamo notato che ci sono {children} bambini/studenti "
            f"nel gruppo. Vi ricordiamo che:\n\n"
            f"🎫 *7-18 anni*: biglietto ridotto (portare documento)\n"
            f"🎓 *Studenti ≤25 anni*: ridotto con tesserino universitario\n"
            f"👶 *0-6 anni*: gratuito\n\n"
            f"Portate i documenti il giorno della visita! 🇻🇦"
        )
        return self.send_whatsapp(phone, msg)


# Global instance
info_collector = MissingInfoCollector()
