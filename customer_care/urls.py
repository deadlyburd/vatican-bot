"""
Customer Care Bot URL Configuration
=====================================
API endpoints for customer care: Telegram, WhatsApp, Email, Dashboard.
"""

from django.urls import path
from customer_care.bot.django_bot import (
    TelegramWebhookView,
    BotStatusView,
    CustomerLookupView,
    BotConfigView,
    CRMInsightsView,
    ProductsView,
)
from customer_care.channels.whatsapp_webhook import WhatsAppWebhookView, WhatsAppSendView

app_name = "customer_care"

urlpatterns = [
    # Telegram webhook
    path("webhook/", TelegramWebhookView.as_view(), name="telegram-webhook"),

    # WhatsApp webhook & send
    path("whatsapp/webhook/", WhatsAppWebhookView.as_view(), name="whatsapp-webhook"),
    path("whatsapp/send/", WhatsAppSendView.as_view(), name="whatsapp-send"),

    # Admin dashboard API
    path("api/status/", BotStatusView.as_view(), name="bot-status"),
    path("api/config/", BotConfigView.as_view(), name="bot-config"),
    path("api/insights/", CRMInsightsView.as_view(), name="crm-insights"),
    path("api/customer/", CustomerLookupView.as_view(), name="customer-lookup"),
    path("api/products/", ProductsView.as_view(), name="products"),
]
