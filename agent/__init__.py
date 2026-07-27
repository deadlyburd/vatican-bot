"""
Vatican Bot Agent — Consolidated booking pipeline and customer care system.

Modules:
    config:   Central configuration from environment variables
    sheets:   Google Sheets read/write operations
    vatican_api: Vatican Museums API slot checking
    booker:   Browser automation booking (nodriver)
    notifier: Telegram admin notifications
    pipeline: End-to-end booking orchestrator
    customer_bot: Tourist-facing Telegram bot
    cli:      Command-line interface
"""

__version__ = "2.0.0"
