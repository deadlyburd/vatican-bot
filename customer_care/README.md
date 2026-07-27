# 🏛️ Roma Assistant - Customer Care Bot

A full-featured Telegram bot for tourists visiting Rome and Italy.

## Features

- **Booking Management**: Look up, modify, cancel bookings
- **AI-Powered Responses**: Natural conversation using Claude
- **CRM Integration**: Reads from Google Sheets for customer data
- **Multi-Language**: Supports EN, IT, ES, FR, DE, PT, ZH, JA
- **Rome Tourist Info**: Vatican dress code, transport, food tips
- **Support Ticket System**: Creates tickets, notifies admins
- **Email Integration**: Sends confirmations, receipts, promotions
- **Admin Dashboard**: Configure bot behavior, view analytics

## Quick Run

```bash
# Standalone (polling mode)
python -m customer-care.bot

# Integrated with Django
python manage.py run_customer_care_bot

# With webhook
python manage.py run_customer_care_bot --webhook
```

## Configuration

Set environment variables or edit `customer-care/config/bot_config.py`:

- `TELEGRAM_BOT_TOKEN` - Your bot token from @BotFather
- `GOOGLE_SHEET_ID` - CRM spreadsheet ID
- `GOOGLE_SERVICE_ACCOUNT_FILE` - Path to service account JSON
- `ADMIN_TELEGRAM_IDS` - Comma-separated admin Telegram IDs
- `TELEGRAM_WEBHOOK_URL` - Webhook URL (if using webhook mode)
- `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` - For email sending

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Main menu |
| `/bookings` | Look up your bookings |
| `/support` | Get help / create support ticket |
| `/info` | Rome tourist information |
| `/language` | Change language |
| `/help` | Show help |

## Architecture

```
customer-care/
├── bot/
│   ├── tourist_care_bot.py    # Main bot logic
│   ├── django_bot.py          # Django integration
│   └── __main__.py            # Entry point
├── ai/                         # AI response generation
├── channels/
│   ├── email_sender.py        # Email sending
│   └── telegram_webhook.py    # Webhook handler
├── config/
│   └── bot_config.py          # Central configuration
└── urls.py                    # API routes
```
