"""
AI ADMIN ASSISTANT — Conversational CRM Interface
===================================================
Fast local handlers for known queries + DeepSeek for everything else.
CRM data cached for 60s for instant responses.
"""
import json, logging, os, re, time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
import requests

logger = logging.getLogger(__name__)

BACKEND = os.getenv("SERVER_BASE_URL", "http://backend:8000")
if not BACKEND.startswith("http"): BACKEND = f"http://{BACKEND}"

DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# ── Simple cache to avoid repeated CRM/API calls ──────────────────
_cache = {"data": None, "ts": 0, "ttl": 60}

def cached_crm_data():
    """Get full CRM snapshot, cached for 60 seconds."""
    now = time.time()
    if _cache["data"] and (now - _cache["ts"]) < _cache["ttl"]:
        return _cache["data"]
    data = _collect_crm_data()
    _cache["data"] = data
    _cache["ts"] = now
    return data

def _collect_crm_data():
    """Collect all CRM + backend data into one dict."""
    d = {"today": date.today().strftime("%Y-%m-%d"), "week": 0, "month_revenue": 0.0,
         "activities_today": [], "activities_week": [], "urgent_vatican": [],
         "upcoming_vatican": [], "held_slots": [], "payment_links": [],
         "customers": [], "products_vatican": 0, "total_bookings": 0}
    try:
        from crm_intelligence.parsers.sheet_parser import SheetParser
        from customer_care.config.bot_config import config
        parser = SheetParser(sheet_id=config.crm.sheet_id,
                            credentials_file=config.crm.service_account_file)
        parser.connect()

        # Activities
        activities = parser.parse_activity_lines(limit=5000)
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        for a in activities:
            adate = a.activity_date
            if adate == d["today"]:
                d["activities_today"].append({
                    "time": a.startTime or "", "product": a.product_title or "",
                    "pax": a.total_participants or 0, "vatican": a.is_vatican,
                    "booking_id": a.booking_id or "",
                })
            if adate and adate >= week_start.strftime("%Y-%m-%d"):
                d["activities_week"].append({"date": adate, "time": a.startTime or "",
                    "product": a.product_title or "", "pax": a.total_participants or 0})
                d["week"] += 1

            # Revenue from products
            if adate and adate >= month_start.strftime("%Y-%m-%d"):
                try:
                    from crm_intelligence.auto_snipe import CRMAutoSnipeService
                    # Quick revenue estimate
                except: pass

        # Bookings
        bookings = parser.parse_bookings(limit=1000)
        d["total_bookings"] = len(bookings)
        for b in bookings[:50]:
            if b.customer and b.customer.email:
                d["customers"].append({
                    "name": b.customer.full_name or "", "email": b.customer.email,
                    "phone": b.customer.phone or "", "country": b.customer.country or "",
                    "total_spent": float(getattr(b.customer, 'total_spent', 0) or 0),
                })

        # Products
        try:
            products = parser.parse_products()
            d["products_vatican"] = sum(1 for p in products if p.is_vatican)
        except: pass

        # Vatican targets
        try:
            from crm_intelligence.auto_snipe import CRMAutoSnipeService
            svc = CRMAutoSnipeService()
            targets = svc.scan_crm_for_targets()
            for t in targets:
                info = {"date": t.activity_date, "name": t.customer_name,
                        "visitors": t.visitors, "product": t.product_title[:50],
                        "days": t.days_until, "status": t.status}
                if t.days_until <= 3: d["urgent_vatican"].append(info)
                elif t.days_until <= 14: d["upcoming_vatican"].append(info)
        except: pass

        # Backend: held slots + payments
        try:
            r = requests.get(f"{BACKEND}/api/v1/holds/", params={"status": "all"}, timeout=5)
            if r.status_code == 200:
                results = r.json()
                if isinstance(results, dict): results = results.get("results", [])
                for h in results[:20]:
                    slot_info = {"id": h.get("id"), "date": h.get("date"),
                                 "time": h.get("time_slot"), "status": h.get("status"),
                                 "visitors": h.get("visitors")}
                    d["held_slots"].append(slot_info)
                    if h.get("payment_link"):
                        d["payment_links"].append({
                            "id": h.get("id"), "date": h.get("date"),
                            "link": h.get("payment_link", "")[:120],
                        })
        except: pass

        # Revenue estimate
        try:
            d["month_revenue"] = sum(
                float(getattr(b, 'total_price', 0) or 0)
                for b in bookings
                if getattr(b, 'booking_date', '') and b.booking_date >= month_start.strftime("%Y-%m-%d")
            )
        except: pass

    except Exception as e:
        d["_error"] = str(e)[:100]
    return d


class AdminAssistant:
    """AI assistant — fast local handlers + DeepSeek for complex queries."""

    def handle_query(self, query: str) -> str:
        q = query.strip()
        if len(q) < 2: return "👋 Hi! Ask me anything about your travel agency."

        # ── Chitchat (no API call) ──
        lo = q.lower()
        if lo in ("hi","hello","hey","yo","ciao","salve"): return "👋 Hello! Ask me about bookings, revenue, customers, or anything about your agency."
        if lo in ("thanks","thx","thank you","grazie"): return "😊 You're welcome!"
        if lo in ("ok","okay","k"): return "👍"

        # ── Fast local handlers ──
        result = self._local_handler(q)
        if result: return result

        # ── DeepSeek for everything else ──
        return self._ask_deepseek(q)

    # ── Local handlers (instant, no API cost) ────────────────────

    def _local_handler(self, q: str) -> Optional[str]:
        lo = q.lower()
        data = cached_crm_data()

        # Today's bookings
        if any(w in lo for w in ("today","oggi")):
            acts = data.get("activities_today", [])
            if not acts: return "📅 *Today*: No activities scheduled."
            vatican = [a for a in acts if a.get("vatican")]
            msg = f"📅 *Today — {len(acts)} activities*\n\n"
            for a in sorted(acts, key=lambda x: x["time"])[:15]:
                icon = "🏛️" if a["vatican"] else "📋"
                msg += f"  {icon} {a['time']} — {a['product'][:40]} ({a['pax']}pax)\n"
            if len(acts) > 15: msg += f"\n_+{len(acts)-15} more_"
            if vatican: msg += f"\n\n🏛️ *Vatican today:* {len(vatican)} bookings"
            return msg

        # This week
        if any(w in lo for w in ("week","settimana","this week")):
            week = data.get("activities_week", [])
            if not week: return "📅 *This week*: No activities."
            by_day = {}
            for a in week:
                d = a["date"]; by_day.setdefault(d, []).append(a)
            msg = f"📅 *This Week — {len(week)} activities*\n\n"
            for d in sorted(by_day.keys())[:7]:
                msg += f"*{d}*: {len(by_day[d])} activities\n"
            return msg

        # Revenue
        if any(w in lo for w in ("revenue","income","sales","money","earned","ricavi","fatturato")):
            rev = data.get("month_revenue", 0)
            today_count = len(data.get("activities_today", []))
            return (
                f"💰 *Revenue — {date.today().strftime('%B %Y')}*\n\n"
                f"📊 Month-to-date revenue: *€{rev:,.2f}*\n"
                f"📅 Today's activities: *{today_count}*\n"
                f"📋 Total bookings: *{data.get('total_bookings', 0)}*\n\n"
                f"_Estimated from CRM booking totals._"
            )

        # Pending / urgent Vatican
        if any(w in lo for w in ("pending","unsniped","urgent","pendenti","urgente","need ticket")):
            urgent = data.get("urgent_vatican", [])
            upcoming = data.get("upcoming_vatican", [])
            if not urgent and not upcoming: return "✅ *No pending Vatican bookings!*"
            msg = "🎯 *Vatican Snipe Status*\n\n"
            if urgent:
                msg += f"🔴 *Urgent (≤3 days): {len(urgent)}*\n"
                for t in urgent[:8]:
                    msg += f"  • {t['date']} — {t['name']} ({t['visitors']}v)\n"
            if upcoming:
                msg += f"\n🟡 *Upcoming (4-14d): {len(upcoming)}*\n"
                for t in upcoming[:5]:
                    msg += f"  • {t['date']} — {t['name']} ({t['visitors']}v)\n"
            return msg

        # Held slots
        if any(w in lo for w in ("holds","held","locked","slot","bloccati")):
            holds = data.get("held_slots", [])
            if not holds: return "🔓 *No slots currently held.*"
            msg = f"🔒 *Held Slots — {len(holds)}*\n\n"
            for h in holds[:10]:
                msg += f"  • #{h['id']} — {h['date']} {h['time']} — {h['visitors']}v — {h['status']}\n"
            return msg

        # Payment links
        if any(w in lo for w in ("payment","pay","epay","pagamento","link","pagare")):
            links = data.get("payment_links", [])
            if not links: return "💳 *No payment links yet.* Completed bookings will appear here."
            msg = f"💳 *Payment Links — {len(links)}*\n\n"
            for l in links[:8]:
                msg += f"  • #{l['id']} {l['date']} — [Open Payment]({l['link']})\n"
            return msg

        # Customer lookup
        em = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', q)
        if em:
            email = em.group(0).lower()
            matches = [c for c in data.get("customers", []) if c.get("email","").lower() == email]
            if not matches: return f"❌ No customer found with `{email}`"
            c = matches[0]
            return (
                f"👤 *{c['name']}*\n\n"
                f"📧 `{c['email']}`\n📞 {c['phone']}\n🌍 {c['country']}\n"
                f"💶 Total spent: €{c['total_spent']:,.2f}"
            )

        # Status / dashboard
        if any(w in lo for w in ("status","overview","dashboard","stato","stats")):
            return (
                f"📊 *Agency Dashboard*\n\n"
                f"📅 Today: *{len(data.get('activities_today',[]))}* activities\n"
                f"📅 This week: *{data.get('week',0)}* activities\n"
                f"📋 Total bookings: *{data.get('total_bookings',0)}*\n"
                f"🏛️ Vatican products: *{data.get('products_vatican',0)}*\n"
                f"🔒 Held slots: *{len(data.get('held_slots',[]))}*\n"
                f"🔴 Urgent snipes: *{len(data.get('urgent_vatican',[]))}*\n"
                f"💳 Payment links: *{len(data.get('payment_links',[]))}*\n\n"
                f"_Ask me anything — `daily report` for full details_"
            )

        # Help
        if any(w in lo for w in ("help","aiuto","commands","comandi","what can you do")):
            return (
                "🤖 *Admin Assistant*\n\n"
                "Just type naturally:\n"
                "• `bookings today` / `this week`\n"
                "• `revenue` / `what's pending?`\n"
                "• `held slots` / `payment links`\n"
                "• `customer email@...`\n"
                "• `status` / `dashboard`\n\n"
                "Or ask anything — I'll use DeepSeek AI to answer from your CRM data."
            )

        # Booking trigger — only standalone "book", not "booking" or "bookings"
        if any(w in lo.split() for w in ("/book","book now","book a","book for","prenota","buy ticket","snipe")):
            return (
                "🚀 *Auto-Booking Active*\n\n"
                "The system scans CRM every 5 minutes and books automatically.\n\n"
                "*Manual booking:* SSH to server:\n"
                "`docker exec -e DISPLAY=:100 vatican-bot-chrome_bot_1-1 python3 /root/book_from_recording.py --date DD/MM/YYYY`\n\n"
                "Commands: `/add` `/snipes` `/holds` `/status`"
            )

        return None  # Let DeepSeek handle it

    # ── DeepSeek conversational AI ───────────────────────────────

    def _ask_deepseek(self, query: str) -> str:
        try:
            data = cached_crm_data()
            context = json.dumps({
                "today": data.get("today"),
                "today_activities": len(data.get("activities_today", [])),
                "this_week": data.get("week", 0),
                "total_bookings": data.get("total_bookings", 0),
                "month_revenue": f"€{data.get('month_revenue', 0):,.2f}",
                "urgent_vatican": len(data.get("urgent_vatican", [])),
                "upcoming_vatican": len(data.get("upcoming_vatican", [])),
                "held_slots": len(data.get("held_slots", [])),
                "payment_links": len(data.get("payment_links", [])),
                "vatican_products": data.get("products_vatican", 0),
                "customers": data.get("customers", [])[:30],
                "urgent_details": data.get("urgent_vatican", [])[:5],
                "held_details": data.get("held_slots", [])[:5],
                "payment_details": data.get("payment_links", [])[:5],
            }, default=str)

            resp = requests.post(DEEPSEEK_URL,
                headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": (
                            "You are an admin assistant for a travel agency. Answer concisely, use emojis, "
                            "be friendly. You have access to the agency's CRM data below. Answer based on this data. "
                            "If data doesn't cover the question, be honest. Keep responses under 400 words.\n\n"
                            f"CURRENT CRM DATA:\n{json.dumps(context, indent=2)}"
                        )},
                        {"role": "user", "content": query},
                    ],
                    "temperature": 0.7, "max_tokens": 600,
                }, timeout=15)

            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            return "🤔 I couldn't process that. Try `help` to see what I can do."

        except requests.exceptions.Timeout:
            return "⏳ Taking too long. Try a specific command like `status` or `daily report`."
        except Exception as e:
            logger.error(f"DeepSeek: {e}")
            return "❌ Something went wrong. Try again or use `help` for commands."


# Global instance
admin_assistant = AdminAssistant()
