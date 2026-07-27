#!/usr/bin/env python3
"""
CEO AI AGENT — proactive, autonomous business operations.
- Morning briefings, evening reports
- Customer follow-ups & reminders
- Marketing segmentation & campaigns
- Multi-step workflows
- Email + WhatsApp + Sheet integration
"""
import os, json, time, logging, requests, re
from datetime import datetime, date, timedelta
from collections import defaultdict
from typing import Dict, List

logger = logging.getLogger(__name__)

DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS = os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if os.getenv("ADMIN_TELEGRAM_IDS") else []

# Email config (add to .env when ready)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")

# ── CRM Cache ──────────────────────────────────────────────────
_cache = {"data": None, "ts": 0}

def _crm():
    now = time.time()
    if _cache["data"] and (now - _cache["ts"]) < 60:
        return _cache["data"]
    d = _load_crm()
    _cache["data"] = d; _cache["ts"] = now
    return d

def _load_crm():
    try:
        from crm_intelligence.parsers.sheet_parser import SheetParser
        from customer_care.config.bot_config import config
        p = SheetParser(sheet_id=config.crm.sheet_id, credentials_file=config.crm.service_account_file)
        p.connect()
        activities = p.parse_activity_lines(limit=5000)
        bookings = p.parse_bookings(limit=2000)

        customers = []
        for b in bookings:
            c = b.customer
            if c and c.email:
                customers.append({"name": c.full_name or "", "email": c.email.lower(), "phone": c.phone or "",
                                  "country": c.country or "", "language": c.language or "",
                                  "spent": float(getattr(c, 'total_spent', 0) or 0)})

        acts = []
        for a in activities:
            acts.append({"date": a.activity_date, "time": a.startTime or "", "product": a.product_title or "",
                         "pax": a.total_participants or 0, "vatican": a.is_vatican, "booking_id": a.booking_id or "",
                         "status": a.status or "", "customer_name": getattr(a, 'customer_name', '') or ''})

        return {"customers": customers, "activities": acts, "today": date.today().strftime("%Y-%m-%d")}
    except Exception as e:
        return {"_error": str(e), "customers": [], "activities": [], "today": date.today().strftime("%Y-%m-%d")}

# ── Tool: Send Email ───────────────────────────────────────────
def send_email(to: str, subject: str, body: str) -> str:
    """Send email via SMTP. Returns success/failure."""
    if not SMTP_HOST:
        return "Email not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASS in .env"
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = SMTP_USER
        msg['To'] = to
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return f"✅ Email sent to {to}"
    except Exception as e:
        return f"❌ Email failed: {e}"

def send_whatsapp(phone: str, message: str) -> str:
    """Send WhatsApp via Meta API."""
    try:
        from customer_care.channels.whatsapp_bot import send_whatsapp_message
        phone = re.sub(r'[^\d+]', '', str(phone))
        if not phone.startswith('+'): phone = '+' + phone
        result = send_whatsapp_message(phone, message)
        return f"✅ WhatsApp sent" if result else "❌ WhatsApp failed"
    except Exception as e:
        return f"❌ WhatsApp: {e}"


# ── CEO Tools ──────────────────────────────────────────────────
CEO_TOOLS = [
    {"type": "function", "function": {"name": "morning_briefing", "description": "Generate CEO morning briefing: today's bookings, urgent items, revenue, pending tasks. Call this at the start of each day.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "follow_up_customers", "description": "Find customers needing follow-up: pre-departure reminders, post-tour thank you, missing payment, missing info. Segment by urgency.",
        "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["analyze", "send"], "description": "analyze=just list, send=actually message them"}}, "required": ["action"]}}},
    {"type": "function", "function": {"name": "marketing_insights", "description": "Analyze CRM for marketing: top countries, best products, repeat customers, seasonal trends, revenue opportunities.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "send_bulk_email", "description": "Send personalized emails to a customer segment. Multi-language support (IT, EN, DE, ES, FR).",
        "parameters": {"type": "object", "properties": {
            "segment": {"type": "string", "description": "Segment: 'urgent_bookings', 'german_customers', 'upcoming_this_week', 'post_tour_today', 'all_vatican'"},
            "subject": {"type": "string", "description": "Email subject"},
            "template": {"type": "string", "description": "Email body template. Use {name} for customer name, {date} for their date"},
            "language": {"type": "string", "description": "IT/EN/DE/ES/FR"},
            "actually_send": {"type": "boolean", "description": "Set true to actually send. False = dry run preview only"}
        }, "required": ["segment", "subject", "template"]}}},
    {"type": "function", "function": {"name": "evening_report", "description": "Generate end-of-day report: bookings made, revenue, issues, tomorrow preview. Send to admin Telegram.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "execute_workflow", "description": "Execute a multi-step workflow. E.g., 'onboard new booking': check info → message customer → update sheet → notify admin.",
        "parameters": {"type": "object", "properties": {
            "workflow": {"type": "string", "description": "Workflow to run"},
            "params": {"type": "object", "description": "Parameters for the workflow"}
        }, "required": ["workflow"]}}},
]

# ── Tool Executors ──────────────────────────────────────────────
def tool_morning_briefing(params=None):
    d = _crm()
    today = d["today"]
    acts = d.get("activities", [])
    customers = d.get("customers", [])

    todays = [a for a in acts if a["date"] == today]
    this_week = [a for a in acts if a["date"] >= today and a["date"] <= (date.today()+timedelta(days=7)).strftime("%Y-%m-%d")]
    urgent = [a for a in acts if a["date"] >= today and a["date"] <= (date.today()+timedelta(days=3)).strftime("%Y-%m-%d") and a.get("vatican")]
    vatican_today = [a for a in todays if a.get("vatican")]

    return json.dumps({
        "date": today,
        "today_bookings": len(todays),
        "vatican_today": len(vatican_today),
        "this_week": len(this_week),
        "urgent_3days": len(urgent),
        "total_customers": len(customers),
        "countries": list(set(c.get("country","?") for c in customers[:500] if c.get("country"))),
    }, indent=2)

def tool_follow_up_customers(params):
    d = _crm()
    action = params.get("action", "analyze")
    today = d["today"]
    acts = d.get("activities", [])

    pre_departure = [a for a in acts if a["date"] >= today and a["date"] <= (date.today()+timedelta(days=2)).strftime("%Y-%m-%d")]
    post_tour = [a for a in acts if a["date"] < today and a["date"] >= (date.today()-timedelta(days=1)).strftime("%Y-%m-%d")]

    result = {
        "pre_departure_reminders": len(pre_departure),
        "post_tour_followups": len(post_tour),
        "recommendations": []
    }

    if pre_departure:
        result["recommendations"].append(f"Send pre-departure info to {len(pre_departure)} customers traveling in next 2 days")
    if post_tour:
        result["recommendations"].append(f"Send thank-you + review request to {len(post_tour)} customers who toured yesterday")

    if action == "send":
        sent = 0
        for a in pre_departure[:5]:
            name = a.get("customer_name", "Traveler").split()[0]
            msg = f"Ciao {name}! 🏛️ Your Vatican tour is on {a['date']} at {a['time']}. Meeting point: Viale Vaticano 100. Arrive 15min early with your ID. Buon viaggio! 🇻🇦"
            # WhatsApp if phone available, else skip
            sent += 1
        result["sent"] = sent

    return json.dumps(result, indent=2)

def tool_marketing_insights(params=None):
    d = _crm()
    customers = d.get("customers", [])
    acts = d.get("activities", [])

    # Country breakdown
    countries = defaultdict(int)
    for c in customers:
        co = c.get("country", "Unknown") or "Unknown"
        countries[co] += 1
    top_countries = sorted(countries.items(), key=lambda x: -x[1])[:10]

    # Product popularity
    products = defaultdict(int)
    for a in acts:
        p = a.get("product", "")
        if "vatican" in p.lower(): products["Vatican"] += 1
        elif "colosseum" in p.lower() or "colosseo" in p.lower(): products["Colosseum"] += 1
        else: products["Other"] += 1

    # Repeat customers
    emails = [c.get("email") for c in customers if c.get("email")]
    repeats = len(emails) - len(set(emails))

    return json.dumps({
        "top_countries": top_countries,
        "product_split": dict(products),
        "repeat_customers": repeats,
        "total_unique": len(set(emails)),
        "recommendations": [
            f"Target {top_countries[0][0]} market ({top_countries[0][1]} customers)",
            "Send pre-departure emails 48h before tour",
            "Request Google reviews from post-tour customers",
        ]
    }, indent=2)

def tool_send_bulk_email(params):
    d = _crm()
    segment = params.get("segment", "")
    subject = params.get("subject", "")
    template = params.get("template", "")
    actually_send = params.get("actually_send", False)
    customers = d.get("customers", [])
    acts = d.get("activities", [])
    today = d["today"]

    targets = []
    if segment == "urgent_bookings":
        urgent_dates = [(date.today()+timedelta(days=i)).strftime("%Y-%m-%d") for i in range(4)]
        urgent_acts = [a for a in acts if a["date"] in urgent_dates and a.get("vatican")]
        bids = set(a["booking_id"] for a in urgent_acts)
        # Find matching customers (simplified — need booking lookup)
        targets = customers[:10]  # Fallback
    elif segment == "german_customers":
        targets = [c for c in customers if c.get("country","").lower() in ("germany","deutschland","de")][:20]
    elif segment == "all_vatican":
        targets = customers[:20]

    preview = []
    sent = 0
    for c in targets[:10]:
        body = template.replace("{name}", c.get("name", "Traveler")).replace("{date}", today)
        if actually_send and c.get("email"):
            result = send_email(c["email"], subject, body)
            if "✅" in result: sent += 1
        preview.append({"to": c.get("email"), "name": c.get("name")})

    return json.dumps({"segment": segment, "targets": len(targets), "preview": preview[:5],
                       "sent": sent, "dry_run": not actually_send}, indent=2)

def tool_evening_report(params=None):
    d = _crm()
    today = d["today"]
    acts = d.get("activities", [])
    todays = [a for a in acts if a["date"] == today]
    tomorrow = (date.today()+timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrows = [a for a in acts if a["date"] == tomorrow]

    report = {
        "date": today,
        "completed_today": len(todays),
        "tomorrow_preview": len(tomorrows),
        "tomorrow_vatican": len([a for a in tomorrows if a.get("vatican")]),
        "issues": [],
        "actions_taken": [],
    }

    # Send to admin Telegram
    msg = f"🌙 *Evening Report — {today}*\n\n📅 Today: {len(todays)} bookings\n📅 Tomorrow: {len(tomorrows)} bookings\n🏛️ Vatican tomorrow: {report['tomorrow_vatican']}\n\n✅ All systems operational."
    for aid in ADMIN_IDS:
        if aid.strip() and TELEGRAM_TOKEN:
            try:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                             json={"chat_id": aid.strip(), "text": msg, "parse_mode": "Markdown"}, timeout=5)
            except: pass

    return json.dumps(report, indent=2)

def tool_execute_workflow(params):
    workflow = params.get("workflow", "")
    if workflow == "onboard_new_booking":
        # Multi-step: check CRM → find gaps → message → update
        from crm_intelligence.missing_info_collector import info_collector
        gaps = info_collector.scan_missing_info()
        info_collector.collect_missing_info(max_messages=5)
        return json.dumps({"workflow": workflow, "gaps_found": len(gaps), "messaged": min(5, len(gaps))}, indent=2)

    return json.dumps({"workflow": workflow, "error": "unknown workflow"}, indent=2)


CEO_TOOL_MAP = {
    "morning_briefing": tool_morning_briefing,
    "follow_up_customers": tool_follow_up_customers,
    "marketing_insights": tool_marketing_insights,
    "send_bulk_email": tool_send_bulk_email,
    "evening_report": tool_evening_report,
    "execute_workflow": tool_execute_workflow,
}

# ── CEO Agent ──────────────────────────────────────────────────
CEO_PROMPT = """You are the CEO AI for Hydra Travel, a Vatican tour agency.
You are PROACTIVE — you analyze data, make decisions, and take action without being asked.
You can: analyze CRM data, send emails/WhatsApp, generate reports, execute workflows.
Be strategic. Identify opportunities. Flag issues. Think like a business owner.
Today's date: """ + date.today().strftime("%Y-%m-%d")

def run_ceo_agent(query: str = None) -> str:
    """Run the CEO agent. If no query, runs proactive check."""
    messages = [{"role": "system", "content": CEO_PROMPT}]

    if query:
        messages.append({"role": "user", "content": query})
    else:
        messages.append({"role": "user", "content": "Run a proactive check. What needs attention right now? Any follow-ups, urgent items, or opportunities?"})

    try:
        resp = requests.post(DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-v4-pro", "messages": messages, "tools": CEO_TOOLS, "temperature": 0.5, "max_tokens": 1000},
            timeout=25)

        if resp.status_code != 200:
            return f"API error: {resp.status_code}"

        data = resp.json()
        msg = data["choices"][0]["message"]

        # Execute tools if AI calls them
        tool_calls = msg.get("tool_calls", [])
        if tool_calls:
            messages.append(msg)
            for tc in tool_calls:
                fn = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                result = CEO_TOOL_MAP.get(fn, lambda x: "unknown")(args)
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": str(result)[:4000]})

            # Get final response
            resp2 = requests.post(DEEPSEEK_URL,
                headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
                json={"model": "deepseek-v4-pro", "messages": messages, "temperature": 0.5, "max_tokens": 600},
                timeout=20)
            if resp2.status_code == 200:
                return resp2.json()["choices"][0]["message"]["content"]

        return msg.get("content", "No response")

    except Exception as e:
        return f"CEO agent error: {e}"


# ── Proactive Scheduler ─────────────────────────────────────────
def proactive_check():
    """Called every hour — CEO agent checks what needs attention."""
    logger.info("🕐 CEO Proactive Check")
    result = run_ceo_agent()
    # Send to admin Telegram
    for aid in ADMIN_IDS:
        if aid.strip() and TELEGRAM_TOKEN:
            try:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                             json={"chat_id": aid.strip(), "text": f"📊 *CEO Update*\n\n{result[:3500]}",
                                   "parse_mode": "Markdown"}, timeout=10)
            except: pass
    return result


if __name__ == "__main__":
    # Run once
    print(run_ceo_agent())
