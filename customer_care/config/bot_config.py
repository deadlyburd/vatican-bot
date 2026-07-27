"""
Customer Care Bot Configuration
================================
Central configuration for the tourist customer care Telegram bot.
Customized for tourists visiting Italy and Rome.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BotPersona:
    """The bot's personality and behavior settings."""
    name: str = "Roma Assistant"
    tone: str = "friendly, helpful, professional"
    emoji_style: str = "warm"  # warm, minimal, none
    response_length: str = "concise"  # concise, detailed, adaptive
    proactive_suggestions: bool = True
    max_message_length: int = 4000


@dataclass
class TouristContext:
    """Context about the tourist for personalized responses."""
    # What the bot knows about the tourist
    known_attractions: List[str] = field(default_factory=lambda: [
        "Vatican Museums", "Sistine Chapel", "Colosseum",
        "Trevi Fountain", "Pantheon", "Spanish Steps",
        "St. Peter's Basilica", "Villa Borghese", "Roman Forum",
        "Castel Sant'Angelo", "Piazza Navona", "Trastevere"
    ])

    # Common tourist questions and their answers
    faq_topics: List[str] = field(default_factory=lambda: [
        "ticket_booking", "refund_policy", "cancellation",
        "meeting_point", "what_to_bring", "dress_code",
        "audio_guide", "group_booking", "private_tour",
        "rome_transport", "best_time_to_visit", "nearby_restaurants",
        "weather", "language", "payment_methods", "accessibility"
    ])

    # Rome-specific info the bot should know
    rome_facts: Dict[str, str] = field(default_factory=lambda: {
        "vatican_dress_code": "Shoulders and knees must be covered. No shorts or sleeveless tops.",
        "vatican_best_time": "Early morning (8:00-9:00) or late afternoon (after 15:00) for fewer crowds.",
        "rome_tap_water": "Rome's tap water is safe to drink. Look for 'nasoni' (public fountains) for free fresh water.",
        "rome_transport": "Metro runs 5:30-23:30 (Fri/Sat until 1:30). Day pass €7, 2-day €12.50.",
        "tipping": "Tipping is not mandatory in Italy. A small tip (€1-2) is appreciated for good service.",
        "siesta": "Many shops close 13:00-16:00 for siesta. Vatican Museums stay open.",
        "emergency_number": "112 (European emergency number)",
        "tourist_police": "113 (Police), 118 (Medical emergency)",
    })


@dataclass
class CRMIntegration:
    """How the bot connects to CRM data."""
    sheet_id: str = os.getenv("GOOGLE_SHEET_ID", "1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg")
    service_account_file: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "/app/google_credentials.json")

    # Which worksheets to use
    bookings_sheet: str = "Bookings"
    activity_lines_sheet: str = "Activity_Lines"
    passengers_sheet: str = "Passengers"
    products_sheet: str = "Products"

    # How often to refresh CRM data (seconds)
    refresh_interval: int = 300  # 5 minutes

    # AI filtering settings
    ai_filter_enabled: bool = True
    min_confidence_score: float = 0.7


@dataclass
class AISettings:
    """AI/LLM settings for the bot."""
    provider: str = "claude"  # claude, openai, local
    model: str = "claude-sonnet-4-6"
    api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # System prompt for the tourist care bot
    system_prompt: str = """You are Roma Assistant, a helpful customer care bot for tourists visiting Rome and Italy.

Your role:
- Help tourists with ticket bookings, cancellations, and modifications
- Answer questions about Vatican Museums, Colosseum, and other Rome attractions
- Provide personalized recommendations based on their booking history
- Handle complaints and issues professionally
- Suggest upgrades and additional experiences

Guidelines:
- Be warm, friendly, and patient — tourists may be stressed or confused
- Always confirm booking details before making changes
- Provide clear, step-by-step instructions
- If you don't know something, say so and offer to connect to a human
- Use the tourist's name when you know it
- Be proactive: suggest relevant info (weather, transport, nearby restaurants)
- Keep responses concise but complete
- Use emojis sparingly for a professional yet warm tone

You have access to:
- The tourist's booking history from our CRM
- Product catalog with descriptions and prices
- Rome tourism information (transport, weather, attractions)
- Company policies (refunds, cancellations, modifications)

When handling bookings:
1. Always verify the booking ID or confirmation code
2. Check the activity date and time
3. Confirm the number of participants
4. Explain any fees or policies before proceeding
5. Get explicit confirmation before making changes

Languages: Support English, Italian, Spanish, French, German, Portuguese, Chinese, Japanese.
Default to the customer's language based on their CRM profile."""

    # Response generation settings
    max_tokens: int = 1024
    temperature: float = 0.7

    # Intent classification
    intent_confidence_threshold: float = 0.8


@dataclass
class ChannelSettings:
    """Settings for different communication channels."""
    # Telegram
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_webhook_url: str = os.getenv("TELEGRAM_WEBHOOK_URL", "")

    # Email (for follow-ups)
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    email_from: str = os.getenv("EMAIL_FROM", "your-email@example.com")

    # WhatsApp (future)
    whatsapp_enabled: bool = False
    whatsapp_api_key: str = os.getenv("WHATSAPP_API_KEY", "")


@dataclass
class BotConfig:
    """Main bot configuration."""
    persona: BotPersona = field(default_factory=BotPersona)
    tourist_context: TouristContext = field(default_factory=TouristContext)
    crm: CRMIntegration = field(default_factory=CRMIntegration)
    ai: AISettings = field(default_factory=AISettings)
    channels: ChannelSettings = field(default_factory=ChannelSettings)

    # Admin settings
    admin_telegram_ids: List[str] = field(default_factory=lambda:
        os.getenv("ADMIN_TELEGRAM_IDS", "").split(","))

    # Feature flags
    features: Dict[str, bool] = field(default_factory=lambda: {
        "booking_lookup": True,
        "booking_modification": True,
        "cancellation": True,
        "refund_request": True,
        "product_recommendations": True,
        "rome_guide": True,
        "multi_language": True,
        "human_handoff": True,
        "email_followup": True,
        "satisfaction_survey": True,
        "proactive_notifications": True,
    })


# Global config instance
config = BotConfig()
