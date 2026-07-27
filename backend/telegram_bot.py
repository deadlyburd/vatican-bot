"""
Telegram Bot for Vatican Monitor Management
State managed via context.user_data['step'] - no ConversationHandler state confusion.
"""
import os
import sys
import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember, ChatMemberUpdated
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ChatMemberHandler, filters
)

# AI Admin Assistant — natural language CRM queries
from crm_intelligence.admin_ai import admin_assistant  # Fast local handlers
from crm_intelligence.agent import run_agent  # Full AI agent with tools

# Setup Django
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

from django.utils import timezone
from monitors.models import MonitorTask, Agency, TelegramGroup, User
from backend.services.ai_agent import get_ai_agent

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set!")


# ── Keyboards ────────────────────────────────────────────────────────────────

def kb_main():
    """Simplified main menu - synced with extension workflow"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎫 Create Monitor", callback_data='add')],
        [InlineKeyboardButton("📊 View Status", callback_data='snipes')],
        [InlineKeyboardButton("👤 Set Profile", callback_data='setprofile_start')],
        [InlineKeyboardButton("ℹ️ Help", callback_data='help')],
    ])

def kb_calendar(year: int, month: int):
    """Build a month-view calendar keyboard."""
    import calendar
    today = datetime.now().date()

    # Header: month name + year
    month_name = datetime(year, month, 1).strftime('%B %Y')
    rows = [
        # Navigation row
        [
            InlineKeyboardButton("◀️", callback_data=f'cal:prev:{year}:{month}'),
            InlineKeyboardButton(f"📅 {month_name}", callback_data='cal:ignore'),
            InlineKeyboardButton("▶️", callback_data=f'cal:next:{year}:{month}'),
        ],
        # Day-of-week header
        [InlineKeyboardButton(d, callback_data='cal:ignore') for d in ['Mo','Tu','We','Th','Fr','Sa','Su']],
    ]

    # Fill calendar grid
    cal = calendar.monthcalendar(year, month)
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data='cal:ignore'))
            else:
                d = datetime(year, month, day).date()
                if d <= today:
                    # Past/today - not selectable
                    row.append(InlineKeyboardButton(f"·{day}", callback_data='cal:ignore'))
                else:
                    date_str = d.strftime('%Y-%m-%d')
                    row.append(InlineKeyboardButton(str(day), callback_data=f'date:{date_str}'))
        rows.append(row)

    rows.append([InlineKeyboardButton("❌ Cancel", callback_data='cancel')])
    return InlineKeyboardMarkup(rows)

def kb_visitors_adults():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(i), callback_data=f'vis_a:{i}') for i in range(1, 6)],
        [InlineKeyboardButton(str(i), callback_data=f'vis_a:{i}') for i in range(6, 11)],
        [InlineKeyboardButton("❌ Cancel", callback_data='cancel')],
    ])

def kb_visitors_children():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(i), callback_data=f'vis_c:{i}') for i in range(0, 5)],
        [InlineKeyboardButton(str(i), callback_data=f'vis_c:{i}') for i in range(5, 11)],
        [InlineKeyboardButton("❌ Cancel", callback_data='cancel')],
    ])

def kb_ticket():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎫 Standard Entry", callback_data='ticket:standard')],
        [InlineKeyboardButton("👥 Guided Tour",    callback_data='ticket:guided')],
        [InlineKeyboardButton("❌ Cancel",          callback_data='cancel')],
    ])

def kb_tier(plan='free'):
    """Two tiers: Notify or Snipe. Hold removed — Vatican doesn't support server-side holds."""
    rows = [[InlineKeyboardButton("🔔 Notify Only — alert when slot opens", callback_data='tier:notify')]]
    if plan == 'agency':
        rows.append([InlineKeyboardButton("⚡ Snipe — auto-book instantly", callback_data='tier:snipe')])
    else:
        rows.append([InlineKeyboardButton("⚡ Snipe — Agency plan required 🔐", callback_data='tier:locked_snipe')])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data='cancel')])
    return InlineKeyboardMarkup(rows)

def kb_language():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English",  callback_data='lang:ENG')],
        [InlineKeyboardButton("🇮🇹 Italiano", callback_data='lang:ITA')],
        [InlineKeyboardButton("🇫🇷 Français", callback_data='lang:FRA')],
        [InlineKeyboardButton("🇩🇪 Deutsch",  callback_data='lang:DEU')],
        [InlineKeyboardButton("🇪🇸 Español",  callback_data='lang:SPA')],
        [InlineKeyboardButton("❌ Cancel",     callback_data='cancel')],
    ])

def kb_times(selected=None):
    """Exact Vatican time slots — tap to toggle, Done when ready."""
    selected = selected or []
    slots = ['08:00','08:30','09:00','09:30','10:00','10:30','11:00','11:30',
             '12:00','12:30','13:00','13:30','14:00','14:30',
             '15:00','15:30','16:00','16:30','17:00','17:30']
    rows = []
    for i in range(0, len(slots), 3):
        row = []
        for t in slots[i:i+3]:
            check = '✅ ' if t in selected else ''
            row.append(InlineKeyboardButton(f"{check}{t}", callback_data=f'time:{t}'))
        rows.append(row)
    # Bottom row
    done_label = f"✅ Done ({len(selected)} selected)" if selected else "⏰ Any Time"
    done_data = 'time:done' if selected else 'time:any'
    rows.append([InlineKeyboardButton(done_label, callback_data=done_data)])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data='cancel')])
    return InlineKeyboardMarkup(rows)

def kb_confirm():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data='confirm')],
        [InlineKeyboardButton("❌ Cancel",  callback_data='cancel')],
    ])

def kb_back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='menu')]])


# ── Helpers ──────────────────────────────────────────────────────────────────

async def get_agency(chat_id):
    from asgiref.sync import sync_to_async

    def _lookup():
        # 1. Check approved group with agency linked
        group = TelegramGroup.objects.filter(
            chat_id=str(chat_id),
            status='approved',
            agency__isnull=False
        ).select_related('agency').first()
        if group:
            return group.agency

        # 2. Check approved group without agency — still allow access, use first agency
        group_no_agency = TelegramGroup.objects.filter(
            chat_id=str(chat_id),
            status='approved',
        ).first()
        if group_no_agency:
            # Link to first available agency automatically
            first_agency = Agency.objects.filter(
                is_active=True
            ).exclude(plan='system').first()
            if first_agency:
                group_no_agency.agency = first_agency
                group_no_agency.save(update_fields=['agency'])
                return first_agency

        # 3. Check Agency.telegram_chat_id (legacy)
        agency = Agency.objects.filter(telegram_chat_id=str(chat_id)).first()
        if agency:
            return agency

        # 4. Admin personal chat — always allow access
        admin_ids = [a.strip() for a in os.getenv('ADMIN_TELEGRAM_IDS', '').split(',') if a.strip()]
        if str(chat_id) in admin_ids:
            # Create a personal group entry for admin if not exists
            group, created = TelegramGroup.objects.get_or_create(
                chat_id=str(chat_id),
                defaults={
                    'chat_type': 'private',
                    'chat_title': 'Admin',
                    'status': 'approved',
                    'notification_enabled': True,
                }
            )
            if not group.agency:
                first_agency = Agency.objects.filter(
                    is_active=True
                ).exclude(plan='system').first()
                if first_agency:
                    group.agency = first_agency
                    group.save(update_fields=['agency'])
                    return first_agency
            return group.agency

        return None

    return await sync_to_async(_lookup)()

def summary(ud):
    lang_names = {'ENG':'🇬🇧 English','ITA':'🇮🇹 Italiano','FRA':'🇫🇷 Français','DEU':'🇩🇪 Deutsch','SPA':'🇪🇸 Español'}
    tier_icons = {'notify': '🔔 Notify Only', 'snipe': '⚡ Snipe'}
    lines = [
        f"📅 Date: {ud.get('date','—')}",
        f"👥 Visitors: {ud.get('visitors','—')} ({ud.get('adult_count',0)} Adults, {ud.get('child_count',0)} Children)",
        f"🎫 Ticket: {ud.get('ticket_label','—')}",
    ]
    if ud.get('language'):
        lines.append(f"🌍 Language: {lang_names.get(ud['language'], ud['language'])}")
    lines.append(f"🎯 Mode: {tier_icons.get(ud.get('tier','notify'), ud.get('tier','notify'))}")
    if ud.get('snipe_participants'):
        names = ', '.join(f"{p['first_name']} {p['last_name']}" for p in ud['snipe_participants'])
        lines.append(f"👤 Participants: {names}")
    if ud.get('checkout_method'):
        m = ud['checkout_method']
        lines.append(f"⚙️ Checkout: {'🚀 API' if m == 'api' else '🌐 Playwright'}")
    if ud.get('agent_target'):
        lines.append(f"🖥️ Agent: `{ud['agent_target']}`")
    lines.append(f"⏰ Time: {ud.get('times_label','Any')}")
    return '\n'.join(lines)


# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    agency = await get_agency(chat_id)
    if not agency:
        admin_ids = [a.strip() for a in os.getenv('ADMIN_TELEGRAM_IDS', '').split(',') if a.strip()]
        is_admin = str(chat_id) in admin_ids
        await update.message.reply_text(
            f"⚠️ This chat is not linked to an agency.\n\n"
            f"Chat ID: `{chat_id}`\n"
            f"{'✅ You are admin — but no agencies exist yet.' if is_admin else 'Contact admin to link it.'}\n\n"
            f"Admin: send `/pending` to see pending groups.",
            parse_mode='Markdown'
        )
        return
    context.user_data.clear()
    context.user_data['agency_id'] = agency.id
    context.user_data['agency_name'] = agency.name
    context.user_data['agency_plan'] = agency.plan
    await update.message.reply_text(
        f"🏛️ *Vatican Monitor Bot*\n"
        f"Agency: {agency.name}\n\n"
        f"*Quick Start:*\n"
        f"1️⃣ Set your profile (one time)\n"
        f"2️⃣ Create a monitor for your date\n"
        f"3️⃣ Install browser extension\n"
        f"4️⃣ Extension books automatically!\n\n"
        f"What would you like to do?",
        parse_mode='Markdown',
        reply_markup=kb_main()
    )


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/add — shortcut to jump straight into adding a snipe/monitor task."""
    chat_id = update.effective_chat.id
    agency = await get_agency(chat_id)
    if not agency:
        await update.message.reply_text("⚠️ Chat not linked to an agency. Send /start first.")
        return
    ud = context.user_data
    ud.clear()
    ud['agency_id'] = agency.id
    ud['agency_name'] = agency.name
    ud['agency_plan'] = agency.plan
    ud['step'] = 'date'
    now = datetime.now()
    await update.message.reply_text(
        "📅 Pick a date to monitor/snipe:",
        reply_markup=kb_calendar(now.year, now.month)
    )


# ── Master callback handler ───────────────────────────────────────────────────

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from asgiref.sync import sync_to_async
    query = update.callback_query
    await query.answer()
    data = query.data
    ud = context.user_data

    # ── Admin: approve/reject from notification buttons ──
    if data.startswith("admin_approve:") or data.startswith("admin_reject:"):
        admin_ids = [a.strip() for a in os.getenv('ADMIN_TELEGRAM_IDS', '').split(',') if a.strip()]
        if str(update.effective_user.id) not in admin_ids:
            await query.edit_message_text("⛔ Not authorized.")
            return

        action, group_chat_id = data.split(":", 1)

        if action == "admin_reject":
            @sync_to_async
            def do_reject():
                g = TelegramGroup.objects.filter(chat_id=group_chat_id).first()
                if g:
                    g.status = 'rejected'
                    g.save()
                return g
            g = await do_reject()
            await query.edit_message_text(f"❌ Rejected: {g.chat_title if g else group_chat_id}")
            return

        # Approve → show agency list + create new option
        agencies = await sync_to_async(list)(Agency.objects.filter(is_active=True).exclude(plan='system'))
        kb = [[InlineKeyboardButton(f"🏢 {a.name} ({a.plan})", callback_data=f"admin_link:{group_chat_id}:{a.id}")] for a in agencies]
        kb.append([InlineKeyboardButton("➕ Create New Agency", callback_data=f"admin_new_agency:{group_chat_id}")])
        kb.append([InlineKeyboardButton("⏭ Approve without agency", callback_data=f"admin_link:{group_chat_id}:0")])

        group_title = await sync_to_async(lambda: TelegramGroup.objects.filter(chat_id=group_chat_id).values_list('chat_title', flat=True).first())()
        await query.edit_message_text(
            f"✅ Approving: *{group_title}*\n\nLink to which agency?",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # ── Admin: link group to existing agency ──
    if data.startswith("admin_link:"):
        admin_ids = [a.strip() for a in os.getenv('ADMIN_TELEGRAM_IDS', '').split(',') if a.strip()]
        if str(update.effective_user.id) not in admin_ids:
            await query.edit_message_text("⛔ Not authorized.")
            return
        parts = data.split(":")
        group_chat_id = parts[1]
        agency_id = parts[2]

        @sync_to_async
        def do_link():
            from django.utils import timezone as dj_timezone
            group = TelegramGroup.objects.filter(chat_id=group_chat_id).first()
            if not group:
                return None, None
            group.status = 'approved'
            group.approved_at = dj_timezone.now()
            group.approved_by = str(update.effective_user.id)
            group.notification_enabled = True
            agency = None
            if agency_id != '0':
                agency = Agency.objects.filter(id=int(agency_id)).first()
                group.agency = agency
            group.save()
            return group, agency

        group, agency = await do_link()
        if not group:
            await query.edit_message_text("❌ Group not found.")
            return

        agency_name = agency.name if agency else "No agency"
        await query.edit_message_text(f"✅ *{group.chat_title}* approved → {agency_name}", parse_mode='Markdown')
        try:
            await context.bot.send_message(
                chat_id=group_chat_id,
                text="✅ *Your group has been approved!*\n\nYou will now receive Vatican ticket notifications.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify group: {e}")

        # Offer plan change inline
        if agency:
            plan_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🆓 Free",    callback_data=f"admin_setplan:{agency.id}:free"),
                InlineKeyboardButton("⭐ Pro",     callback_data=f"admin_setplan:{agency.id}:pro"),
                InlineKeyboardButton("🏢 Agency",  callback_data=f"admin_setplan:{agency.id}:agency"),
            ]])
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"🎯 Set plan for *{agency.name}* (current: `{agency.plan}`)",
                parse_mode='Markdown',
                reply_markup=plan_kb
            )
        return

    # ── Admin: start new agency creation flow ──
    if data.startswith("admin_new_agency:"):
        admin_ids = [a.strip() for a in os.getenv('ADMIN_TELEGRAM_IDS', '').split(',') if a.strip()]
        if str(update.effective_user.id) not in admin_ids:
            await query.edit_message_text("⛔ Not authorized.")
            return
        group_chat_id = data.split(":", 1)[1]
        # Store in user_data and ask for agency name
        ud['admin_creating_agency'] = {'group_chat_id': group_chat_id, 'step': 'name'}
        await query.edit_message_text(
            "➕ *Create New Agency*\n\nStep 1/3 — Send the *agency name*:",
            parse_mode='Markdown'
        )
        return

    # ── Admin: plan selection during agency creation ──
    if data.startswith("admin_agency_plan:"):
        admin_ids = [a.strip() for a in os.getenv('ADMIN_TELEGRAM_IDS', '').split(',') if a.strip()]
        if str(update.effective_user.id) not in admin_ids:
            return
        plan = data.split(":", 1)[1]
        ac = ud.get('admin_creating_agency', {})
        ac['plan'] = plan
        ud['admin_creating_agency'] = ac

        @sync_to_async
        def create_agency_and_user():
            import secrets, hashlib
            from django.utils import timezone as dj_timezone
            agency = Agency.objects.create(
                name=ac['agency_name'],
                api_key=secrets.token_hex(16),
                plan=plan,
                is_active=True
            )
            salt = secrets.token_hex(16)
            hashed = hashlib.sha256((ac['password'] + salt).encode()).hexdigest()
            user = User.objects.create(
                username=ac['username'],
                email=f"{ac['username']}@hydrabot.it",
                password_hash=salt + '$' + hashed,
                agency=agency,
                is_active=True,
                is_admin=True
            )
            # Link group
            group = TelegramGroup.objects.filter(chat_id=ac['group_chat_id']).first()
            if group:
                group.status = 'approved'
                group.approved_at = dj_timezone.now()
                group.approved_by = str(update.effective_user.id)
                group.notification_enabled = True
                group.agency = agency
                group.save()
            return agency, user, group

        agency, user, group = await create_agency_and_user()
        ud.pop('admin_creating_agency', None)

        await query.edit_message_text(
            f"✅ *Agency Created & Group Approved!*\n\n"
            f"🏢 Agency: *{agency.name}* ({plan})\n"
            f"👤 Username: `{user.username}`\n"
            f"🔑 Password: `{ac['password']}`\n"
            f"🔗 Group: {group.chat_title if group else ac['group_chat_id']}\n\n"
            f"Share these credentials with the agency.",
            parse_mode='Markdown'
        )
        try:
            await context.bot.send_message(
                chat_id=ac['group_chat_id'],
                text="✅ *Your group has been approved!*\n\nYou will now receive Vatican ticket notifications.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify group: {e}")
        return

    # ── Admin: change plan for an existing agency ──
    if data.startswith("admin_setplan:"):
        admin_ids = [a.strip() for a in os.getenv('ADMIN_TELEGRAM_IDS', '').split(',') if a.strip()]
        if str(update.effective_user.id) not in admin_ids:
            await query.answer("⛔ Not authorized.", show_alert=True)
            return
        _, agency_id_str, new_plan = data.split(":")

        @sync_to_async
        def do_set_plan():
            a = Agency.objects.filter(id=int(agency_id_str)).first()
            if a:
                a.plan = new_plan
                a.save(update_fields=['plan'])
            return a

        a = await do_set_plan()
        plan_labels = {'free': '🆓 Free', 'pro': '⭐ Pro', 'agency': '🏢 Agency'}
        await query.edit_message_text(
            f"✅ Plan updated: *{a.name}* → {plan_labels.get(new_plan, new_plan)}",
            parse_mode='Markdown'
        )
        return

    # Ensure agency is loaded
    if 'agency_id' not in ud:
        agency = await get_agency(update.effective_chat.id)
        if not agency:
            await query.edit_message_text("⚠️ Chat not linked. Contact admin.")
            return
        ud['agency_id'] = agency.id
        ud['agency_name'] = agency.name
        ud['agency_plan'] = agency.plan

    # ── Menu ──
    if data in ('menu', 'back'):
        ud['step'] = None
        await query.edit_message_text(
            f"🏛️ *Vatican Monitor Bot*\n"
            f"Agency: {ud['agency_name']}\n\n"
            f"*Quick Start:*\n"
            f"1️⃣ Set your profile (one time)\n"
            f"2️⃣ Create a monitor for your date\n"
            f"3️⃣ Install browser extension\n"
            f"4️⃣ Extension books automatically!\n\n"
            f"What would you like to do?",
            parse_mode='Markdown',
            reply_markup=kb_main()
        )
        return

    if data == 'cancel':
        ud['step'] = None
        await query.edit_message_text("❌ Cancelled.", reply_markup=kb_back())
        return

    # ── Add flow ──
    if data == 'add':
        ud['step'] = 'date'
        # Reset state for fresh monitor
        ud.pop('selected_times', None)
        ud.pop('preferred_times', None)
        ud.pop('snipe_participants', None)
        ud.pop('adult_count', None)
        ud.pop('child_count', None)
        ud.pop('visitors', None)
        
        now = datetime.now()
        await query.edit_message_text(
            "📅 Pick a date:",
            reply_markup=kb_calendar(now.year, now.month)
        )
        return

    # Calendar navigation
    if data.startswith('cal:'):
        parts = data.split(':')
        action = parts[1]
        if action == 'ignore':
            return
        year, month = int(parts[2]), int(parts[3])
        if action == 'prev':
            month -= 1
            if month < 1:
                month = 12; year -= 1
        elif action == 'next':
            month += 1
            if month > 12:
                month = 1; year += 1
        await query.edit_message_text(
            "📅 Pick a date:",
            reply_markup=kb_calendar(year, month)
        )
        return

    if data == 'date:manual':
        ud['step'] = 'date_text'
        await query.edit_message_text(
            "✏️ Type the date in YYYY-MM-DD format\nExample: 2026-06-15\n\nOr /cancel to go back."
        )
        return

    if data.startswith('date:'):
        date_val = data.split(':', 1)[1]
        ud['date'] = date_val
        ud['step'] = 'visitors_a'
        await query.edit_message_text(
            f"✅ Date: {date_val}\n\n👥 How many *Adults*?",
            parse_mode='Markdown',
            reply_markup=kb_visitors_adults()
        )
        return

    if data.startswith('vis_a:'):
        ud['adult_count'] = int(data.split(':')[1])
        ud['step'] = 'visitors_c'
        await query.edit_message_text(
            f"✅ Date: {ud['date']}\n✅ Adults: {ud['adult_count']}\n\n👥 How many *Children* (6-18y)?",
            parse_mode='Markdown',
            reply_markup=kb_visitors_children()
        )
        return

    if data.startswith('vis_c:'):
        ud['child_count'] = int(data.split(':')[1])
        ud['visitors'] = ud['adult_count'] + ud['child_count']
        ud['step'] = 'ticket'
        await query.edit_message_text(
            f"✅ Date: {ud['date']}\n✅ Visitors: {ud['visitors']} ({ud['adult_count']}A, {ud['child_count']}C)\n\n🎫 Select ticket type:",
            reply_markup=kb_ticket()
        )
        return

    if data == 'ticket:standard':
        ud['ticket_type'] = 0
        ud['ticket_name'] = "Musei Vaticani - Biglietti d'ingresso"
        ud['ticket_label'] = 'Standard Entry'
        ud['language'] = None
        ud['step'] = 'tier'
        await query.edit_message_text(
            f"✅ Date: {ud['date']}\n✅ Visitors: {ud['visitors']}\n✅ Ticket: Standard Entry\n\n🎯 Select monitoring mode:",
            reply_markup=kb_tier(ud.get('agency_plan', 'free'))
        )
        return

    if data == 'ticket:guided':
        ud['ticket_type'] = 1
        ud['ticket_name'] = 'Musei Vaticani - Visite Guidate'
        ud['ticket_label'] = 'Guided Tour'
        ud['step'] = 'language'
        await query.edit_message_text(
            f"✅ Date: {ud['date']}\n✅ Visitors: {ud['visitors']}\n✅ Ticket: Guided Tour\n\n🌍 Select language:",
            reply_markup=kb_language()
        )
        return

    if data.startswith('lang:'):
        lang = data.split(':')[1]
        ud['language'] = lang
        ud['ticket_name'] = f'Musei Vaticani - Visite Guidate ({lang})'
        ud['step'] = 'tier'
        await query.edit_message_text(
            f"✅ Date: {ud['date']}\n✅ Visitors: {ud['visitors']}\n✅ Ticket: Guided Tour ({lang})\n\n🎯 Select monitoring mode:",
            reply_markup=kb_tier(ud.get('agency_plan', 'free'))
        )
        return

    if data.startswith('time:'):
        slot = data.split(':', 1)[1]
        selected = ud.get('selected_times', [])

        if slot == 'any':
            # Any time — clear selection and confirm
            ud['preferred_times'] = ['08:00','08:30','09:00','09:30','10:00','10:30',
                                     '11:00','11:30','12:00','12:30','13:00','13:30',
                                     '14:00','14:30','15:00','15:30','16:00','16:30',
                                     '17:00','17:30']
            ud['times_label'] = 'Any Time'
            ud['step'] = 'confirm'
            await query.edit_message_text(
                f"📋 *Confirm New Monitor*\n\n{summary(ud)}\n\nAdd this monitor?",
                parse_mode='Markdown', reply_markup=kb_confirm()
            )
        elif slot == 'done':
            # Finalize selection
            if not selected:
                await query.answer("Select at least one time first!", show_alert=True)
                return
            ud['preferred_times'] = sorted(selected)
            ud['times_label'] = ', '.join(sorted(selected))
            ud['step'] = 'confirm'
            await query.edit_message_text(
                f"📋 *Confirm New Monitor*\n\n{summary(ud)}\n\nAdd this monitor?",
                parse_mode='Markdown', reply_markup=kb_confirm()
            )
        else:
            # Toggle this time slot
            if slot in selected:
                selected.remove(slot)
            else:
                selected.append(slot)
            ud['selected_times'] = selected
            label = f"⏰ Select times ({len(selected)} selected)" if selected else "⏰ Select time slots:"
            await query.edit_message_text(
                f"{label}\nTap to toggle, then tap ✅ Done",
                reply_markup=kb_times(selected)
            )
        return

    if data.startswith('tier:locked_'):
        locked = data.split('tier:locked_')[1]
        await query.answer("🔐 Agency plan required. Contact admin to upgrade.", show_alert=True)
        return

    if data.startswith('tier:'):
        tier = data.split(':')[1]
        tier_labels = {
            'notify': '🔔 Notify Only',
            'snipe':  '⚡ Snipe',
        }
        ud['tier'] = tier
        ud['tier_label'] = tier_labels.get(tier, tier)

        if tier == 'snipe':
            # Collect participant names before time selection
            a_count = ud.get('adult_count', 1)
            c_count = ud.get('child_count', 0)
            ud['snipe_participants'] = []
            ud['step'] = 'snipe_name'
            
            label = f"👤 Adult 1/{a_count}" if a_count > 0 else f"👤 Child 1/{c_count}"
            await query.edit_message_text(
                f"⚡ *Snipe — {ud['visitors']} Visitors*\n"
                f"({a_count} Adults, {c_count} Children)\n\n"
                f"Enter the name of each participant for the Vatican booking.\n\n"
                f"{label} — send *First Last*:\n_(e.g. `Mario Rossi`)_",
                parse_mode='Markdown'
            )
        else:
            # Notify: go straight to time selection
            ud['step'] = 'times'
            await query.edit_message_text(
                f"✅ Date: {ud['date']}\n✅ Visitors: {ud['visitors']}\n"
                f"✅ Ticket: {ud.get('ticket_label','')}\n✅ Mode: {ud['tier_label']}\n\n"
                f"⏰ Select preferred time:",
                reply_markup=kb_times(ud.get("selected_times",[]))
            )
        return

    if data.startswith('checkout:'):
        method = data.split(':')[1]  # 'api' or 'playwright'
        ud['checkout_method'] = method
        method_label = '🚀 API (fast)' if method == 'api' else '🌐 Playwright (free)'

        if method == 'playwright':
            # Ask which agent/machine should open the browser
            import requests as _req
            BACKEND = os.getenv('BACKEND_URL', 'http://backend:8000')
            try:
                r = _req.get(f'{BACKEND}/api/v1/agents/', timeout=4)
                agents = r.json().get('agents', {}) if r.status_code == 200 else {}
            except Exception:
                agents = {}

            rows = []
            for aid in agents:
                rows.append([InlineKeyboardButton(f"🖥️ {aid}", callback_data=f'agent_target:{aid}')])
            rows.append([InlineKeyboardButton("🔀 Any available agent", callback_data='agent_target:any')])
            rows.append([InlineKeyboardButton("❌ Cancel", callback_data='cancel')])

            await query.edit_message_text(
                f"✅ Checkout: {method_label}\n\n"
                f"🖥️ *Which machine should open Chrome?*\n\n"
                f"{'Online agents shown above.' if agents else '⚠️ No agents online — make sure `local_browser_agent.py` is running on your PC.'}\n\n"
                f"Select a machine or choose Any:",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(rows)
            )
        else:
            # API method — no agent needed, go straight to times
            ud['agent_target'] = None
            ud['step'] = 'times'
            await query.edit_message_text(
                f"✅ Checkout: {method_label}\n\n⏰ Select the time slots to snipe:",
                reply_markup=kb_times(ud.get("selected_times", []))
            )
        return

    if data.startswith('agent_target:'):
        target = data.split(':', 1)[1]  # agent name or 'any'
        ud['agent_target'] = None if target == 'any' else target
        label = f"🖥️ `{target}`" if target != 'any' else "🔀 Any available agent"
        ud['step'] = 'times'
        await query.edit_message_text(
            f"✅ Agent: {label}\n\n⏰ Select the time slots to snipe:",
            parse_mode='Markdown',
            reply_markup=kb_times(ud.get("selected_times", []))
        )
        return

    if data == 'confirm':
        await do_create_monitor(query, context)
        return

    # ── List ──
    if data == 'list':
        await do_list(query, context)
        return

    # ── Remove ──
    if data == 'remove':
        await do_remove_menu(query, context)
        return

    if data.startswith('del:'):
        task_id = int(data.split(':')[1])
        await do_delete_task(query, context, task_id)
        return

    # ── Status ──
    if data == 'status':
        await do_status(query, context)
        return

    if data == 'snipes':
        await do_list_snipes(query, context)
        return

    # ── Pay Hold ──
    if data.startswith('pay_hold:'):
        hold_id = int(data.split(':')[1])
        await do_pay_hold(query, context, hold_id)

    # ── Open Browser (local agent) ──
    if data.startswith('open_browser:') or data.startswith('open_browser_slot:'):
        from django.core.cache import cache
        import time as _time
        user = query.from_user
        user_name = user.first_name if user else 'Someone'

        # Deduplicate — ignore if same data was clicked in last 30s
        dedup_key = f"browser_click_dedup:{data[:50]}"
        if cache.get(dedup_key):
            await query.answer("Already processing — Chrome is opening!")
            return
        cache.set(dedup_key, True, timeout=30)

        # Store in cache so local agent can poll it
        agency = await get_agency(update.effective_chat.id)
        agency_key = agency.api_key if agency and agency.api_key else 'default'
        key = f"browser_pending_{agency_key}"

        pending = cache.get(key, [])
        pending.append({'data': data, 'user': user_name, 'auto': True})
        cache.set(key, pending, timeout=300)
        logger.info(f"Queued browser job for agency {agency_key}: {data[:50]}")

        # Edit the message to show it was clicked (prevents double-click)
        try:
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(f"✅ Clicked by {user_name}", callback_data='noop')
                ]])
            )
        except Exception:
            pass

        await query.answer(f"Opening Chrome on the agent machine...")
        return
        return

    # ── Book flow ──
    if data == 'book':
        await do_book_start(query, context)
        return

    if data.startswith('book_date:'):
        date_str = data.split(':', 1)[1]  # DD/MM/YYYY
        await do_book_select_slot(query, context, date_str)
        return

    if data.startswith('book_slot_time:'):
        # format: book_slot_time:{date}:{slot_time}
        parts = data.split(':', 2)
        date_str = parts[1]
        slot_time = parts[2]
        await do_book_show_visitor_options(query, context, date_str, slot_time)
        return

    if data.startswith('book_slot:'):
        # format: book_slot:{hold_id}
        hold_id = int(data.split(':')[1])
        await do_book_select_visitors(query, context, hold_id)
        return

    if data.startswith('book_vis:'):
        # format: book_vis:{hold_id}:{visitors}
        _, hold_id_str, vis_str = data.split(':')
        hold_id = int(hold_id_str)
        visitors = int(vis_str)
        await do_book_ask_names(query, context, hold_id, visitors)
        return

    if data.startswith('book_confirm:'):
        hold_id = int(data.split(':')[1])
        await do_book_generate_link(query, context, hold_id)
        return

    if data == 'book_cancel':
        ud.pop('booking', None)
        ud['step'] = None
        await query.edit_message_text("❌ Booking cancelled.", reply_markup=kb_back())
        return


# ── Text message handler (for manual date / custom times) ─────────────────────

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    step = ud.get('step')
    text = update.message.text.strip()

    # ── Admin: agency creation text steps ──
    admin_ids = [a.strip() for a in os.getenv('ADMIN_TELEGRAM_IDS', '').split(',') if a.strip()]
    ac = ud.get('admin_creating_agency')
    if ac and str(update.effective_user.id) in admin_ids:
        ac_step = ac.get('step')

        if ac_step == 'name':
            ac['agency_name'] = text
            ac['step'] = 'username'
            ud['admin_creating_agency'] = ac
            await update.message.reply_text(
                f"✅ Agency name: *{text}*\n\nStep 2/3 — Send the *login username* for this agency:",
                parse_mode='Markdown'
            )
        elif ac_step == 'username':
            # Check if username taken
            from asgiref.sync import sync_to_async
            from monitors.models import User as BotUser
            exists = await sync_to_async(BotUser.objects.filter(username=text).exists)()
            if exists:
                await update.message.reply_text("❌ Username already taken. Choose another:")
                return
            ac['username'] = text
            ac['step'] = 'password'
            ud['admin_creating_agency'] = ac
            await update.message.reply_text(
                f"✅ Username: *{text}*\n\nStep 3/3 — Send the *password*:",
                parse_mode='Markdown'
            )
        elif ac_step == 'password':
            ac['password'] = text
            ac['step'] = 'plan'
            ud['admin_creating_agency'] = ac
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🆓 Free", callback_data="admin_agency_plan:free"),
                InlineKeyboardButton("⭐ Pro", callback_data="admin_agency_plan:pro"),
                InlineKeyboardButton("🏢 Agency", callback_data="admin_agency_plan:agency"),
            ]])
            await update.message.reply_text(
                f"✅ Password set.\n\nSelect plan:",
                reply_markup=kb
            )
        return

    # ── AI Agent: answer ALL questions — CRM lookup, booking, everything ──
    if not ac and len(text) > 2:
        # Try fast local handlers first (instant, free)
        try:
            local = admin_assistant.handle_query(text)
            if local and not local.startswith("🤔"):
                await update.message.reply_text(local, parse_mode='Markdown', disable_web_page_preview=True)
                return
        except Exception:
            pass

        # Fall back to full AI agent with tools (DeepSeek-powered)
        try:
            response = run_agent(text)
            # Clean markdown for Telegram compatibility
            response = response.replace("**", "*").replace("# ", "*").replace("## ", "*")
            await update.message.reply_text(response, parse_mode='Markdown', disable_web_page_preview=True)
            return
        except Exception as e:
            await update.message.reply_text(f"❌ AI error: {str(e)[:200]}")
            return

    if step == 'date_text':
        try:
            d = datetime.strptime(text, '%Y-%m-%d')
            if d.date() < datetime.now().date():
                await update.message.reply_text("❌ Date must be in the future. Try again (YYYY-MM-DD):")
                return
            ud['date'] = text
            ud['step'] = 'visitors_a'
            await update.message.reply_text(
                f"✅ Date: {text}\n\n👥 How many *Adults*?",
                parse_mode='Markdown',
                reply_markup=kb_visitors_adults()
            )
        except ValueError:
            await update.message.reply_text("❌ Invalid format. Use YYYY-MM-DD (e.g. 2026-06-15):")
        return

    # ── Profile setup steps ──
    if step == 'profile_first_name':
        ud['profile']['first_name'] = text
        ud['step'] = 'profile_last_name'
        await update.message.reply_text("Step 2/5 — Send your *last name*:", parse_mode='Markdown')
        return

    if step == 'profile_last_name':
        ud['profile']['last_name'] = text
        ud['step'] = 'profile_email'
        await update.message.reply_text("Step 3/5 — Send your *email address*:", parse_mode='Markdown')
        return

    if step == 'profile_email':
        if '@' not in text:
            await update.message.reply_text("❌ Invalid email. Try again:")
            return
        ud['profile']['email'] = text
        ud['step'] = 'profile_phone'
        await update.message.reply_text("Step 4/5 — Send your *phone number* (e.g. +39 333 1234567):", parse_mode='Markdown')
        return

    if step == 'profile_phone':
        ud['profile']['phone'] = text
        ud['step'] = 'profile_birth_date'
        await update.message.reply_text("Step 5/5 — Send your *date of birth* (YYYY-MM-DD):", parse_mode='Markdown')
        return

    if step == 'profile_birth_date':
        from asgiref.sync import sync_to_async
        from datetime import date as date_type
        try:
            bd = datetime.strptime(text, '%Y-%m-%d').date()
        except ValueError:
            await update.message.reply_text("❌ Invalid format. Use YYYY-MM-DD (e.g. 1990-05-20):")
            return

        profile_data = ud.get('profile', {})
        agency_id = ud.get('agency_id')

        @sync_to_async
        def save_profile():
            from monitors.models import BuyerProfile, Agency
            agency = Agency.objects.get(id=agency_id)
            obj, _ = BuyerProfile.objects.update_or_create(
                agency=agency,
                defaults={
                    'first_name': profile_data['first_name'],
                    'last_name': profile_data['last_name'],
                    'email': profile_data['email'],
                    'phone': profile_data['phone'],
                    'birth_date': bd,
                }
            )
            return obj

        await save_profile()
        ud['step'] = None
        ud.pop('profile', None)
        await update.message.reply_text(
            f"✅ *Buyer profile saved!*\n\n"
            f"👤 {profile_data['first_name']} {profile_data['last_name']}\n"
            f"📧 {profile_data['email']}\n"
            f"📱 {profile_data['phone']}\n"
            f"🎂 {text}\n\n"
            f"Snipe mode will use this info to auto-book tickets.",
            parse_mode='Markdown',
            reply_markup=kb_back()
        )
        return

    # ── Snipe setup: collect participant names inline ──
    if step == 'snipe_name':
        visitors = ud.get('visitors', 1)
        a_count = ud.get('adult_count', 1)
        c_count = ud.get('child_count', 0)
        participants = ud.get('snipe_participants', [])

        parts = text.split(None, 1)
        first = parts[0].strip()
        last = parts[1].strip() if len(parts) > 1 else ''
        
        # Determine ticket type based on current count
        ticket_type = 'intero' if len(participants) < a_count else 'ridotto'
        label = 'Adult' if ticket_type == 'intero' else 'Child'
        
        participants.append({
            'first_name': first, 
            'last_name': last,
            'ticketType': ticket_type
        })
        ud['snipe_participants'] = participants

        if len(participants) < visitors:
            next_idx = len(participants)
            if next_idx < a_count:
                next_label = f"Adult {next_idx + 1}/{a_count}"
            else:
                next_label = f"Child {next_idx - a_count + 1}/{c_count}"
                
            await update.message.reply_text(
                f"✅ {label}: {first} {last}\n\n"
                f"👤 {next_label} — send *First Last* name:",
                parse_mode='Markdown'
            )
        else:
            # All names collected — ask checkout method
            preview = '\n'.join(f"  {i+1}. {p['first_name']} {p['last_name']}" for i, p in enumerate(participants))
            ud['step'] = 'snipe_checkout_method'
            await update.message.reply_text(
                f"✅ *{visitors} participant{'s' if visitors > 1 else ''} set:*\n{preview}\n\n"
                f"⚙️ *Checkout method:*\n\n"
                f"🚀 *API* — fast (~30s), needs 2captcha balance (~$0.001/booking)\n"
                f"🌐 *Playwright* — slow (~3min), free (browser solves Turnstile)\n",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 API (fast, needs 2captcha)", callback_data='checkout:api')],
                    [InlineKeyboardButton("🌐 Playwright (free, slower)", callback_data='checkout:playwright')],
                ])
            )
        return

    # ── Booking: collect participant names one by one ──
    if step == 'book_name':
        booking = ud.get('booking', {})
        names = booking.get('names', [])
        needed = booking.get('visitors', 1)
        collected = len(names)

        # Parse "FirstName LastName"
        parts = text.split(None, 1)
        first = parts[0].strip()
        last = parts[1].strip() if len(parts) > 1 else ''
        names.append({'first_name': first, 'last_name': last})
        booking['names'] = names
        ud['booking'] = booking

        if len(names) < needed:
            await update.message.reply_text(
                f"✅ {first} {last}\n\n"
                f"👤 Participant {len(names)+1}/{needed} — send *First Last* name:",
                parse_mode='Markdown'
            )
        else:
            # All names collected — show confirm
            hold_id = booking['hold_id']
            preview = '\n'.join(f"  {i+1}. {n['first_name']} {n['last_name']}" for i, n in enumerate(names))
            await update.message.reply_text(
                f"✅ All {needed} participants collected:\n\n{preview}\n\n"
                f"📅 {booking['date']} {booking['slot_time']}\n"
                f"👥 {needed} visitors | €{booking['total']}\n\n"
                f"Generate payment link?",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Generate Payment Link", callback_data=f"book_confirm:{hold_id}")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="book_cancel")],
                ])
            )
            ud['step'] = None
        return

    # Ignore other text during flow
    if step:
        await update.message.reply_text("Please use the buttons above, or /cancel to stop.")
        return

    # ── AI Assistant (RAG) ──
    # If no step is active, treat text as a question for the AI
    ai_agent = get_ai_agent()
    response = await ai_agent.answer_question(text)
    await update.message.reply_text(response)


async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI Assistant: answer natural language questions about CRM, bookings, revenue, snipes."""
    query = update.message.text.strip()
    # Remove the /ask prefix if present
    if query.lower().startswith('/ask'):
        query = query[4:].strip()

    if not query:
        await update.message.reply_text(
            "🤖 *AI Admin Assistant*\n\n"
            "Ask me anything! Examples:\n"
            "• Bookings today\n"
            "• Revenue this month\n"
            "• What's pending?\n"
            "• Show held slots\n"
            "• Customer john@email.com\n"
            "• Daily report",
            parse_mode='Markdown'
        )
        return

    await update.message.reply_text("🤔 Thinking...")
    response = run_agent(query)  # Full AI agent with tools
    await update.message.reply_text(response, parse_mode='Markdown', disable_web_page_preview=True)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows global system status of all tasks and their states."""
    from asgiref.sync import sync_to_async
    
    tasks = await sync_to_async(list)(VaticanTask.objects.all().order_by('-updated_at')[:20])
    
    if not tasks:
        await update.message.reply_text("📭 No tasks in the system.")
        return

    msg = "📊 *Current System Status (Last 20 Tasks):*\n\n"
    for t in tasks:
        emoji = "🆕" if t.status == 'new' else "🔍" if t.status == 'checking' else "⚠️" if t.status == 'awaiting_info' else "✅" if t.status == 'ready' else "🤖" if t.status == 'monitoring' else "🚀" if t.status == 'booking' else "🎫" if t.status == 'booked' else "🏁"
        msg += f"{emoji} *#{t.id}* ({t.booking_id})\n   └ State: `{t.status}` | Date: {t.target_date}\n"

    await update.message.reply_text(msg, parse_mode='Markdown')

async def pending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all tasks stuck in awaiting_info."""
    from asgiref.sync import sync_to_async
    
    pending = await sync_to_async(list)(VaticanTask.objects.filter(status='awaiting_info'))
    
    if not pending:
        await update.message.reply_text("✅ No tasks are currently awaiting info.")
        return

    msg = "⚠️ *Tasks Awaiting Info:*\n\n"
    for t in pending:
        msg += f"🔸 *#{t.id}* ({t.booking_id})\n   └ Customer: {t.customer_name}\n   └ Missing: _{t.missing_info or 'N/A'}_\n"

    await update.message.reply_text(msg, parse_mode='Markdown')

# ── Actions ───────────────────────────────────────────────────────────────────

async def do_create_monitor(query, context):
    from asgiref.sync import sync_to_async
    ud = context.user_data
    agency_id = ud.get('agency_id')
    date = ud.get('date')
    visitors = ud.get('visitors') or 1
    adult_count = ud.get('adult_count')
    if adult_count is None:
        adult_count = visitors
    child_count = ud.get('child_count')
    if child_count is None:
        child_count = 0
    ticket_type = ud.get('ticket_type', 0)
    ticket_name = ud.get('ticket_name', "Musei Vaticani - Biglietti d'ingresso")
    ticket_label = ud.get('ticket_label', 'Standard Entry')
    language = ud.get('language')
    preferred_times = ud.get('preferred_times', ['09:00','10:00','11:00','12:00','13:00','14:00','15:00','16:00'])

    try:
        agency = await sync_to_async(Agency.objects.get)(id=agency_id)

        tier = ud.get('tier', 'notify')
        snipe_participants = ud.get('snipe_participants', [])
        checkout_method = ud.get('checkout_method', 'api')

        # Check duplicate — only block if EXACT same date+visitors+times+tier
        existing_list = await sync_to_async(list)(
            MonitorTask.objects.filter(
                agency=agency, site='vatican',
                dates__contains=[date], visitors=visitors,
                ticket_type=ticket_type, tier=tier, is_active=True
            )
        )

        pref_set = set(preferred_times)
        duplicate = None
        for ex in existing_list:
            if set(ex.preferred_times or []) == pref_set:
                duplicate = ex
                break

        if duplicate:
            times_str = ', '.join(sorted(duplicate.preferred_times or []))
            await query.edit_message_text(
                f"⚠️ Monitor already exists (Task #{duplicate.id})\n\nDate: {date} · Visitors: {visitors}\nTimes: {times_str}",
                reply_markup=kb_back()
            )
            return

        import json as _json
        task = await sync_to_async(MonitorTask.objects.create)(
            agency=agency,
            site='vatican',
            area_name='Musei Vaticani',
            dates=[date],
            preferred_times=preferred_times,
            visitors=visitors,
            adult_count=adult_count,
            child_count=child_count,
            ticket_type=ticket_type,
            ticket_label=ticket_label,
            ticket_name=ticket_name,
            ticket_id=None,
            language=language,
            check_interval=60,
            tier=tier,
            checkout_method=checkout_method,
            participants_json=_json.dumps(snipe_participants) if snipe_participants else None,
            match_strategy='any',
            notification_mode='available_only',
            is_active=True,
            last_status='pending',
            remote_worker_needed=(tier == 'snipe'),
            agent_target=ud.get('agent_target'),  # specific machine or None for any
            last_result_summary=f"Created via Telegram on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Trigger immediate check
        try:
            from monitors.tasks import resolve_and_check_task
            await sync_to_async(resolve_and_check_task.delay)(task.id)
        except Exception as e:
            logger.warning(f"Could not trigger immediate check: {e}")

        # ── PLAYWRIGHT: push to browser agent immediately on task creation ──
        if tier == 'snipe' and checkout_method == 'playwright':
            import base64 as _b64
            from django.core.cache import cache as _cache
            year, month, day = date.split('-')
            d_api = f"{day}/{month}/{year}"
            # Preferred time for the agent to target (first in list, or 09:00 fallback)
            pref_time = preferred_times[0] if preferred_times else '09:00'
            # Encode slot info — no slot_id yet, agent will find one
            slot_info = _b64.b64encode(
                f"{d_api}|{pref_time}||{visitors}|?|{adult_count}|{child_count}".encode()
            ).decode()
            job = {
                'data': f'open_browser_slot:{slot_info}',
                'user': f'Task #{task.id} (playwright)',
                'auto': True,
                'task_id': task.id,
            }
            agency_key = agency.api_key if agency and agency.api_key else 'default'
            agent_target = ud.get('agent_target')
            if agent_target:
                key = f'browser_pending_{agency_key}_{agent_target}'
                q = _cache.get(key, [])
                q.insert(0, job)
                _cache.set(key, q, timeout=1800)
                logger.info(f"Queued targeted browser job for agency {agency_key}, agent {agent_target}")
            else:
                key = f'browser_pending_{agency_key}'
                pending = _cache.get(key, [])
                pending.insert(0, job)
                _cache.set(key, pending, timeout=1800)
                logger.info(f"Queued agency browser job for agency {agency_key}")

            ud['step'] = None
            extra = ''
            if snipe_participants:
                names_preview = ', '.join(f"{p['first_name']} {p['last_name']}" for p in snipe_participants)
                extra = f"\n👥 Participants: {names_preview}"
            await query.edit_message_text(
                f"✅ *Task #{task.id} created — Chrome opening now*\n\n"
                f"{summary(ud)}{extra}\n\n"
                f"🌐 Browser agent is launching Chrome for *{d_api}*.\n"
                f"Form will be pre-filled. Pay manually on the site.",
                parse_mode='Markdown',
                reply_markup=kb_back()
            )
            return

        # For snipe tasks: immediately check if slot is already available and hold it NOW
        if tier == 'snipe':
            try:
                import requests as _req
                from asgiref.sync import sync_to_async as _s2a

                s = _req.Session()
                H = {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest',
                     'Referer': 'https://tickets.museivaticani.va/'}
                year, month, day = date.split('-')
                d_api = f"{day}/{month}/{year}"

                r = s.get('https://tickets.museivaticani.va/api/search/resultPerTag', params={
                    'lang': 'it', 'visitorNum': str(visitors), 'visitDate': d_api,
                    'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
                }, headers=H, timeout=8)

                if r.status_code == 200:
                    ticket = next((v for v in r.json().get('visits', [])
                                   if 'musei vaticani' in v.get('name', '').lower()
                                   and 'ingresso' in v.get('name', '').lower()
                                   and v.get('availability') in ('AVAILABLE', 'LOW_AVAILABILITY')), None)
                    if ticket:
                        tid = ticket['id']
                        r2 = s.get('https://tickets.museivaticani.va/api/visit/timeavail', params={
                            'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
                            'visitorNum': str(visitors), 'visitDate': d_api,
                        }, headers=H, timeout=8)
                        if r2.status_code == 200:
                            open_slots = [sl for sl in r2.json().get('timetable', [])
                                          if sl.get('availability') not in ('SOLD_OUT', 'NOT_ALLOWED')]
                            # Filter to preferred times
                            if preferred_times:
                                matching = [sl for sl in open_slots if sl.get('time') in preferred_times]
                            else:
                                matching = open_slots

                            if matching:
                                best = matching[0]
                                slot_time_found = best.get('time')
                                slot_id_found = str(best.get('id', ''))
                                logger.info(f"⚡ Immediate snipe: task #{task.id} — slot {d_api} {slot_time_found} available NOW — holding directly")

                                # Directly trigger auto_hold_slot for THIS task (bypasses cooldowns)
                                from monitors.tasks_hold import auto_hold_slot
                                await _s2a(auto_hold_slot.delay)(
                                    task_id=task.id,
                                    date=d_api,
                                    slot_id=slot_id_found,
                                    slot_time=slot_time_found,
                                    ticket_id=str(tid),
                                    ticket_name="Musei Vaticani - Biglietti d'ingresso",
                                    visitors=visitors,
                                )
                                await query.edit_message_text(
                                    f"⚡ *Slot found immediately!*\n\n"
                                    f"📅 {d_api} {slot_time_found}\n"
                                    f"👥 {visitors} visitors\n\n"
                                    f"🔒 Holding slot now... Chrome will open on your machine shortly.",
                                    parse_mode='Markdown',
                                    reply_markup=kb_back()
                                )
                                return  # skip the normal "monitor created" message
                            else:
                                logger.info(f"Snipe task #{task.id}: slots open on {d_api} but none match preferred times {preferred_times}")
                        else:
                            logger.info(f"Snipe task #{task.id}: timeavail {r2.status_code} for {d_api}")
                    else:
                        logger.info(f"Snipe task #{task.id}: no available ticket on {d_api}")
            except Exception as e:
                logger.warning(f"Immediate snipe check failed: {e}")

        ud['step'] = None
        tier = ud.get('tier', 'notify')
        extra = ''
        if tier == 'snipe' and snipe_participants:
            names_preview = ', '.join(f"{p['first_name']} {p['last_name']}" for p in snipe_participants)
            extra = f"\n👥 Participants: {names_preview}"
        await query.edit_message_text(
            f"✅ Monitor created! (Task #{task.id})\n\n{summary(ud)}{extra}\n\n"
            f"{'⚡ Will auto-snipe and send payment link when slot opens.' if tier == 'snipe' else '🔔 You will be notified when tickets are available.'}",
            reply_markup=kb_back()
        )
    except Exception as e:
        logger.error(f"Error creating monitor: {e}")
        await query.edit_message_text(f"❌ Error: {e}", reply_markup=kb_back())


async def do_list(query, context):
    from asgiref.sync import sync_to_async
    agency_id = context.user_data.get('agency_id')
    tasks = await sync_to_async(list)(
        MonitorTask.objects.filter(agency_id=agency_id, site='vatican', is_active=True).order_by('dates')
    )
    if not tasks:
        await query.edit_message_text("📋 No active monitors.", reply_markup=kb_back())
        return
    tier_icons = {'notify': '🔔', 'snipe': '⚡'}
    lines = [f"📋 *Active Monitors ({len(tasks)})*\n"]
    for t in tasks:
        status_icon = "🟢" if t.last_status == 'available' else "🔴" if t.last_status == 'sold_out' else "⏳"
        icon = tier_icons.get(t.tier, '🔔')
        times = t.preferred_times
        time_str = times[0] if len(times) == 1 else 'Any'
        lines.append(f"{status_icon} #{t.id} · {t.dates[0] if t.dates else '?'} · {t.visitors}v · {time_str} · {icon} {t.tier}")
    await query.edit_message_text('\n'.join(lines), parse_mode='Markdown', reply_markup=kb_back())


async def do_remove_menu(query, context):
    from asgiref.sync import sync_to_async
    agency_id = context.user_data.get('agency_id')
    tasks = await sync_to_async(list)(
        MonitorTask.objects.filter(agency_id=agency_id, site='vatican', is_active=True).order_by('dates')[:10]
    )
    if not tasks:
        await query.edit_message_text("📋 No monitors to remove.", reply_markup=kb_back())
        return
    rows = [[InlineKeyboardButton(
        f"🗑️ #{t.id} · {t.dates[0] if t.dates else '?'} · {t.visitors}v",
        callback_data=f'del:{t.id}'
    )] for t in tasks]
    rows.append([InlineKeyboardButton("🔙 Back", callback_data='menu')])
    await query.edit_message_text("Select monitor to remove:", reply_markup=InlineKeyboardMarkup(rows))


async def do_delete_task(query, context, task_id):
    from asgiref.sync import sync_to_async
    try:
        task = await sync_to_async(MonitorTask.objects.get)(id=task_id)
        date = task.dates[0] if task.dates else '?'
        await sync_to_async(task.delete)()
        await query.edit_message_text(f"✅ Monitor #{task_id} removed (Date: {date})", reply_markup=kb_back())
    except MonitorTask.DoesNotExist:
        await query.edit_message_text("❌ Monitor not found.", reply_markup=kb_back())


async def do_status(query, context):
    from asgiref.sync import sync_to_async
    agency_id = context.user_data.get('agency_id')
    agency_name = context.user_data.get('agency_name', '?')
    tasks = await sync_to_async(list)(MonitorTask.objects.filter(agency_id=agency_id, site='vatican', is_active=True))
    available = sum(1 for t in tasks if t.last_status == 'available')
    sold_out  = sum(1 for t in tasks if t.last_status == 'sold_out')
    await query.edit_message_text(
        f"📊 Status\nAgency: {agency_name}\n\n"
        f"Monitors: {len(tasks)}\n✅ Available: {available}\n❌ Sold Out: {sold_out}\n"
        f"⏳ Other: {len(tasks)-available-sold_out}\n\n⚡ Running 24/7",
        reply_markup=kb_back()
    )


async def snipes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/snipes command — show active snipe monitors and stats."""
    from asgiref.sync import sync_to_async
    agency = await get_agency(update.effective_chat.id)
    if not agency:
        await update.message.reply_text("⚠️ Chat not linked to an agency.")
        return

    @sync_to_async
    def get_snipes():
        from monitors.models import MonitorTask, HeldSlot
        snipes = list(MonitorTask.objects.filter(agency=agency, tier='snipe', is_active=True).order_by('dates'))
        # Active holds
        holds = list(HeldSlot.objects.filter(task__agency=agency, status__in=['held','paying']).order_by('-hold_started_at')[:10])
        return snipes, holds

    snipes, holds = await get_snipes()

    msg = f"⚡ *Vatican Snipes Dashboard*\n\n"
    if not snipes:
        msg += "❌ No active snipe monitors."
    else:
        msg += f"✅ *{len(snipes)} Active Snipe Tasks:*\n"
        for s in snipes:
            msg += f"• #{s.id} | {s.dates[0]} | {s.visitors}v | {s.checkout_method}\n"

    msg += "\n🕒 *Recent/Active Holds:*\n"
    if not holds:
        msg += "_None currently held_"
    for h in holds:
        rem = max(0, 24 - h.hold_duration_hours())
        msg += f"• {h.date} {h.slot_time} | {h.visitors}v | ⏱{rem:.1f}h\n"

    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=kb_main())


async def do_list_snipes(query, context):
    """Callback for the 'Snipes' button."""
    from asgiref.sync import sync_to_async
    agency_id = context.user_data.get('agency_id')
    
    @sync_to_async
    def get_snipes():
        from monitors.models import MonitorTask, HeldSlot
        snipes = list(MonitorTask.objects.filter(agency_id=agency_id, tier='snipe', is_active=True).order_by('dates'))
        holds = list(HeldSlot.objects.filter(task__agency_id=agency_id, status__in=['held','paying']).order_by('-hold_started_at')[:5])
        return snipes, holds
        
    snipes, holds = await get_snipes()
    
    msg = f"⚡ *Snipe Management*\n\n"
    if not snipes:
        msg += "No active snipe monitors."
    else:
        for s in snipes:
            status = "🟢" if s.last_status == 'available' else "🔴"
            msg += f"{status} #{s.id} | {s.dates[0]} | {s.visitors}v | {s.checkout_method}\n"

    if holds:
        msg += "\n🔒 *Current Holds:*\n"
        for h in holds:
            rem = max(0, 24 - h.hold_duration_hours())
            msg += f"• {h.date} {h.slot_time} ({rem:.1f}h left)\n"
            
    await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=kb_back())


async def do_pay_hold(query, context, hold_id):
    """Generate a payment link for a hold, using uploaded participant names."""
    from asgiref.sync import sync_to_async
    # import aiohttp (removed unused)

    @sync_to_async
    def get_hold_and_link():
        from monitors.models import HeldSlot, BuyerProfile
        import secrets, json
        from django.core.cache import cache

        try:
            held = HeldSlot.objects.select_related('task__agency').get(id=hold_id)
        except HeldSlot.DoesNotExist:
            return None, "Hold not found"

        if held.status not in ('held', 'paying'):
            return None, f"Hold is {held.status}"

        if held.hold_duration_hours() >= 24:
            return None, "Hold expired (24h limit)"

        # Get participant names from BuyerProfile
        participants = []
        try:
            profile = BuyerProfile.objects.get(agency=held.task.agency)
            if profile.participants_json:
                participants = json.loads(profile.participants_json)
        except Exception:
            pass

        # Generate token
        token = secrets.token_urlsafe(32)
        cache.set(f"epay_token:{hold_id}:{token}", {
            'hold_id': hold_id,
            'participants': participants,
            'representative': {},
        }, timeout=1800)

        # Build URL — use the server's base URL
        import os
        base = os.getenv('SERVER_BASE_URL', 'https://hydrabot.it')
        payment_url = f"{base}/pay/{hold_id}/{token}/"

        remaining = max(0, 24 - held.hold_duration_hours())
        return {
            'url': payment_url,
            'date': held.date,
            'time': held.slot_time,
            'visitors': held.visitors,
            'total': held.total_price,
            'remaining': remaining,
            'participants': participants,
        }, None

    result, error = await get_hold_and_link()

    if error:
        await query.edit_message_text(f"❌ {error}", reply_markup=kb_back())
        return

    participant_preview = ""
    if result['participants']:
        names = [f"{p.get('first_name','')} {p.get('last_name','')}".strip()
                 for p in result['participants'][:result['visitors']]]
        participant_preview = "\n👤 Participants:\n" + '\n'.join(f"  {i+1}. {n}" for i, n in enumerate(names))
    else:
        participant_preview = "\n⚠️ No participant names uploaded — using profile defaults.\nUse /setparticipants to upload names."

    await query.edit_message_text(
        f"💳 *Payment Link Ready*\n\n"
        f"📅 {result['date']} {result['time']}\n"
        f"👥 {result['visitors']} visitors | €{result['total']}\n"
        f"⏱ {result['remaining']:.0f}h remaining\n"
        f"{participant_preview}\n\n"
        f"🔗 *Open this link to pay:*\n"
        f"{result['url']}\n\n"
        f"⚠️ Link valid for 30 minutes. Single-use.",
        parse_mode='Markdown',
        disable_web_page_preview=True,
        reply_markup=kb_back()
    )


async def pending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/pending — admin only: list all pending groups waiting for approval."""
    from asgiref.sync import sync_to_async

    admin_ids = [a.strip() for a in os.getenv('ADMIN_TELEGRAM_IDS', '').split(',') if a.strip()]
    if str(update.effective_user.id) not in admin_ids:
        await update.message.reply_text("⛔ Not authorized.")
        return

    @sync_to_async
    def get_pending():
        return list(TelegramGroup.objects.filter(status='pending').order_by('-created_at')[:20])

    groups = await get_pending()
    if not groups:
        await update.message.reply_text("✅ No pending groups.")
        return

    for g in groups:
        approve_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve:{g.chat_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject:{g.chat_id}")
        ]])
        await update.message.reply_text(
            f"🔔 *Pending Group*\n\n"
            f"Group: *{g.chat_title or 'Unknown'}*\n"
            f"ID: `{g.chat_id}`\n"
            f"Added by: {g.added_by_first_name or 'N/A'} (@{g.added_by_username or 'N/A'})\n"
            f"Created: {g.created_at.strftime('%Y-%m-%d %H:%M')}",
            parse_mode='Markdown',
            reply_markup=approve_kb
        )


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['step'] = None
    await update.message.reply_text("❌ Cancelled. Use /start to go back.", reply_markup=kb_back())


async def setprofile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setprofile — set buyer profile for snipe mode.
    Walks through: first_name → last_name → email → phone → birth_date → done.
    """
    ud = context.user_data
    agency = await get_agency(update.effective_chat.id)
    if not agency:
        await update.message.reply_text("⚠️ Chat not linked to an agency.")
        return
    ud['agency_id'] = agency.id
    ud['agency_name'] = agency.name
    ud['step'] = 'profile_first_name'
    ud['profile'] = {}
    await update.message.reply_text(
        "👤 *Set Buyer Profile* (for Snipe mode)\n\n"
        "This info is used to auto-fill the Vatican booking form.\n\n"
        "Step 1/5 — Send your *first name*:",
        parse_mode='Markdown'
    )


async def holds_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/holds — list recent snipe results (paying/paid slots)."""
    from asgiref.sync import sync_to_async
    agency = await get_agency(update.effective_chat.id)
    if not agency:
        await update.message.reply_text("⚠️ Chat not linked to an agency.")
        return

    @sync_to_async
    def get_snipes():
        from monitors.models import HeldSlot
        return list(HeldSlot.objects.filter(
            status__in=['paying', 'paid']
        ).order_by('-hold_started_at')[:20])

    snipes = await get_snipes()
    if not snipes:
        await update.message.reply_text(
            "⚡ No snipe results yet.\n\nSnipes appear here when a slot is auto-booked.",
            reply_markup=kb_back()
        )
        return

    lines = [f"⚡ *Recent Snipes ({len(snipes)})*\n"]
    for h in snipes:
        import json as _j
        try:
            ref = _j.loads(h.notes or '{}').get('reference', '')
        except Exception:
            ref = ''
        status_icon = "✅" if h.status == 'paid' else "💳"
        lines.append(f"{status_icon} {h.date} {h.slot_time} · {h.visitors}v · €{h.total_price} · {ref or h.status}")

    await update.message.reply_text('\n'.join(lines), parse_mode='Markdown', reply_markup=kb_back())


# ============================================================================
# DEPRECATED COMMANDS - Replaced by Browser Extension
# ============================================================================
# These commands are no longer used. The browser extension handles all booking
# automation automatically. Kept here for reference only.
# ============================================================================

# async def stop_recap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """/stop_recap <hold_id> — DEPRECATED: Extension handles this automatically."""
#     await update.message.reply_text(
#         "⚠️ *This command is deprecated.*\n\n"
#         "The browser extension handles booking automatically.\n"
#         "No manual recap control needed.\n\n"
#         "See /help for current commands.",
#         parse_mode='Markdown'
#     )


# async def resume_recap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """/resume_recap <hold_id> — DEPRECATED: Extension handles this automatically."""
#     await update.message.reply_text(
#         "⚠️ *This command is deprecated.*\n\n"
#         "The browser extension handles booking automatically.\n"
#         "See /help for current commands.",
#         parse_mode='Markdown'
#     )


# async def pay_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """/pay <hold_id> — DEPRECATED: Extension completes payment automatically."""
#     await update.message.reply_text(
#         "⚠️ *This command is deprecated.*\n\n"
#         "The browser extension completes bookings automatically.\n"
#         "Just wait for the confirmation email!\n\n"
#         "See /help for current commands.",
#         parse_mode='Markdown'
#     )


async def open_browser_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/open <hold_id> [agent] — open Chrome on the local agent for a specific hold.
    You pay manually on the site — the browser just navigates and fills the form.
    Usage:
      /open 42          — open on any available agent
      /open 42 my-pc    — open on a specific machine
      /open             — list active holds to choose from
    """
    import base64 as _b64
    from django.core.cache import cache
    from asgiref.sync import sync_to_async

    args = context.args or []

    @sync_to_async
    def get_active_holds():
        from monitors.models import HeldSlot
        return list(HeldSlot.objects.filter(status__in=['held', 'paying']).order_by('-hold_started_at')[:10])

    # No args — list active holds
    if not args:
        holds = await get_active_holds()
        if not holds:
            await update.message.reply_text(
                "❌ No active holds.\n\nUse `/add` to set up a snipe task first.",
                parse_mode='Markdown'
            )
            return
        lines = ["🔒 *Active Holds — use /open <id> to trigger browser:*\n"]
        for h in holds:
            rem = max(0, 24 - h.hold_duration_hours())
            lines.append(f"• `/open {h.id}` — {h.date} {h.slot_time} · {h.visitors}v · {rem:.0f}h left")
        await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')
        return

    if not args[0].isdigit():
        await update.message.reply_text(
            "Usage: `/open <hold_id>` or just `/open` to list active holds.",
            parse_mode='Markdown'
        )
        return

    hold_id = int(args[0])
    target_agent = args[1] if len(args) >= 2 else None

    @sync_to_async
    def fetch_hold(hid):
        from monitors.models import HeldSlot
        try:
            return HeldSlot.objects.get(id=hid), None
        except HeldSlot.DoesNotExist:
            return None, f"Hold #{hid} not found"

    hold, error = await fetch_hold(hold_id)
    if error:
        await update.message.reply_text(f"❌ {error}")
        return

    slot_info = _b64.b64encode(
        f"{hold.date}|{hold.slot_time}|{hold.slot_id or ''}|{hold.visitors}|{hold.total_price or '?'}|{hold.adult_count}|{hold.child_count}".encode()
    ).decode()
    job = {'data': f'open_browser:{hold_id}:{slot_info}', 'user': update.effective_user.first_name or 'User', 'auto': False}

    if target_agent:
        key = f'browser_pending_{target_agent}'
        q = cache.get(key, [])
        q.insert(0, job)
        cache.set(key, q, timeout=300)
        target_msg = f"on `{target_agent}`"
    else:
        pending = cache.get('browser_pending', [])
        pending.insert(0, job)
        cache.set('browser_pending', pending, timeout=300)
        target_msg = "on first available agent"

    await update.message.reply_text(
        f"🌐 *Chrome opening {target_msg}*\n\n"
        f"📅 {hold.date} {hold.slot_time} · {hold.visitors}v\n\n"
        f"Form will be pre-filled. Pay manually on the site.",
        parse_mode='Markdown'
    )


async def agent_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/agent — admin commands to control the local browser agent.
    Usage:
      /agent status          — show agent status and config
      /agent poll <seconds>  — change poll interval (e.g. /agent poll 2)
      /agent open <hold_id>  — force open Chrome for a specific hold
      /agent open <date> <time> <visitors>  — open Chrome for a specific slot directly
    """
    import requests as _req
    from django.core.cache import cache

    admin_ids = [a.strip() for a in os.getenv('ADMIN_TELEGRAM_IDS', '').split(',') if a.strip()]
    if str(update.effective_user.id) not in admin_ids:
        await update.message.reply_text("⛔ Admin only.")
        return

    BACKEND = os.getenv('BACKEND_URL', 'http://backend:8000')
    args = context.args or []

    if not args or args[0] == 'status':
        # Show current config + pending queue size + online agents
        try:
            r = _req.get(f'{BACKEND}/api/v1/agent-config/', timeout=5)
            cfg = r.json() if r.status_code == 200 else {}
        except Exception:
            cfg = {}
        try:
            r2 = _req.get(f'{BACKEND}/api/v1/agents/', timeout=5)
            agents = r2.json().get('agents', {}) if r2.status_code == 200 else {}
        except Exception:
            agents = {}
        pending = cache.get('browser_pending', [])
        from monitors.models import HeldSlot
        active_holds = HeldSlot.objects.filter(status__in=['held', 'paying']).count()

        agent_lines = '\n'.join(
            f"  • `{aid}` ({info.get('hostname','?')}) ✅ online"
            for aid, info in agents.items()
        ) or '  None online'

        await update.message.reply_text(
            f"🤖 *Agent Status*\n\n"
            f"*Online agents:*\n{agent_lines}\n\n"
            f"Pending jobs: `{len(pending)}`\n"
            f"Active holds: `{active_holds}`\n\n"
            f"*Commands:*\n"
            f"`/agent open <hold_id>` — open on any free agent\n"
            f"`/agent open <hold_id> <agent_name>` — open on specific machine\n"
            f"`/agent open DD/MM/YYYY HH:MM visitors` — open directly\n"
            f"`/agent poll 2` — set poll interval",
            parse_mode='Markdown'
        )

    elif args[0] == 'poll' and len(args) >= 2:
        try:
            secs = max(1, int(args[1]))
            _req.post(f'{BACKEND}/api/v1/agent-config/set/', json={'poll_interval': secs}, timeout=5)
            await update.message.reply_text(f"✅ Agent poll interval set to `{secs}s`", parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    elif args[0] == 'open':
        import base64 as _b64
        if len(args) >= 2 and args[1].isdigit():
            # /agent open <hold_id> [agent_name]
            hold_id = int(args[1])
            target_agent = args[2] if len(args) >= 3 else None  # optional: target specific machine
            try:
                r = _req.get(f'{BACKEND}/api/v1/holds/?status=all', timeout=5)
                holds = r.json().get('results', []) if r.status_code == 200 else []
                hold = next((h for h in holds if h['id'] == hold_id), None)
            except Exception:
                hold = None
            if not hold:
                await update.message.reply_text(f"❌ Hold #{hold_id} not found.")
                return
            try: _req.post(f'{BACKEND}/api/v1/holds/{hold_id}/pause-recap/', timeout=5)
            except: pass
            slot_info = _b64.b64encode(
                f"{hold['date']}|{hold['slot_time']}|{hold.get('slot_id','')}|{hold['visitors']}|{hold.get('total_price','?')}".encode()
            ).decode()
            job = {'data': f'open_browser:{hold_id}:{slot_info}', 'user': 'Admin', 'auto': True}
            if target_agent:
                # Push to agent-specific queue
                key = f'browser_pending_{target_agent}'
                q = cache.get(key, [])
                q.insert(0, job)
                cache.set(key, q, timeout=300)
                target_msg = f"on `{target_agent}`"
            else:
                # Push to shared queue — any free agent picks it up
                pending = cache.get('browser_pending', [])
                pending.insert(0, job)
                cache.set('browser_pending', pending, timeout=300)
                target_msg = "on first available agent"
            await update.message.reply_text(
                f"🌐 Chrome opening {target_msg} for Hold #{hold_id}\n"
                f"📅 {hold['date']} {hold['slot_time']} · {hold['visitors']}v\n"
                f"Agent picks up within ~1s.",
                parse_mode='Markdown'
            )

        elif len(args) >= 4:
            # /agent open DD/MM/YYYY HH:MM visitors
            date_str, time_str, vis_str = args[1], args[2], args[3]
            visitors = int(vis_str)
            slot_info = _b64.b64encode(f"{date_str}|{time_str}||{visitors}|?".encode()).decode()
            pending = cache.get('browser_pending', [])
            pending.insert(0, {'data': f'open_browser_slot:{slot_info}', 'user': 'Admin', 'auto': True})
            cache.set('browser_pending', pending, timeout=300)
            await update.message.reply_text(
                f"🌐 Chrome opening for {date_str} {time_str} · {visitors}v\n"
                f"Agent will pick this up within 2s."
            )
        else:
            await update.message.reply_text("Usage: `/agent open <hold_id>` or `/agent open DD/MM/YYYY HH:MM visitors`", parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "Usage:\n`/agent status`\n`/agent poll <seconds>`\n`/agent open <hold_id>`",
            parse_mode='Markdown'
        )


async def setparticipants_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setparticipants [task_id] — set participant names for a specific snipe task.
    If no task_id given, shows list of snipe tasks to choose from.
    Names are used as participantUser in the Vatican reservation.
    """
    from asgiref.sync import sync_to_async

    agency = await get_agency(update.effective_chat.id)
    if not agency:
        await update.message.reply_text("⚠️ Chat not linked to an agency.")
        return

    args = context.args or []

    @sync_to_async
    def get_snipe_tasks():
        from monitors.models import MonitorTask
        return list(MonitorTask.objects.filter(agency=agency, tier='snipe', is_active=True)
                    .values('id', 'area_name', 'visitors', 'pay_mode', 'participants_json'))

    tasks = await get_snipe_tasks()
    if not tasks:
        await update.message.reply_text("⚠️ No active snipe tasks found. Set a task to tier='snipe' first.")
        return

    # If task_id provided, go straight to upload
    if args and args[0].isdigit():
        task_id = int(args[0])
        task = next((t for t in tasks if t['id'] == task_id), None)
        if not task:
            await update.message.reply_text(f"❌ Snipe task #{task_id} not found.")
            return
        context.user_data['step'] = 'awaiting_participants_file'
        context.user_data['agency_id'] = agency.id
        context.user_data['participants_task_id'] = task_id
        await update.message.reply_text(
            f"📋 *Upload participants for Task #{task_id}* ({task['area_name']}, {task['visitors']} visitors)\n\n"
            "Send a `.txt` or `.csv` file, one name per line:\n"
            "`FirstName LastName`\n`FirstName,LastName`",
            parse_mode='Markdown'
        )
        return

    # Show task list
    lines = ["📋 *Snipe Tasks — choose one:*\n"]
    for t in tasks:
        import json as _json
        pcount = 0
        if t.get('participants_json'):
            try:
                pcount = len(_json.loads(t['participants_json']))
            except Exception:
                pass
        lines.append(f"• `/setparticipants {t['id']}` — Task #{t['id']} | {t['area_name']} | {t['visitors']}v | {pcount} names set")
    await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle .txt/.csv participant list uploads."""
    from asgiref.sync import sync_to_async

    ud = context.user_data
    if ud.get('step') != 'awaiting_participants_file':
        return

    doc = update.message.document
    if not doc.file_name.endswith(('.txt', '.csv')):
        await update.message.reply_text("❌ Please send a .txt or .csv file.")
        return

    agency_id = ud.get('agency_id')
    if not agency_id:
        await update.message.reply_text("⚠️ Session expired. Use /start first.")
        return

    # Download file
    file = await context.bot.get_file(doc.file_id)
    raw = await file.download_as_bytearray()
    text = raw.decode('utf-8', errors='ignore')

    # Parse names
    participants = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ',' in line:
            parts = [p.strip() for p in line.split(',', 1)]
        else:
            parts = line.split(None, 1)
        if len(parts) == 2:
            participants.append({'first_name': parts[0], 'last_name': parts[1]})
        elif len(parts) == 1:
            participants.append({'first_name': parts[0], 'last_name': ''})

    if not participants:
        await update.message.reply_text("❌ No valid names found. Check the format and try again.")
        return

    # Save to MonitorTask.participants_json (task-specific) or BuyerProfile (fallback)
    @sync_to_async
    def save_participants():
        from monitors.models import BuyerProfile, Agency, MonitorTask
        import json
        agency = Agency.objects.get(id=agency_id)
        task_id = ud.get('participants_task_id')
        if task_id:
            # Save to specific task
            MonitorTask.objects.filter(id=task_id, agency=agency).update(
                participants_json=json.dumps(participants)
            )
            return len(participants), f"Task #{task_id}"
        else:
            # Fallback: save to BuyerProfile (agency-wide)
            profile, _ = BuyerProfile.objects.get_or_create(
                agency=agency,
                defaults={'first_name': 'Agency', 'last_name': 'User', 'email': f'agency{agency_id}@hydrabot.it', 'phone': '+000'}
            )
            profile.participants_json = json.dumps(participants)
            profile.save(update_fields=['participants_json'])
            return len(participants), "all tasks (profile)"

    count, target = await save_participants()
    ud['step'] = None
    ud.pop('participants_task_id', None)
    preview = '\n'.join(f"  {i+1}. {p['first_name']} {p['last_name']}" for i, p in enumerate(participants[:5]))
    if count > 5:
        preview += f"\n  ... and {count - 5} more"

    await update.message.reply_text(
        f"✅ *{count} participants saved for {target}!*\n\n{preview}\n\n"
        f"These names will be used for the next snipe booking.",
        parse_mode='Markdown',
        reply_markup=kb_back()
    )


# ── /bulkhold ─────────────────────────────────────────────────────────────────

async def bulkhold_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /bulkhold — manage bulk slot locking.

    Usage:
      /bulkhold                          — show active configs + held slot count
      /bulkhold start YYYY-MM-DD YYYY-MM-DD HH:MM HH:MM <visitors>
                                         — start bulk hold for date range + time window
      /bulkhold stop <id>                — pause a config
      /bulkhold release <id>             — release all held slots for a config
    """
    from asgiref.sync import sync_to_async
    from datetime import date as date_type

    agency = await get_agency(update.effective_chat.id)
    if not agency:
        await update.message.reply_text("⚠️ Chat not linked to an agency.")
        return

    args = context.args or []

    # ── Status (no args) ──────────────────────────────────────────────────────
    if not args:
        @sync_to_async
        def get_status():
            from monitors.models import BulkHoldConfig, HeldSlot
            configs = list(BulkHoldConfig.objects.filter(agency=agency).order_by('-created_at')[:10])
            held_count = HeldSlot.objects.filter(status__in=['held','paying']).count()
            return configs, held_count

        configs, held_count = await get_status()

        if not configs:
            await update.message.reply_text(
                f"🔒 *Bulk Hold Manager*\n\n"
                f"No configs yet. Start one:\n"
                f"`/bulkhold start 2026-04-15 2026-05-15 08:30 14:30 2`\n\n"
                f"_(date\\_from date\\_to time\\_from time\\_to visitors)_",
                parse_mode='Markdown'
            )
            return

        lines = [f"🔒 *Bulk Hold Manager* — {held_count} slots currently locked\n"]
        for c in configs:
            status = "▶️ active" if c.is_active else "⏸ paused"
            lines.append(
                f"#{c.id} {status} | {c.date_from}→{c.date_to} | "
                f"{c.time_from}-{c.time_to} | {c.visitors}v | "
                f"{c.total_locked} locked"
            )
        lines.append(f"\n`/bulkhold stop <id>` — pause\n`/bulkhold release <id>` — release all slots")
        await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')
        return

    # ── Start ─────────────────────────────────────────────────────────────────
    if args[0] == 'start':
        if len(args) < 6:
            await update.message.reply_text(
                "Usage: `/bulkhold start YYYY-MM-DD YYYY-MM-DD HH:MM HH:MM <visitors>`\n"
                "Example: `/bulkhold start 2026-04-15 2026-06-15 08:30 14:30 2`",
                parse_mode='Markdown'
            )
            return
        try:
            date_from = datetime.strptime(args[1], '%Y-%m-%d').date()
            date_to = datetime.strptime(args[2], '%Y-%m-%d').date()
            time_from = args[3]  # HH:MM
            time_to = args[4]    # HH:MM
            visitors = int(args[5])
        except (ValueError, IndexError) as e:
            await update.message.reply_text(f"❌ Invalid format: {e}")
            return

        if date_from > date_to:
            await update.message.reply_text("❌ date_from must be before date_to")
            return

        days = (date_to - date_from).days + 1

        @sync_to_async
        def create_config():
            from monitors.models import BulkHoldConfig
            return BulkHoldConfig.objects.create(
                agency=agency,
                date_from=date_from, date_to=date_to,
                time_from=time_from, time_to=time_to,
                visitors=visitors, is_active=True,
            )

        cfg = await create_config()

        # Trigger immediate scan
        try:
            from monitors.tasks_bulk_hold import bulk_hold_scan
            await sync_to_async(bulk_hold_scan.apply_async)(queue='vatican', countdown=2)
        except Exception:
            pass

        await update.message.reply_text(
            f"✅ *Bulk Hold #{cfg.id} started!*\n\n"
            f"📅 {date_from} → {date_to} ({days} days)\n"
            f"⏰ {time_from} – {time_to}\n"
            f"👥 {visitors} visitors per slot\n\n"
            f"Scanning now... check `/bulkhold` in a minute for results.",
            parse_mode='Markdown'
        )
        return

    # ── Stop ──────────────────────────────────────────────────────────────────
    if args[0] == 'stop' and len(args) >= 2:
        cfg_id = int(args[1])

        @sync_to_async
        def pause_config():
            from monitors.models import BulkHoldConfig
            updated = BulkHoldConfig.objects.filter(id=cfg_id, agency=agency).update(is_active=False)
            return updated > 0

        ok = await pause_config()
        if ok:
            await update.message.reply_text(f"⏸ Bulk Hold #{cfg_id} paused. Held slots remain locked until keepalive stops.")
        else:
            await update.message.reply_text(f"❌ Config #{cfg_id} not found.")
        return

    # ── Release ───────────────────────────────────────────────────────────────
    if args[0] == 'release' and len(args) >= 2:
        cfg_id = int(args[1])

        @sync_to_async
        def release_slots():
            from monitors.models import BulkHoldConfig, HeldSlot
            import json
            cfg = BulkHoldConfig.objects.filter(id=cfg_id, agency=agency).first()
            if not cfg:
                return 0, False
            cfg.is_active = False
            cfg.save(update_fields=['is_active'])
            # Mark all held slots from this config as released
            count = 0
            for h in HeldSlot.objects.filter(status__in=['held','paying']):
                try:
                    notes = json.loads(h.notes or '{}')
                    if notes.get('bulk_hold_config') == cfg_id:
                        h.status = 'released'
                        h.released_at = timezone.now()
                        h.save(update_fields=['status', 'released_at'])
                        count += 1
                except Exception:
                    pass
            return count, True

        count, found = await release_slots()
        if found:
            await update.message.reply_text(
                f"🔓 Bulk Hold #{cfg_id} stopped.\n{count} slots released."
            )
        else:
            await update.message.reply_text(f"❌ Config #{cfg_id} not found.")
        return

    await update.message.reply_text(
        "Unknown command. Use `/bulkhold` to see options.", parse_mode='Markdown'
    )


# ── /setpaymode ───────────────────────────────────────────────────────────────

async def setpaymode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setpaymode <task_id> <link|auto>
    Set pay mode for a snipe task:
      link — send payment URL to Telegram (user pays themselves, no card stored)
      auto — auto-pay with stored card via Playwright
    """
    from asgiref.sync import sync_to_async

    agency = await get_agency(update.effective_chat.id)
    if not agency:
        await update.message.reply_text("⚠️ Chat not linked to an agency.")
        return

    args = context.args or []

    @sync_to_async
    def get_snipe_tasks():
        from monitors.models import MonitorTask
        return list(MonitorTask.objects.filter(agency=agency, tier='snipe', is_active=True)
                    .values('id', 'area_name', 'visitors', 'pay_mode'))

    tasks = await get_snipe_tasks()
    if not tasks:
        await update.message.reply_text("⚠️ No active snipe tasks found.")
        return

    if len(args) < 2 or not args[0].isdigit() or args[1] not in ('link', 'auto'):
        lines = ["⚙️ *Pay Mode Settings*\n\n"
                 "`/setpaymode <task_id> link` — send payment link to Telegram\n"
                 "`/setpaymode <task_id> auto` — auto-pay with stored card\n\n"
                 "*Current tasks:*"]
        for t in tasks:
            mode_icon = "🔗" if t['pay_mode'] == 'link' else "💳"
            lines.append(f"• Task #{t['id']} | {t['area_name']} | {t['visitors']}v | {mode_icon} {t['pay_mode']}")
        await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')
        return

    task_id = int(args[0])
    new_mode = args[1]

    @sync_to_async
    def update_pay_mode():
        from monitors.models import MonitorTask
        updated = MonitorTask.objects.filter(id=task_id, agency=agency, tier='snipe').update(pay_mode=new_mode)
        return updated > 0

    ok = await update_pay_mode()
    if ok:
        icon = "🔗" if new_mode == 'link' else "💳"
        desc = "payment link sent to Telegram" if new_mode == 'link' else "auto-pay with stored card"
        await update.message.reply_text(
            f"✅ Task #{task_id} pay mode set to {icon} *{new_mode}*\n_{desc}_",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(f"❌ Task #{task_id} not found or not a snipe task.")


async def setbrowsergroup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setbrowsergroup — set this group as the browser trigger group.
    When a slot is found, the bot sends a [🌐 Open Browser] button here.
    Run this command IN the group you want to use (e.g. WOR group).
    """
    chat = update.effective_chat
    chat_id = str(chat.id)
    chat_title = chat.title or chat.first_name or chat_id

    # Store in cache so local agent can read it
    from django.core.cache import cache
    cache.set('browser_trigger_group', {'chat_id': chat_id, 'title': chat_title}, timeout=None)

    await update.message.reply_text(
        f"✅ *Browser trigger group set!*\n\n"
        f"Group: *{chat_title}*\n"
        f"Chat ID: `{chat_id}`\n\n"
        f"When a slot is detected, the bot will send a [🌐 Open Browser] button here.\n"
        f"Click it to open Chrome on the agent machine.\n\n"
        f"Make sure `run_agent.bat` is running on your Windows machine.",
        parse_mode='Markdown'
    )


# ── Group join/leave handler ──────────────────────────────────────────────────

def extract_status_change(chat_member_update: ChatMemberUpdated):
    status_change = chat_member_update.difference().get("status")
    old_is_member, new_is_member = chat_member_update.difference().get("is_member", (None, None))
    if status_change is None:
        return None
    old_status, new_status = status_change
    was_member = old_status in [ChatMember.MEMBER, ChatMember.OWNER, ChatMember.ADMINISTRATOR] \
        or (old_status == ChatMember.RESTRICTED and old_is_member is True)
    is_member = new_status in [ChatMember.MEMBER, ChatMember.OWNER, ChatMember.ADMINISTRATOR] \
        or (new_status == ChatMember.RESTRICTED and new_is_member is True)
    return was_member, is_member


async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from asgiref.sync import sync_to_async
    from django.utils import timezone
    result = extract_status_change(update.my_chat_member)
    if result is None:
        return
    was_member, is_member = result
    chat = update.effective_chat
    user = update.effective_user

    if not was_member and is_member:
        logger.info(f"Bot added to {chat.type}: {chat.title} (ID: {chat.id})")
        group, created = await sync_to_async(TelegramGroup.objects.get_or_create)(
            chat_id=str(chat.id),
            defaults={
                'chat_type': chat.type,
                'chat_title': chat.title,
                'chat_username': chat.username,
                'added_by_user_id': str(user.id),
                'added_by_username': user.username,
                'added_by_first_name': user.first_name,
                'status': 'pending',
                'last_activity': timezone.now()
            }
        )

        # Update title/username if group already existed
        if not created:
            group.chat_title = chat.title
            group.chat_username = chat.username
            group.status = 'pending'  # reset to pending on re-add
            await sync_to_async(group.save)(update_fields=['chat_title', 'chat_username', 'status'])

        # Always notify the group itself
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=f"👋 *Vatican Monitor Bot added!*\n\n🔒 Pending admin approval.\nGroup ID: `{chat.id}`",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to message group {chat.id}: {e}")

        # Always notify ALL admins with approve/reject buttons
        approve_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve:{chat.id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject:{chat.id}")
        ]])
        admin_ids = [a.strip() for a in os.getenv('ADMIN_TELEGRAM_IDS', '').split(',') if a.strip()]
        for aid in admin_ids:
            try:
                await context.bot.send_message(
                    chat_id=aid,
                    text=(
                        f"🔔 *New group approval request*\n\n"
                        f"Group: *{chat.title}*\n"
                        f"ID: `{chat.id}`\n"
                        f"Type: {chat.type}\n"
                        f"Added by: {user.first_name} (@{user.username or 'N/A'})\n\n"
                        f"Approve or reject below:"
                    ),
                    parse_mode='Markdown',
                    reply_markup=approve_kb
                )
                logger.info(f"✅ Admin {aid} notified about group {chat.id}")
            except Exception as e:
                logger.error(f"Failed to notify admin {aid}: {e}")
    elif was_member and not is_member:
        group = await sync_to_async(TelegramGroup.objects.filter(chat_id=str(chat.id)).first)()
        if group:
            group.status = 'suspended'
            await sync_to_async(group.save)()


async def book_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/book — interactive booking flow: select held date → slot → visitors → names → pay link."""
    agency = await get_agency(update.effective_chat.id)
    if not agency:
        await update.message.reply_text("⚠️ Chat not linked to an agency.")
        return
    context.user_data['agency_id'] = agency.id
    context.user_data.pop('booking', None)
    context.user_data['step'] = None

    from asgiref.sync import sync_to_async

    @sync_to_async
    def get_open_dates():
        from monitors.models import HeldSlot
        holds = HeldSlot.objects.filter(
            status__in=['held', 'paying']
        ).order_by('date', 'slot_time')
        # Group by date, keep only dates with time remaining
        dates = {}
        for h in holds:
            remaining = max(0, 24 - h.hold_duration_hours())
            if remaining > 0 and h.date not in dates:
                dates[h.date] = remaining
        return dates

    dates = await get_open_dates()
    if not dates:
        await update.message.reply_text(
            "🔓 No active holds right now.\n\nHolds are created automatically when slots open.",
            reply_markup=kb_back()
        )
        return

    rows = []
    for date, remaining in sorted(dates.items(), key=lambda x: x[0]):
        try:
            dt = datetime.strptime(date, '%d/%m/%Y')
            day_name = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][dt.weekday()]
        except Exception:
            day_name = ''
        rows.append([InlineKeyboardButton(
            f"📅 {date} ({day_name}) — ⏱ {remaining:.0f}h left",
            callback_data=f"book_date:{date}"
        )])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="book_cancel")])

    await update.message.reply_text(
        f"🏛️ *Vatican Booking*\n\n"
        f"Step 1/4 — Select a date:\n"
        f"({len(dates)} dates with active holds)",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(rows)
    )


async def do_book_start(query, context):
    """Called from callback — same as book_cmd but via inline button."""
    from asgiref.sync import sync_to_async

    @sync_to_async
    def get_open_dates():
        from monitors.models import HeldSlot
        holds = HeldSlot.objects.filter(status__in=['held', 'paying']).order_by('date')
        dates = {}
        for h in holds:
            remaining = max(0, 24 - h.hold_duration_hours())
            if remaining > 0 and h.date not in dates:
                dates[h.date] = remaining
        return dates

    dates = await get_open_dates()
    if not dates:
        await query.edit_message_text("🔓 No active holds.", reply_markup=kb_back())
        return

    rows = []
    for date, remaining in sorted(dates.items()):
        try:
            dt = datetime.strptime(date, '%d/%m/%Y')
            day_name = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][dt.weekday()]
        except Exception:
            day_name = ''
        rows.append([InlineKeyboardButton(
            f"📅 {date} ({day_name}) — ⏱ {remaining:.0f}h left",
            callback_data=f"book_date:{date}"
        )])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="book_cancel")])

    await query.edit_message_text(
        f"🏛️ *Vatican Booking*\n\nStep 1/4 — Select a date:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(rows)
    )


async def deep_scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/deep_scan <YYYY-MM-DD> — check every visitor count for hidden inventory."""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "🔎 *Deep Discovery Tool*\n\n"
            "Usage: `/deep_scan 2026-06-15`\n\n"
            "This will scan for 1, 2, 3, 4, 6, 8, and 10 visitors to find hidden slots.",
            parse_mode='Markdown'
        )
        return

    date_str = args[0]
    # Basic date validation
    if not ('-' in date_str and len(date_str) == 10):
        await update.message.reply_text("❌ Invalid date format. Use YYYY-MM-DD.")
        return

    await update.message.reply_text(
        f"🚀 *Starting Deep Discovery for {date_str}...*\n\n"
        f"Checking all visitor counts (1-10).\n"
        f"Results will be sent here in about 1 minute.",
        parse_mode='Markdown'
    )

    # Trigger Celery Task
    try:
        from monitors.tasks import run_deep_scan
        run_deep_scan.delay(date=date_str, chat_id=update.effective_chat.id)
    except Exception as e:
        logger.error(f"Failed to trigger deep scan: {e}")
        await update.message.reply_text(f"❌ Error starting scan: {e}")


async def do_book_select_slot(query, context, date_str):
    """Step 2 — show all available time slots for the selected date."""
    from asgiref.sync import sync_to_async

    @sync_to_async
    def get_slots_for_date():
        from monitors.models import HeldSlot
        holds = HeldSlot.objects.filter(
            date=date_str, status__in=['held', 'paying']
        ).order_by('slot_time', 'visitors')
        slots = {}
        for h in holds:
            remaining = max(0, 24 - h.hold_duration_hours())
            if remaining > 0:
                if h.slot_time not in slots:
                    slots[h.slot_time] = []
                slots[h.slot_time].append(h.visitors)
        return slots

    slots = await get_slots_for_date()
    if not slots:
        await query.edit_message_text(f"❌ No slots for {date_str}.", reply_markup=kb_back())
        return

    rows = []
    for slot_time, visitor_counts in sorted(slots.items()):
        max_v = max(visitor_counts)
        rows.append([InlineKeyboardButton(
            f"⏰ {slot_time} — up to {max_v} {'person' if max_v == 1 else 'people'}",
            callback_data=f"book_slot_time:{date_str}:{slot_time}"
        )])
    rows.append([InlineKeyboardButton("◀️ Back", callback_data="book")])

    await query.edit_message_text(
        f"🏛️ *Vatican Booking*\n\n"
        f"📅 Date: {date_str}\n\n"
        f"Step 2/4 — Select a time slot:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(rows)
    )


async def do_book_show_visitor_options(query, context, date_str, slot_time):
    """Step 3 — show visitor count options for the selected date+time."""
    from asgiref.sync import sync_to_async

    @sync_to_async
    def get_holds_for_slot():
        from monitors.models import HeldSlot
        return list(HeldSlot.objects.filter(
            date=date_str, slot_time=slot_time,
            status__in=['held', 'paying']
        ).order_by('visitors'))

    siblings = await get_holds_for_slot()
    if not siblings:
        await query.edit_message_text("❌ No holds for this slot.", reply_markup=kb_back())
        return

    rows = []
    for s in siblings:
        remaining = max(0, 24 - s.hold_duration_hours())
        if remaining <= 0:
            continue
        rows.append([InlineKeyboardButton(
            f"👥 {s.visitors} {'person' if s.visitors == 1 else 'people'} — €{s.total_price} (⏱ {remaining:.0f}h left)",
            callback_data=f"book_vis:{s.id}:{s.visitors}"
        )])
    rows.append([InlineKeyboardButton("◀️ Back", callback_data=f"book_date:{date_str}")])

    await query.edit_message_text(
        f"🏛️ *Vatican Booking*\n\n"
        f"📅 {date_str} {slot_time}\n\n"
        f"Step 3/4 — How many people?",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(rows)
    )


async def do_book_select_visitors(query, context, hold_id):
    """Kept for backward compat — redirects to show_visitor_options."""
    from asgiref.sync import sync_to_async

    @sync_to_async
    def get_hold(hid):
        from monitors.models import HeldSlot
        return HeldSlot.objects.filter(id=hid).first()

    held = await get_hold(hold_id)
    if not held:
        await query.edit_message_text("❌ Hold not found.", reply_markup=kb_back())
        return
    await do_book_show_visitor_options(query, context, held.date, held.slot_time)


async def do_book_ask_names(query, context, hold_id, visitors):
    """Step 4 — ask for participant names one by one."""
    from asgiref.sync import sync_to_async

    @sync_to_async
    def get_hold(hid):
        from monitors.models import HeldSlot
        return HeldSlot.objects.filter(id=hid).first()

    held = await get_hold(hold_id)
    if not held:
        await query.edit_message_text("❌ Hold not found.", reply_markup=kb_back())
        return

    # Store booking state
    context.user_data['booking'] = {
        'hold_id': hold_id,
        'visitors': visitors,
        'date': held.date,
        'slot_time': held.slot_time,
        'total': held.total_price,
        'names': [],
    }
    context.user_data['step'] = 'book_name'

    await query.edit_message_text(
        f"🏛️ *Vatican Booking*\n\n"
        f"📅 {held.date} {held.slot_time}\n"
        f"👥 {visitors} {'person' if visitors == 1 else 'people'} | €{held.total_price}\n\n"
        f"Step 4/4 — Enter participant names\n\n"
        f"Send *Participant 1/{visitors}* name:\n"
        f"Format: `FirstName LastName`\n\n"
        f"Example: `John Doe`",
        parse_mode='Markdown'
    )


async def do_book_generate_link(query, context, hold_id):
    """Final step — inject names, generate payment link, send to user."""
    from asgiref.sync import sync_to_async
    import secrets

    booking = context.user_data.get('booking', {})
    names = booking.get('names', [])
    visitors = booking.get('visitors', 1)

    @sync_to_async
    def build_link(hid, participant_names, num_visitors):
        from monitors.models import HeldSlot, BuyerProfile
        from django.core.cache import cache
        import os

        held = HeldSlot.objects.select_related('task__agency').filter(id=hid).first()
        if not held:
            return None, "Hold not found"
        if held.hold_duration_hours() >= 24:
            return None, "Hold expired (24h limit)"

        # Get buyer profile for representative info
        try:
            profile = BuyerProfile.objects.get(agency=held.task.agency)
        except BuyerProfile.DoesNotExist:
            return None, "No buyer profile set. Run /setprofile first."

        # Build participant list from entered names
        participants = []
        for i, n in enumerate(participant_names[:num_visitors]):
            participants.append({
                'first_name': n.get('first_name', profile.first_name),
                'last_name': n.get('last_name', profile.last_name),
            })
        # Pad if needed
        while len(participants) < num_visitors:
            participants.append({
                'first_name': profile.first_name,
                'last_name': profile.last_name,
            })

        # Representative = profile data
        representative = {
            'first_name': profile.first_name,
            'last_name': profile.last_name,
            'email': profile.email,
            'phone': profile.phone,
            'country': profile.country,
            'city': profile.city,
            'birth_date': profile.birth_date.strftime('%Y-%m-%dT%H:%M:%S.000Z') if profile.birth_date else None,
            'gender': profile.gender,
            'language': profile.language or 'en',
        }

        # Generate single-use token (30 min expiry)
        token = secrets.token_urlsafe(32)
        cache.set(f"epay_token:{hid}:{token}", {
            'hold_id': hid,
            'participants': participants,
            'representative': representative,
        }, timeout=1800)

        base = os.getenv('SERVER_BASE_URL', 'https://hydrabot.it')
        payment_url = f"{base}/pay/{hid}/{token}/"

        return {
            'url': payment_url,
            'date': held.date,
            'time': held.slot_time,
            'visitors': num_visitors,
            'total': held.total_price,
            'remaining': max(0, 24 - held.hold_duration_hours()),
            'participants': participants,
            'rep_name': f"{profile.first_name} {profile.last_name}",
            'rep_email': profile.email,
        }, None

    result, error = await build_link(hold_id, names, visitors)

    # Clear booking state
    context.user_data.pop('booking', None)
    context.user_data['step'] = None

    if error:
        await query.edit_message_text(f"❌ {error}", reply_markup=kb_back())
        return

    # Format participant preview
    p_lines = '\n'.join(
        f"  {i+1}. {p['first_name']} {p['last_name']}"
        for i, p in enumerate(result['participants'])
    )

    await query.edit_message_text(
        f"✅ *Payment Link Ready!*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 {result['date']} {result['time']}\n"
        f"👥 {result['visitors']} visitors | €{result['total']}\n"
        f"⏱ {result['remaining']:.0f}h remaining\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 *Participants:*\n{p_lines}\n\n"
        f"🧾 *Billing:* {result['rep_name']} ({result['rep_email']})\n\n"
        f"💳 *Open this link to pay:*\n"
        f"{result['url']}\n\n"
        f"⚠️ Single-use · Valid 30 minutes\n"
        f"Opens Vatican payment page in any browser",
        parse_mode='Markdown',
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Book Another", callback_data="book")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")],
        ])
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Single callback handler handles everything
    app.add_handler(CallbackQueryHandler(on_callback))

    # ============================================================================
    # CORE COMMANDS - Synced with Extension
    # ============================================================================
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('add', add_cmd))  # Create monitoring task
    app.add_handler(CommandHandler('monitor', add_cmd))  # Alias for /add
    app.add_handler(CommandHandler('cancel', cancel_cmd))
    app.add_handler(CommandHandler('setprofile', setprofile_cmd))
    app.add_handler(CommandHandler('setparticipants', setparticipants_cmd))
    app.add_handler(CommandHandler('holds', holds_cmd))  # View held slots
    app.add_handler(CommandHandler('snipes', snipes_cmd))  # View active monitors
    app.add_handler(CommandHandler('status', status_cmd))  # Global status overview
    app.add_handler(CommandHandler('pending_info', pending_cmd))  # Tasks needing info
    app.add_handler(CommandHandler('ask', ask_cmd))  # AI Assistant - CRM queries
    app.add_handler(CommandHandler('ai', ask_cmd))  # Alias for /ask

    # ============================================================================
    # ADMIN COMMANDS
    # ============================================================================
    app.add_handler(CommandHandler('pending', pending_cmd))  # Approve groups
    
    # ============================================================================
    # REMOVED COMMANDS - Extension handles these automatically
    # ============================================================================
    # ❌ /pay - Extension books automatically
    # ❌ /open - Extension opens windows automatically
    # ❌ /agent - Extension replaces browser agent
    # ❌ /book - Extension completes booking automatically
    # ❌ /stop_recap - Not needed with extension
    # ❌ /resume_recap - Not needed with extension
    # ❌ /setpaymode - Extension always auto-pays
    # ❌ /setbrowsergroup - Extension polls API directly
    # ❌ /bulkhold - Complex feature, rarely used
    # ❌ /deep_scan - Advanced feature, rarely used

    # Text input (for manual date entry, profile steps)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Document upload (participant list)
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))

    # Group join/leave
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    logger.info("🤖 Telegram bot starting...")
    logger.info("✅ Extension-synced mode: Automatic booking enabled")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
