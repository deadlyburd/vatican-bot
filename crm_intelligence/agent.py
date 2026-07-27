"""
HYDRA AI AGENT — Full operational AI for travel agency management
==================================================================
DeepSeek-powered agent that can:
- Query CRM (customers, bookings, revenue)
- Send notifications (Telegram, email-ready)
- Update Google Sheets
- Trigger bookings
- Execute multi-step workflows

Tool-based architecture → scalable, cache-aware, async-capable.
"""
import json, logging, os, time, re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
import requests

logger = logging.getLogger(__name__)

BACKEND = os.getenv("SERVER_BASE_URL", "http://backend:8000")
if not BACKEND.startswith("http"): BACKEND = f"http://{BACKEND}"
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS = os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")

# ── CRM Cache ────────────────────────────────────────────────────
_cache = {"data": None, "ts": 0, "ttl": 30}

def _crm():
    now = time.time()
    if _cache["data"] and (now - _cache["ts"]) < _cache["ttl"]:
        return _cache["data"]
    d = _load_crm()
    _cache["data"] = d; _cache["ts"] = now
    return d

def _load_crm():
    d = {"today": date.today().strftime("%Y-%m-%d"), "customers": [], "activities": [],
         "bookings": [], "products": [], "vatican_targets": []}
    try:
        from crm_intelligence.parsers.sheet_parser import SheetParser
        from customer_care.config.bot_config import config
        p = SheetParser(sheet_id=config.crm.sheet_id, credentials_file=config.crm.service_account_file)
        p.connect()

        activities = p.parse_activity_lines(limit=5000)
        for a in activities:
            d["activities"].append({
                "date": a.activity_date, "time": a.startTime or "",
                "product": a.product_title or "", "pax": a.total_participants or 0,
                "vatican": a.is_vatican, "booking_id": a.booking_id or "",
                "status": a.status or "", "confirmation": a.product_confirmation_code or "",
            })

        bookings = p.parse_bookings(limit=2000)
        for b in bookings:
            c = b.customer
            d["customers"].append({
                "name": c.full_name or "" if c else "", "email": (c.email or "").lower() if c else "",
                "phone": c.phone or "" if c else "", "country": c.country or "" if c else "",
                "language": c.language or "" if c else "",
                "total_spent": float(getattr(c, 'total_spent', 0) or 0) if c else 0,
                "booking_ids": [b.booking_id],
            })

        d["bookings"] = [{"id": b.booking_id, "date": getattr(b, 'booking_date', ''),
                          "total": float(getattr(b, 'total_price', 0) or 0)} for b in bookings]

        try:
            products = p.parse_products()
            d["products"] = [{"title": pr.title, "price": pr.price_from, "vatican": pr.is_vatican} for pr in products]
        except: pass

        try:
            from crm_intelligence.auto_snipe import CRMAutoSnipeService
            svc = CRMAutoSnipeService()
            for t in svc.scan_crm_for_targets():
                d["vatican_targets"].append({"date": t.activity_date, "name": t.customer_name,
                    "email": t.customer_email, "visitors": t.visitors, "days": t.days_until})
        except: pass

    except Exception as e:
        d["_error"] = str(e)[:100]
    return d

# ── TOOLS ─────────────────────────────────────────────────────────
# Each tool is a function the AI can call. Described for DeepSeek function calling.

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_customers",
            "description": "Search customers by country, language, product interest, or date range. Returns matching customers with their contact info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "country": {"type": "string", "description": "Filter by country (e.g., Germany, Italy, USA)"},
                    "language": {"type": "string", "description": "Filter by language (e.g., IT, EN, DE)"},
                    "has_vatican": {"type": "boolean", "description": "Only customers with Vatican bookings"},
                    "date_from": {"type": "string", "description": "Start date YYYY-MM-DD for activity filtering"},
                    "date_to": {"type": "string", "description": "End date YYYY-MM-DD"},
                    "min_spent": {"type": "number", "description": "Minimum total spent in EUR"},
                    "limit": {"type": "integer", "description": "Max results (default 20)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_detail",
            "description": "Get full details for a specific customer by email, including all their bookings and activities.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Customer email address"},
                },
                "required": ["email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_bookings_summary",
            "description": "Get booking summary for a date range or period. Returns counts, revenue, and breakdowns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "enum": ["today", "week", "month", "year"], "description": "Time period"},
                    "product_type": {"type": "string", "enum": ["all", "vatican", "other"], "description": "Filter by product type"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_customer_message",
            "description": "Prepare and send a message to customer(s). Currently sends via Telegram to admin for review, with email-ready template.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipients": {"type": "string", "description": "How to find recipients: 'all_vatican_tomorrow', 'urgent_bookings', 'german_customers', 'customer_email@...', or 'all_customers'"},
                    "subject": {"type": "string", "description": "Message subject/topic"},
                    "message": {"type": "string", "description": "Message body to send"},
                    "language": {"type": "string", "description": "Language for the message (IT, EN, DE, etc.)"},
                },
                "required": ["recipients", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_vatican_status",
            "description": "Get current Vatican booking status — available slots, held slots, pending snipes, and payment links.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_booking",
            "description": "Trigger an immediate booking attempt for a specific date. Books via Chrome/nodriver.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date in DD/MM/YYYY format"},
                    "visitors": {"type": "integer", "description": "Number of visitors (default 2)"},
                    "customer_email": {"type": "string", "description": "Customer email to use for buyer info"},
                },
                "required": ["date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_sheet",
            "description": "Update Google Sheets CRM data: write payment links, update booking status, add notes, add customers, or modify any sheet data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["write_payment_link", "add_note", "update_status", "add_activity", "update_customer", "list_sheets"], "description": "What to do"},
                    "booking_id": {"type": "string", "description": "Booking ID to update"},
                    "activity_date": {"type": "string", "description": "Activity date YYYY-MM-DD"},
                    "payment_link": {"type": "string", "description": "epay URL to write"},
                    "note": {"type": "string", "description": "Note text to add"},
                    "status": {"type": "string", "description": "New status to set"},
                    "customer_email": {"type": "string", "description": "Customer email"},
                    "customer_name": {"type": "string", "description": "Customer full name"},
                    "customer_phone": {"type": "string", "description": "Customer phone"},
                    "product_title": {"type": "string", "description": "Product name for new activity"},
                    "visitors": {"type": "integer", "description": "Number of visitors"},
                    "sheet_name": {"type": "string", "description": "Sheet tab name to operate on"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "collect_missing_info",
            "description": "Scan upcoming Vatican bookings for missing customer info (email, phone, passport, etc.) and send WhatsApp messages to collect it. Returns report.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_messages": {"type": "integer", "description": "Max customers to message (default 10)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_revenue_report",
            "description": "Get detailed revenue breakdown by month, product type, or customer segment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "enum": ["month", "year", "all"], "description": "Time period"},
                    "breakdown": {"type": "string", "enum": ["product", "month", "country"], "description": "How to break down"},
                },
            },
        },
    },
]

# ── TOOL EXECUTORS ────────────────────────────────────────────────

def tool_search_customers(params: dict) -> str:
    d = _crm()
    customers = d.get("customers", [])
    activities = d.get("activities", [])

    country = (params.get("country") or "").lower()
    language = (params.get("language") or "").lower()
    has_vatican = params.get("has_vatican")
    min_spent = params.get("min_spent", 0)
    limit = params.get("limit", 20)

    results = []
    for c in customers:
        if country and country not in c.get("country", "").lower(): continue
        if language and language != c.get("language", "").lower(): continue
        if min_spent and c.get("total_spent", 0) < min_spent: continue
        if has_vatican:
            bid = c.get("booking_ids", [None])[0]
            has_v = any(a.get("booking_id") == bid and a.get("vatican") for a in activities)
            if not has_v: continue
        results.append(c)

    results = results[:limit]
    if not results: return "No customers match those filters."

    return json.dumps({
        "count": len(results),
        "customers": [{"name": r["name"], "email": r["email"], "phone": r["phone"],
                        "country": r["country"], "spent": r["total_spent"]} for r in results],
    }, indent=2)

def tool_get_customer_detail(params: dict) -> str:
    email = (params.get("email") or "").lower()
    d = _crm()
    customers = [c for c in d.get("customers", []) if c.get("email") == email]
    if not customers: return f"No customer found for {email}"
    c = customers[0]
    bids = c.get("booking_ids", [])
    acts = [a for a in d.get("activities", []) if a.get("booking_id") in bids]
    upcoming = [a for a in acts if a["date"] >= d["today"]]

    return json.dumps({
        "profile": {"name": c["name"], "email": c["email"], "phone": c["phone"],
                    "country": c["country"], "language": c["language"], "total_spent": c["total_spent"]},
        "total_bookings": len(bids),
        "total_activities": len(acts),
        "upcoming": [{"date": a["date"], "time": a["time"], "product": a["product"][:50], "pax": a["pax"]} for a in upcoming[:10]],
    }, indent=2)

def tool_get_bookings_summary(params: dict) -> str:
    d = _crm()
    period = params.get("period", "month")
    ptype = params.get("product_type", "all")
    today = date.today()

    if period == "today": start = today
    elif period == "week": start = today - timedelta(days=today.weekday())
    elif period == "month": start = today.replace(day=1)
    elif period == "year": start = today.replace(month=1, day=1)
    else: start = today.replace(day=1)

    acts = [a for a in d.get("activities", []) if a["date"] and a["date"] >= start.strftime("%Y-%m-%d")]
    if ptype == "vatican": acts = [a for a in acts if a.get("vatican")]
    elif ptype == "other": acts = [a for a in acts if not a.get("vatican")]

    rev = sum(float(b.get("total", 0) or 0) for b in d.get("bookings", [])
              if b.get("date") and b["date"] >= start.strftime("%Y-%m-%d"))

    return json.dumps({
        "period": period, "product_type": ptype,
        "total_activities": len(acts),
        "estimated_revenue": round(rev, 2),
        "by_date": {d: len([a for a in acts if a["date"] == d])
                    for d in sorted(set(a["date"] for a in acts if a["date"]))[:14]},
    }, indent=2)

def tool_send_customer_message(params: dict) -> str:
    recipients = params.get("recipients", "")
    subject = params.get("subject", "")
    message_body = params.get("message", "")
    lang = params.get("language", "IT")

    d = _crm()
    customers = d.get("customers", [])
    targets = []

    if "@" in recipients:
        targets = [c for c in customers if c.get("email") == recipients.lower()]
    elif recipients == "all_vatican_tomorrow":
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        vat_acts = [a for a in d.get("activities", []) if a["date"] == tomorrow and a.get("vatican")]
        bids = set(a["booking_id"] for a in vat_acts)
        targets = [c for c in customers if any(b in bids for b in c.get("booking_ids", []))]
    elif recipients == "urgent_bookings":
        for t in d.get("vatican_targets", []):
            if t["days"] <= 3 and t.get("email"):
                c = next((c for c in customers if c.get("email") == t.get("email")), None)
                if c: targets.append(c)
    elif recipients == "german_customers":
        targets = [c for c in customers if c.get("country", "").lower() in ("germany", "deutschland", "de")]
    elif recipients == "all_customers":
        targets = customers[:50]
    else:
        # Try matching by name/country
        targets = [c for c in customers if recipients.lower() in c.get("name","").lower()
                   or recipients.lower() in c.get("country","").lower()][:30]

    if not targets:
        return f"No recipients found for: {recipients}"

    # Multi-language message templates
    def translate(msg, to_lang):
        """Simple multi-lang wrapper using DeepSeek for proper translation."""
        # Common phrases in multiple languages
        phrases = {
            "payment_reminder": {
                "IT": f"Gentile {{name}},\n\nQuesto è un promemoria per il pagamento del tuo tour Vaticano. Puoi completare il pagamento qui: {{link}}\n\nGrazie,\nHydra Travel",
                "EN": f"Dear {{name}},\n\nThis is a reminder to complete payment for your Vatican tour. You can pay here: {{link}}\n\nThank you,\nHydra Travel",
                "DE": f"Sehr geehrte(r) {{name}},\n\nDies ist eine Zahlungserinnerung für Ihre Vatikan-Tour. Hier bezahlen: {{link}}\n\nDanke,\nHydra Travel",
                "ES": f"Estimado/a {{name}},\n\nRecordatorio de pago para su tour al Vaticano. Pague aquí: {{link}}\n\nGracias,\nHydra Travel",
                "FR": f"Cher/Chère {{name}},\n\nRappel de paiement pour votre visite du Vatican. Payez ici : {{link}}\n\nMerci,\nHydra Travel",
            },
            "general": {
                "IT": f"{{msg}}",
                "EN": f"{{msg}}",
                "DE": f"{{msg}}",
                "ES": f"{{msg}}",
                "FR": f"{{msg}}",
            },
        }
        tmpl = phrases.get(subject.lower().replace(" ","_"), phrases["general"])
        template = tmpl.get(lang.upper(), tmpl.get("EN", "{{msg}}"))
        return template.replace("{{msg}}", message_body).replace("{{name}}", to.get("name",""))

    # Send via WhatsApp if credentials configured
    sent_count = 0
    failed_phones = []
    try:
        from customer_care.channels.whatsapp_bot import send_whatsapp_message, WHATSAPP_TOKEN, WHATSAPP_PHONE_ID

        if WHATSAPP_TOKEN and WHATSAPP_PHONE_ID:
            for c in targets:
                phone = c.get("phone", "").strip()
                if not phone: continue
                # Clean phone number
                phone = re.sub(r'[^\d+]', '', phone)
                if not phone.startswith('+'): phone = '+' + phone

                personalized = translate(message_body, lang).replace("{{name}}", c.get("name", ""))
                personalized = personalized.replace("{{link}}", d.get("payment_links", [{}])[0].get("link", ""))

                try:
                    result = send_whatsapp_message(phone, personalized)
                    if result:
                        sent_count += 1
                    else:
                        failed_phones.append(phone)
                except Exception:
                    failed_phones.append(phone)
                time.sleep(0.5)  # Rate limit
    except ImportError:
        pass

    # Also prepare email-ready version
    emails = [c["email"] for c in targets if c.get("email")]
    report = f"📧 *Message Sent*\n\nTo: {len(targets)} customers ({recipients})\nLanguage: {lang}\n"
    if sent_count > 0:
        report += f"✅ WhatsApp sent: *{sent_count}*\n"
    if failed_phones:
        report += f"❌ Failed: {len(failed_phones)}\n"
    report += f"\n📋 Emails: {', '.join(emails[:8])}"
    if len(emails) > 8: report += f"\n... +{len(emails)-8} more"
    report += f"\n\n💬 Message:\n{message_body[:400]}"

    # Notify admin
    try:
        for aid in ADMIN_IDS:
            a = aid.strip()
            if a:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                             json={"chat_id": a, "text": report, "parse_mode": "Markdown"}, timeout=5)
    except: pass

    return report

def tool_get_vatican_status(params: dict = None) -> str:
    d = _crm()
    # Backend holds
    holds = []
    try:
        r = requests.get(f"{BACKEND}/api/v1/holds/", params={"status": "all"}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            holds = data.get("results", []) if isinstance(data, dict) else data
    except: pass

    return json.dumps({
        "pending_targets": len([t for t in d.get("vatican_targets", []) if t["days"] >= 0]),
        "urgent": len([t for t in d.get("vatican_targets", []) if t["days"] <= 3]),
        "upcoming": len([t for t in d.get("vatican_targets", []) if 3 < t["days"] <= 14]),
        "held_slots": len([h for h in holds if h.get("status") in ("held", "recap_done")]),
        "payment_ready": len([h for h in holds if h.get("status") == "payment_ready"]),
        "payment_links": [{"id": h.get("id"), "date": h.get("date"),
                          "link": (h.get("payment_link") or "")[:80]} for h in holds if h.get("payment_link")][:5],
    }, indent=2)

def tool_trigger_booking(params: dict) -> str:
    date_str = params.get("date", "")
    visitors = params.get("visitors", 2)
    email = params.get("customer_email", "")
    if not date_str: return "Error: date required (DD/MM/YYYY)"

    # Find slot via API
    from slot_finder import SlotFinder
    finder = SlotFinder()
    slots = finder.find_slots(date_str, visitors, use_cache=False)
    if not slots:
        return f"No available Vatican slots for {date_str} ({visitors}v)"

    slot = slots[0]
    # Return instructions to run booker
    return json.dumps({
        "status": "slot_found",
        "date": slot.date, "time": slot.time, "visitors": slot.visitors,
        "slot_id": slot.slot_id, "ticket": slot.ticket_name,
        "command": f"docker exec -e DISPLAY=:100 vatican-bot-chrome_bot_1-1 python3 /root/book_from_recording.py --date {date_str} --visitors {visitors}",
        "customer_email": email or "not specified",
    }, indent=2)

def tool_update_sheet(params: dict) -> str:
    """Write data to Google Sheets CRM."""
    action = params.get("action", "")
    try:
        from crm_intelligence.auto_snipe import CRMAutoSnipeService
        svc = CRMAutoSnipeService()
        svc.parser.connect()
        sheet = svc.parser._sheet

        if action == "write_payment_link":
            bid = params.get("booking_id", "")
            date_str = params.get("activity_date", "")
            link = params.get("payment_link", "")
            if not bid or not link:
                return "Error: booking_id and payment_link required"
            ok = svc.write_payment_link_to_sheet(bid, date_str, link)
            return f"✅ Payment link written for booking {bid}" if ok else f"❌ Failed to write for {bid}"

        elif action == "add_note":
            bid = params.get("booking_id", "")
            note = params.get("note", "")
            if not bid or not note: return "Error: booking_id and note required"
            # Find Activity_Lines sheet and matching row
            for ws in sheet.worksheets():
                if "activity" in ws.title.lower():
                    records = ws.get_all_records()
                    headers = ws.row_values(1)
                    # Find or create notes column
                    note_col = None
                    for i, h in enumerate(headers):
                        if "note" in str(h).lower(): note_col = i+1
                    if not note_col:
                        note_col = len(headers)+1
                        ws.update_cell(1, note_col, "notes")
                    # Find row and append note
                    for ri, rec in enumerate(records, start=2):
                        if str(rec.get("bookingId", "")) == bid:
                            existing = ws.cell(ri, note_col).value or ""
                            ws.update_cell(ri, note_col, f"{existing}\n{note}".strip())
                            return f"✅ Note added to booking {bid}"
                    return f"❌ Booking {bid} not found in sheet"

        elif action == "update_status":
            bid = params.get("booking_id", "")
            status = params.get("status", "")
            if not bid or not status: return "Error: booking_id and status required"
            for ws in sheet.worksheets():
                if "activity" in ws.title.lower():
                    records = ws.get_all_records()
                    headers = ws.row_values(1)
                    status_col = None
                    for i, h in enumerate(headers):
                        if "status" in str(h).lower(): status_col = i+1
                    if not status_col:
                        status_col = len(headers)+1
                        ws.update_cell(1, status_col, "status")
                    for ri, rec in enumerate(records, start=2):
                        if str(rec.get("bookingId", "")) == bid:
                            ws.update_cell(ri, status_col, status)
                            return f"✅ Status updated to '{status}' for booking {bid}"
                    return f"❌ Booking {bid} not found"

        elif action == "add_activity":
            product = params.get("product_title", "New Activity")
            cust_name = params.get("customer_name", "")
            cust_email = params.get("customer_email", "")
            date_str = params.get("activity_date", "")
            visitors = params.get("visitors", 2)
            for ws in sheet.worksheets():
                if "activity" in ws.title.lower():
                    headers = ws.row_values(1)
                    # Build row matching headers
                    new_row = []
                    for h in headers:
                        hl = str(h).lower()
                        if "product" in hl: new_row.append(product)
                        elif "date" in hl and "activity" in hl: new_row.append(date_str)
                        elif "customer" in hl and "name" in hl: new_row.append(cust_name)
                        elif "email" in hl: new_row.append(cust_email)
                        elif "pax" in hl or "participant" in hl: new_row.append(str(visitors))
                        elif "booking" in hl and "id" in hl: new_row.append(f"MANUAL-{int(time.time())}")
                        else: new_row.append("")
                    ws.append_row(new_row)
                    return f"✅ Activity added: {product} on {date_str} for {cust_name} ({visitors}pax)"
            return "❌ No activity sheet found"

        elif action == "list_sheets":
            sheets_info = []
            for ws in sheet.worksheets():
                sheets_info.append(f"  • {ws.title} ({ws.row_count} rows, {ws.col_count} cols)")
            return "📊 *CRM Sheets*\n\n" + "\n".join(sheets_info)

        elif action == "update_customer":
            email = params.get("customer_email", "").lower()
            name = params.get("customer_name", "")
            phone = params.get("customer_phone", "")
            if not email: return "Error: customer_email required"
            for ws in sheet.worksheets():
                if "booking" in ws.title.lower():
                    records = ws.get_all_records()
                    headers = ws.row_values(1)
                    for ri, rec in enumerate(records, start=2):
                        rec_email = str(rec.get("customerEmail", rec.get("email", ""))).lower()
                        if rec_email == email:
                            if name:
                                for i, h in enumerate(headers):
                                    if "name" in str(h).lower(): ws.update_cell(ri, i+1, name)
                            if phone:
                                for i, h in enumerate(headers):
                                    if "phone" in str(h).lower(): ws.update_cell(ri, i+1, phone)
                            return f"✅ Customer {email} updated"
                    return f"❌ Customer {email} not found in bookings"
            return "❌ No bookings sheet found"

        return f"Unknown action: {action}"

    except Exception as e:
        return f"Sheet error: {str(e)[:200]}"


def tool_collect_missing_info(params: dict = None) -> str:
    """Scan for missing info and WhatsApp customers."""
    try:
        from crm_intelligence.missing_info_collector import info_collector
        max_msgs = params.get("max_messages", 10) if params else 10
        return info_collector.collect_missing_info(max_messages=max_msgs)
    except Exception as e:
        return f"Missing info scan error: {e}"


def tool_get_revenue_report(params: dict) -> str:
    d = _crm()
    period = params.get("period", "month")
    breakdown = params.get("breakdown", "product")

    bookings = d.get("bookings", [])
    activities = d.get("activities", [])

    today = date.today()
    if period == "month": start = today.replace(day=1)
    elif period == "year": start = today.replace(month=1, day=1)
    else: start = date(2000, 1, 1)

    period_bookings = [b for b in bookings if b.get("date") and b["date"] >= start.strftime("%Y-%m-%d")]
    total = sum(float(b.get("total", 0) or 0) for b in period_bookings)

    result = {"period": period, "total_revenue": round(total, 2), "booking_count": len(period_bookings)}
    if breakdown == "product":
        result["by_product"] = {"vatican": len([a for a in activities if a.get("vatican")]),
                                "other": len([a for a in activities if not a.get("vatican")])}
    elif breakdown == "country":
        customers = d.get("customers", [])
        countries = {}
        for c in customers:
            co = c.get("country", "Unknown") or "Unknown"
            countries[co] = countries.get(co, 0) + 1
        result["by_country"] = dict(sorted(countries.items(), key=lambda x: -x[1])[:10])

    return json.dumps(result, indent=2)


TOOL_MAP = {
    "search_customers": tool_search_customers,
    "get_customer_detail": tool_get_customer_detail,
    "get_bookings_summary": tool_get_bookings_summary,
    "send_customer_message": tool_send_customer_message,
    "get_vatican_status": tool_get_vatican_status,
    "trigger_booking": tool_trigger_booking,
    "update_sheet": tool_update_sheet,
    "collect_missing_info": tool_collect_missing_info,
    "get_revenue_report": tool_get_revenue_report,
}

# ── AGENT LOOP ────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Hydra, an AI operations agent for a travel agency. You have access to the agency's CRM (Google Sheets), backend API, and booking system.

CAPABILITIES:
- Search customers by country, language, product, spending
- Get detailed customer profiles with booking history
- Check Vatican ticket availability and booking status
- Prepare customer messages (email-ready, multi-language)
- Generate revenue reports and booking summaries
- Trigger ticket bookings

RULES:
1. Always use the tools to get accurate data — never guess
2. When asked to "message" or "email" customers, use send_customer_message
3. Be proactive — if you see something urgent, mention it
4. Respond in the user's language
5. Keep responses concise and actionable
6. If a tool fails, explain what happened

Current date: """ + date.today().strftime("%Y-%m-%d")

def run_agent(user_query: str, chat_history: list = None) -> str:
    """Run the AI agent with tool access. Returns final response."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if chat_history:
        messages.extend(chat_history[-10:])  # Last 10 messages for context
    messages.append({"role": "user", "content": user_query})

    try:
        # First call — let AI decide if it needs tools
        resp = requests.post(DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": messages, "tools": TOOLS,
                  "temperature": 0.3, "max_tokens": 1000},
            timeout=20)

        if resp.status_code != 200:
            return f"❌ AI service error ({resp.status_code}). Try again."

        data = resp.json()
        msg = data["choices"][0]["message"]

        # If AI wants to call tools, execute them
        tool_calls = msg.get("tool_calls", [])
        if tool_calls:
            # Execute all requested tools
            messages.append(msg)  # Add assistant's tool call request
            for tc in tool_calls:
                func_name = tc["function"]["name"]
                func_args = json.loads(tc["function"]["arguments"])
                tool_fn = TOOL_MAP.get(func_name)
                if tool_fn:
                    try:
                        result = tool_fn(func_args)
                    except Exception as e:
                        result = f"Tool error: {e}"
                else:
                    result = f"Unknown tool: {func_name}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": str(result)[:4000],
                })

            # Second call — AI synthesizes final response with tool results
            resp2 = requests.post(DEEPSEEK_URL,
                headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": messages,
                      "temperature": 0.5, "max_tokens": 800},
                timeout=20)

            if resp2.status_code == 200:
                return resp2.json()["choices"][0]["message"]["content"]

        # No tools needed — return direct response
        return msg.get("content", "I couldn't process that. Try rephrasing.")

    except requests.exceptions.Timeout:
        return "⏳ Taking too long. Try simplifying your request."
    except Exception as e:
        logger.error(f"Agent error: {e}")
        return "❌ Something went wrong. Try again."


# Global agent instance
agent = run_agent
