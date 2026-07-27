"""
Django-integrated Customer Care Bot
=====================================
Runs the tourist care bot as part of the Django application.
Adds API endpoints for admin dashboard to interact with the bot.
"""

import os
import logging
import json
from typing import Dict, Any

from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings

from telegram import Update

from customer_care.bot.tourist_care_bot import TouristCareBot
from crm_intelligence.parsers.sheet_parser import SheetParser
from crm_intelligence.ai.crm_analyzer import CRMAnalyzer

logger = logging.getLogger(__name__)

# Global bot instance
_bot_instance = None
_bot_application = None


def get_bot() -> TouristCareBot:
    """Get or create the bot singleton."""
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = TouristCareBot()
    return _bot_instance


def get_application():
    """Get or create the bot application."""
    global _bot_application
    if _bot_application is None:
        bot = get_bot()
        _bot_application = bot.get_application()
    return _bot_application


@method_decorator(csrf_exempt, name='dispatch')
class TelegramWebhookView(View):
    """Handle Telegram webhook updates."""

    async def post(self, request, *args, **kwargs):
        """Process incoming Telegram update."""
        try:
            application = get_application()
            data = json.loads(request.body)
            update = Update.de_json(data, application.bot)
            await application.process_update(update)
            return HttpResponse("OK", status=200)
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return HttpResponse("Error", status=500)


@method_decorator(csrf_exempt, name='dispatch')
class BotStatusView(View):
    """Get bot status and CRM data for admin dashboard."""

    def get(self, request, *args, **kwargs):
        """Return bot status and CRM summary."""
        try:
            bot = get_bot()
            bot._ensure_crm_loaded()

            if not bot.analyzer:
                return JsonResponse({"status": "error", "message": "CRM not loaded"})

            # Get insights
            insights = bot.analyzer.analyze_all()

            # Get summary stats
            bookings_count = len(bot.analyzer.bookings)
            activities_count = len(bot.analyzer.activities)
            products_count = len(bot.analyzer.products)

            # Count unique customers
            emails = set(b.get("customerEmail", "") for b in bot.analyzer.bookings if b.get("customerEmail"))

            # Upcoming bookings
            upcoming = bot.parser.get_upcoming_bookings(days_ahead=30)

            return JsonResponse({
                "status": "ok",
                "stats": {
                    "total_bookings": bookings_count,
                    "total_activities": activities_count,
                    "total_products": products_count,
                    "unique_customers": len(emails),
                    "upcoming_30_days": len(upcoming),
                },
                "insights": [
                    {
                        "category": i.category,
                        "title": i.title,
                        "description": i.description,
                        "confidence": i.confidence,
                        "priority": i.priority,
                        "action_required": i.action_required,
                    }
                    for i in insights[:20]
                ],
            })
        except Exception as e:
            logger.error(f"Status error: {e}")
            return JsonResponse({"status": "error", "message": str(e)})


@method_decorator(csrf_exempt, name='dispatch')
class CustomerLookupView(View):
    """Look up a customer by email for the admin dashboard."""

    def get(self, request, *args, **kwargs):
        """Look up customer by email."""
        email = request.GET.get("email", "").strip().lower()
        if not email:
            return JsonResponse({"error": "Email required"}, status=400)

        try:
            bot = get_bot()
            bot._ensure_crm_loaded()

            if not bot.analyzer:
                return JsonResponse({"error": "CRM not loaded"}, status=500)

            info = bot.analyzer.get_useful_info_for_bot(email)
            return JsonResponse(info)
        except Exception as e:
            logger.error(f"Customer lookup error: {e}")
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class BotConfigView(View):
    """Get/update bot configuration from admin dashboard."""

    def get(self, request, *args, **kwargs):
        """Return current bot configuration."""
        from customer_care.config.bot_config import config

        return JsonResponse({
            "persona": {
                "name": config.persona.name,
                "tone": config.persona.tone,
                "response_length": config.persona.response_length,
            },
            "features": config.features,
            "crm": {
                "sheet_id": config.crm.sheet_id,
                "refresh_interval": config.crm.refresh_interval,
                "ai_filter_enabled": config.crm.ai_filter_enabled,
            },
            "ai": {
                "provider": config.ai.provider,
                "model": config.ai.model,
                "temperature": config.ai.temperature,
            },
        })

    def post(self, request, *args, **kwargs):
        """Update bot configuration."""
        try:
            data = json.loads(request.body)

            from customer_care.config.bot_config import config

            # Update features
            if "features" in data:
                config.features.update(data["features"])

            # Update persona
            if "persona" in data:
                for key, value in data["persona"].items():
                    if hasattr(config.persona, key):
                        setattr(config.persona, key, value)

            # Update AI settings
            if "ai" in data:
                for key, value in data["ai"].items():
                    if hasattr(config.ai, key):
                        setattr(config.ai, key, value)

            return JsonResponse({"status": "ok", "message": "Configuration updated"})
        except Exception as e:
            logger.error(f"Config update error: {e}")
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class CRMInsightsView(View):
    """Get AI-analyzed CRM insights for the admin dashboard."""

    def get(self, request, *args, **kwargs):
        """Return AI insights from CRM data."""
        try:
            bot = get_bot()
            bot._ensure_crm_loaded()

            if not bot.analyzer:
                return JsonResponse({"error": "CRM not loaded"}, status=500)

            insights = bot.analyzer.analyze_all()

            # Filter by category if requested
            category = request.GET.get("category", None)
            if category:
                insights = [i for i in insights if i.category == category]

            # Filter by priority
            priority = request.GET.get("priority", None)
            if priority:
                insights = [i for i in insights if i.priority == priority]

            return JsonResponse({
                "insights": [
                    {
                        "category": i.category,
                        "title": i.title,
                        "description": i.description,
                        "confidence": i.confidence,
                        "priority": i.priority,
                        "action_required": i.action_required,
                        "data": i.data,
                    }
                    for i in insights
                ],
                "total": len(insights),
            })
        except Exception as e:
            logger.error(f"Insights error: {e}")
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class ProductsView(View):
    """Get product catalog for the admin dashboard."""

    def get(self, request, *args, **kwargs):
        """Return product catalog."""
        try:
            bot = get_bot()
            bot._ensure_crm_loaded()

            products = bot.parser.parse_products()

            # Filter by type
            product_type = request.GET.get("type", None)
            if product_type == "vatican":
                products = [p for p in products if p.is_vatican]
            elif product_type == "colosseum":
                products = [p for p in products if p.is_colosseum]
            elif product_type == "private":
                products = [p for p in products if p.is_private]

            return JsonResponse({
                "products": [
                    {
                        "id": p.product_id,
                        "title": p.title,
                        "summary": p.summary[:200] if p.summary else "",
                        "price_from": p.price_from,
                        "duration": p.duration_text,
                        "is_vatican": p.is_vatican,
                        "is_colosseum": p.is_colosseum,
                        "is_private": p.is_private,
                        "has_audio_guide": p.has_audio_guide,
                        "has_skip_the_line": p.has_skip_the_line,
                        "review_rating": p.review_rating,
                        "review_count": p.review_count,
                    }
                    for p in products
                ],
                "total": len(products),
            })
        except Exception as e:
            logger.error(f"Products error: {e}")
            return JsonResponse({"error": str(e)}, status=500)
