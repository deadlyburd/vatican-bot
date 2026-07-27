"""
WhatsApp Webhook Handler
=========================
Process incoming WhatsApp messages from Meta's webhook.
Verifies the webhook and routes messages to the WhatsApp bot.
"""

import json
import logging
import hmac
import hashlib
import os

from django.http import HttpResponse, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from customer_care.channels.whatsapp_bot import whatsapp_bot, send_whatsapp_message

logger = logging.getLogger(__name__)

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "vatican_bot_verify_2024")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")


def verify_whatsapp_signature(body: bytes, signature: str) -> bool:
    """Verify the request signature from Meta."""
    if not WHATSAPP_APP_SECRET:
        return True  # Skip verification if not configured
    try:
        expected = hmac.new(
            WHATSAPP_APP_SECRET.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        received = signature.replace("sha256=", "")
        return hmac.compare_digest(expected, received)
    except Exception:
        return False


@method_decorator(csrf_exempt, name="dispatch")
class WhatsAppWebhookView(View):
    """
    Meta WhatsApp Business Cloud API webhook.

    GET  — webhook verification (Meta sends hub.challenge)
    POST — incoming messages
    """

    def get(self, request, *args, **kwargs):
        """Verify webhook for Meta."""
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
            logger.info("✅ WhatsApp webhook verified")
            return HttpResponse(challenge, status=200)

        logger.warning(f"❌ WhatsApp webhook verification failed: mode={mode}")
        return HttpResponse("Forbidden", status=403)

    def post(self, request, *args, **kwargs):
        """Process incoming WhatsApp message."""
        try:
            body = request.body

            # Verify signature
            signature = request.headers.get("X-Hub-Signature-256", "")
            if not verify_whatsapp_signature(body, signature):
                logger.warning("WhatsApp signature verification failed")
                return HttpResponse("Unauthorized", status=401)

            data = json.loads(body)

            # Check if this is a WhatsApp message
            if data.get("object") != "whatsapp_business_account":
                return HttpResponse("OK", status=200)

            entries = data.get("entry", [])
            for entry in entries:
                changes = entry.get("changes", [])
                for change in changes:
                    if change.get("field") != "messages":
                        continue

                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    contacts = value.get("contacts", [])

                    for msg in messages:
                        self._process_message(msg, contacts)

            return HttpResponse("OK", status=200)

        except json.JSONDecodeError:
            return HttpResponse("Invalid JSON", status=400)
        except Exception as e:
            logger.error(f"WhatsApp webhook error: {e}")
            return HttpResponse("Error", status=500)

    def _process_message(self, msg: dict, contacts: list):
        """Process a single WhatsApp message."""
        try:
            from_phone = msg.get("from", "")
            msg_type = msg.get("type", "text")
            msg_id = msg.get("id", "")

            if msg_type != "text":
                # Handle media messages (send prompt)
                send_whatsapp_message(
                    from_phone,
                    "📎 I see you sent media! For the fastest help, please describe your question in text. "
                    "You can also email us at your-email@example.com"
                )
                return

            text = msg.get("text", {}).get("body", "")
            if not text:
                return

            logger.info(f"📱 WhatsApp from {from_phone}: {text[:100]}")

            # Process through the bot
            response = whatsapp_bot.process_message(from_phone, text)

            # Send response back
            send_whatsapp_message(from_phone, response)

        except Exception as e:
            logger.error(f"Error processing WhatsApp message: {e}")


@method_decorator(csrf_exempt, name="dispatch")
class WhatsAppSendView(View):
    """API endpoint to send WhatsApp messages programmatically."""

    def post(self, request, *args, **kwargs):
        """Send a WhatsApp message."""
        try:
            data = json.loads(request.body)
            phone = data.get("phone", "")
            message = data.get("message", "")

            if not phone or not message:
                return JsonResponse({"error": "phone and message required"}, status=400)

            result = send_whatsapp_message(phone, message)
            if result:
                return JsonResponse({"status": "ok", "message_id": result.get("messages", [{}])[0].get("id")})
            else:
                return JsonResponse({"error": "Failed to send"}, status=500)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
