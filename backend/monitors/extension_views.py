"""
Extension Bridge API — Backend ↔ Chrome Extension Communication
=================================================================
The extension polls these endpoints for booking commands.
The backend creates commands when SlotFinder finds available slots for CRM bookings.
"""

import json
import logging
import uuid
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.cache import cache  # Uses Redis when configured

logger = logging.getLogger(__name__)

# Redis key prefixes
COMMANDS_KEY = "ext:commands"          # Hash: cmd_id → command JSON
COMMANDS_QUEUE = "ext:cmd_queue"       # List: pending command IDs
COMMANDS_PROGRESS = "ext:progress"     # Hash: cmd_id → progress JSON
COMMANDS_COMPLETE = "ext:completed"    # List: completed command IDs

# TTL for command data (24 hours)
CMD_TTL = 86400


def _redis():
    """Get Redis client from Django cache."""
    try:
        return cache.client.get_client()
    except Exception:
        return None


def _gen_id():
    return f"cmd_{uuid.uuid4().hex[:12]}"


# ── Extension: Poll for pending commands ──────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
def extension_commands(request):
    """
    Extension polls this every 5 seconds to get pending booking commands.

    Returns:
        {
            "commands": [
                {
                    "id": "cmd_abc123",
                    "date": "28/07/2026",
                    "time": "09:00",
                    "visitors": 2,
                    "ticket_id": "123",
                    "ticket_name": "Musei Vaticani - Ingresso",
                    "ticket_type": "standard",
                    "priority": 1,
                    "profile": {...},
                    "participants": [...],
                    "booking_id": "BKG-001",
                    "customer_name": "...",
                    "customer_email": "...",
                }
            ]
        }
    """
    r = _redis()
    pending = []

    if r:
        # Get pending command IDs from queue
        cmd_ids = r.lrange(COMMANDS_QUEUE, 0, 5)
        for cid in cmd_ids:
            cid = cid.decode() if isinstance(cid, bytes) else cid
            data = r.hget(COMMANDS_KEY, cid)
            if data:
                cmd = json.loads(data.decode() if isinstance(data, bytes) else data)
                cmd["id"] = cid
                pending.append(cmd)
    else:
        # Fallback to local cache
        cmd_ids = cache.get(COMMANDS_QUEUE, [])
        for cid in cmd_ids[:5]:
            cmd = cache.get(f"{COMMANDS_KEY}:{cid}")
            if cmd:
                cmd["id"] = cid
                pending.append(cmd)

    return JsonResponse({"commands": pending})


# ── Extension: Claim a command ────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def extension_claim(request, cmd_id):
    """
    Extension claims a command — moves it from pending to in_progress.
    """
    r = _redis()

    if r:
        r.lrem(COMMANDS_QUEUE, 0, cmd_id)
        # Update status in the command data
        data_raw = r.hget(COMMANDS_KEY, cmd_id)
        if data_raw:
            cmd = json.loads(data_raw.decode() if isinstance(data_raw, bytes) else data_raw)
            cmd["status"] = "in_progress"
            cmd["claimed_at"] = datetime.utcnow().isoformat()
            r.hset(COMMANDS_KEY, cmd_id, json.dumps(cmd))
    else:
        queue = cache.get(COMMANDS_QUEUE, [])
        if cmd_id in queue:
            queue.remove(cmd_id)
            cache.set(COMMANDS_QUEUE, queue, CMD_TTL)

    return JsonResponse({"status": "claimed"})


# ── Extension: Report progress ────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def extension_progress(request, cmd_id):
    """
    Extension reports booking progress (step by step).
    Body: {"step": "ticket_selected", "details": {...}}
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        body = {}

    step = body.get("step", "unknown")
    details = body.get("details", {})

    r = _redis()
    if r:
        progress = json.dumps({
            "step": step,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
        })
        r.hset(COMMANDS_PROGRESS, cmd_id, progress)
    else:
        cache.set(f"{COMMANDS_PROGRESS}:{cmd_id}", {
            "step": step, "details": details,
            "timestamp": datetime.utcnow().isoformat(),
        }, CMD_TTL)

    logger.info(f"📋 Extension progress [{cmd_id}]: {step}")
    return JsonResponse({"status": "ok"})


# ── Extension: Report completion ──────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def extension_complete(request, cmd_id):
    """
    Extension reports successful booking completion.
    Body: {
        "epay_url": "https://epay.catholica.va/...",
        "duration_seconds": 45.2,
        "steps": ["ticket_selected", "time_selected", ...]
    }
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        body = {}

    epay_url = body.get("epay_url", "")
    duration = body.get("duration_seconds", 0)
    steps = body.get("steps", [])

    logger.info(f"🎉 Extension booking COMPLETE [{cmd_id}]: {epay_url[:80]}")

    # Get original command to access CRM data
    r = _redis()
    cmd = {}
    if r:
        data = r.hget(COMMANDS_KEY, cmd_id)
        if data:
            cmd = json.loads(data.decode() if isinstance(data, bytes) else data)
        r.hdel(COMMANDS_KEY, cmd_id)
        mark_completed = r.lpush(COMMANDS_COMPLETE, cmd_id)
    else:
        cmd = cache.get(f"{COMMANDS_KEY}:{cmd_id}", {})
        cache.delete(f"{COMMANDS_KEY}:{cmd_id}")

    # ── Write to CRM Sheet & Notify Telegram ─────────────────────
    booking_id = cmd.get("booking_id", "")
    date_str = cmd.get("date", "")
    customer_name = cmd.get("customer_name", "")
    customer_email = cmd.get("customer_email", "")
    visitors = cmd.get("visitors", 0)
    time_slot = cmd.get("time", "")

    # Notify admin via Telegram
    try:
        from crm_intelligence.auto_snipe import auto_snipe_service
        msg = (
            f"🎉 *Booking Complete!*\n\n"
            f"📅 {date_str} at {time_slot}\n"
            f"👥 {visitors} visitors\n"
            f"👤 {customer_name or 'CRM Booking'}\n"
            f"📧 {customer_email or 'N/A'}\n\n"
            f"💳 [Payment Link]({epay_url})\n\n"
            f"⏱ Completed in {duration}s\n"
            f"_Auto-booked via Chrome extension_"
        )
        auto_snipe_service.notify_admin(msg)

        # Write payment link to sheet
        if booking_id and epay_url:
            auto_snipe_service.write_payment_link_to_sheet(
                booking_id, date_str, epay_url
            )
    except Exception as e:
        logger.error(f"Post-booking notification error: {e}")

    return JsonResponse({
        "status": "complete",
        "sheet_updated": bool(booking_id and epay_url),
        "notified": True,
    })


# ── Extension: Report failure ─────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def extension_fail(request, cmd_id):
    """
    Extension reports booking failure.
    Body: {"error": "No available time slot", "steps": [...]}
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        body = {}

    error = body.get("error", "Unknown error")
    steps = body.get("steps", [])

    logger.warning(f"❌ Extension booking FAILED [{cmd_id}]: {error}")

    # Re-queue if it's a retryable error
    retryable = any(w in error.lower() for w in [
        'timeout', 'navigation', 'page', 'time slot',
        'element', 'not found', 'render',
    ])

    r = _redis()
    if r and retryable:
        data = r.hget(COMMANDS_KEY, cmd_id)
        if data:
            cmd = json.loads(data.decode() if isinstance(data, bytes) else data)
            retries = cmd.get("retries", 0)
            if retries < 3:
                cmd["retries"] = retries + 1
                r.hset(COMMANDS_KEY, cmd_id, json.dumps(cmd))
                r.rpush(COMMANDS_QUEUE, cmd_id)  # Re-queue
                logger.info(f"Re-queued [{cmd_id}] (retry {retries + 1}/3)")
                return JsonResponse({"status": "requeued", "retry": retries + 1})

    # Notify admin of failure
    try:
        from crm_intelligence.auto_snipe import auto_snipe_service
        auto_snipe_service.notify_admin(
            f"⚠️ *Booking Failed*\n\n"
            f"Error: {error}\n"
            f"Steps completed: {', '.join(steps) if steps else 'none'}\n"
            f"Retries exhausted — manual intervention needed."
        )
    except Exception:
        pass

    return JsonResponse({"status": "failed"})


# ── Backend: Create a booking command ─────────────────────────────────

def create_extension_command(
    date: str,
    visitors: int,
    time_slot: str = None,
    ticket_id: str = None,
    ticket_name: str = "",
    profile: dict = None,
    participants: list = None,
    booking_id: str = "",
    customer_name: str = "",
    customer_email: str = "",
    customer_phone: str = "",
    priority: int = 1,
) -> str:
    """
    Create a booking command that the extension will pick up.
    Called by CRM scanner or manual snipe trigger.

    Returns the command ID.
    """
    cmd_id = _gen_id()

    cmd = {
        "date": date,
        "visitors": visitors,
        "time": time_slot,
        "ticket_id": ticket_id,
        "ticket_name": ticket_name,
        "ticket_type": "standard",
        "priority": priority,
        "profile": profile or {},
        "participants": participants or [],
        "booking_id": booking_id,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "customer_phone": customer_phone,
        "status": "pending",
        "retries": 0,
        "created_at": datetime.utcnow().isoformat(),
    }

    r = _redis()
    if r:
        r.hset(COMMANDS_KEY, cmd_id, json.dumps(cmd))
        r.rpush(COMMANDS_QUEUE, cmd_id)
    else:
        cache.set(f"{COMMANDS_KEY}:{cmd_id}", cmd, CMD_TTL)
        queue = cache.get(COMMANDS_QUEUE, [])
        queue.append(cmd_id)
        cache.set(COMMANDS_QUEUE, queue, CMD_TTL)

    logger.info(f"📤 Extension command created: {cmd_id} — {date} {time_slot or 'any'} — {visitors}v")
    return cmd_id


# ── Backend: Report completion without command ID ─────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def extension_booking_complete(request):
    """
    Extension reports completion when it didn't have a cmd_id.
    Body: {
        "date": "28/07/2026",
        "time": "09:00",
        "visitors": 2,
        "epay_url": "https://epay.catholica.va/...",
        "duration_seconds": 45.2,
        "steps": [...],
    }
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        body = {}

    epay_url = body.get("epay_url", "")
    date_str = body.get("date", "")
    time_slot = body.get("time", "")
    visitors = body.get("visitors", 0)
    duration = body.get("duration_seconds", 0)

    logger.info(f"🎉 Extension booking complete (no cmd_id): {date_str} {time_slot} — {epay_url[:80]}")

    # Notify admin
    try:
        from crm_intelligence.auto_snipe import auto_snipe_service
        auto_snipe_service.notify_admin(
            f"🎉 *Booking Complete!*\n\n"
            f"📅 {date_str} at {time_slot}\n"
            f"👥 {visitors} visitors\n\n"
            f"💳 [Payment Link]({epay_url})\n\n"
            f"⏱ Completed in {duration}s"
        )
    except Exception as e:
        logger.error(f"Notification error: {e}")

    return JsonResponse({"status": "ok"})
