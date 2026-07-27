"""
Central configuration for the Vatican Bot agent system.

All settings are loaded from environment variables with sensible defaults.
Import `config` from this module — it's a validated singleton.
"""

import os
import sys
from dataclasses import dataclass, field
from typing import List


# ── Validation ──────────────────────────────────────────────────────────────

class ConfigError(Exception):
    """Raised when required configuration is missing."""


def _require(name: str, value: str | None) -> str:
    """Return value or raise ConfigError with a helpful message."""
    if not value:
        raise ConfigError(
            f"{name} is required. Set it in your .env file.\n"
            f"  export {name}=<value>"
        )
    return value


def _env(name: str, default: str = "") -> str:
    """Get an environment variable."""
    return os.getenv(name, default)


# ── Dataclass ───────────────────────────────────────────────────────────────

@dataclass
class Config:
    """Central configuration for the agent system."""

    # ── Google Sheets ───────────────────────────────────────────────────
    google_sheet_id: str = field(
        default_factory=lambda: _require("GOOGLE_SHEET_ID", _env("GOOGLE_SHEET_ID"))
    )
    google_service_account_file: str = field(
        default_factory=lambda: _env("GOOGLE_SERVICE_ACCOUNT_FILE", "/app/google_credentials.json")
    )
    google_api_key: str = field(default_factory=lambda: _env("GOOGLE_API_KEY", ""))

    # ── Sheet tab names ─────────────────────────────────────────────────
    master_sheet: str = "📊 Master"
    activity_lines_sheet: str = "Activity_Lines"
    bookings_sheet: str = "Bookings"
    passengers_sheet: str = "Passengers"

    # ── Telegram ────────────────────────────────────────────────────────
    telegram_bot_token: str = field(
        default_factory=lambda: _require("TELEGRAM_BOT_TOKEN", _env("TELEGRAM_BOT_TOKEN"))
    )
    admin_telegram_ids: List[str] = field(
        default_factory=lambda: [
            a.strip() for a in _env("ADMIN_TELEGRAM_IDS", "").split(",") if a.strip()
        ]
    )

    # ── Vatican API ─────────────────────────────────────────────────────
    vatican_base_url: str = "https://tickets.museivaticani.va"
    vatican_search_endpoint: str = "/api/search/resultPerTag"
    vatican_timeavail_endpoint: str = "/api/visit/timeavail"
    vatican_excluded_keywords: List[str] = field(default_factory=lambda: [
        "pellegrinaggi", "lunch", "pranzo", "gruppi",
        "specola", "palazzo", "didattiche", "scuole",
        "pellegrinaggio",
    ])

    # ── Proxy (Oxylabs ISP) ─────────────────────────────────────────────
    oxylabs_username: str = field(default_factory=lambda: _env("OXYLABS_USERNAME", ""))
    oxylabs_password: str = field(default_factory=lambda: _env("OXYLABS_PASSWORD", ""))
    oxylabs_host: str = field(default_factory=lambda: _env("OXYLABS_HOST", "isp.oxylabs.io"))
    oxylabs_ports: List[int] = field(default_factory=lambda: list(range(8001, 8014)))

    @property
    def proxy_url(self) -> str | None:
        """Return a proxy URL or None if not configured."""
        if self.oxylabs_username and self.oxylabs_password:
            import random
            port = random.choice(self.oxylabs_ports)
            return (
                f"http://{self.oxylabs_username}:{self.oxylabs_password}"
                f"@{self.oxylabs_host}:{port}"
            )
        return None

    # ── Booking ─────────────────────────────────────────────────────────
    buyer_default_surname: str = field(default_factory=lambda: _env("BUYER_SURNAME", ""))
    buyer_default_name: str = field(default_factory=lambda: _env("BUYER_NAME", ""))
    buyer_default_email: str = field(default_factory=lambda: _env("BUYER_EMAIL", ""))
    buyer_default_phone: str = field(default_factory=lambda: _env("BUYER_PHONE", ""))
    buyer_default_city: str = field(default_factory=lambda: _env("BUYER_CITY", "Roma"))
    booking_max_retries: int = 3
    booking_timeout_seconds: int = 300

    # ── Pipeline ────────────────────────────────────────────────────────
    pipeline_interval_seconds: int = 300  # 5 minutes
    pipeline_max_bookings_per_cycle: int = 5
    pipeline_cooldown_seconds: int = 5

    # ── Customer Bot ────────────────────────────────────────────────────
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY", ""))
    bot_name: str = "Roma Assistant"
    bot_language: str = field(default_factory=lambda: _env("BOT_LANGUAGE", "en"))

    # ── Server ──────────────────────────────────────────────────────────
    server_base_url: str = field(default_factory=lambda: _env("SERVER_BASE_URL", "http://localhost:8000"))
    debug: bool = field(default_factory=lambda: _env("DEBUG", "False").lower() in ("true", "1", "yes"))

    def validate(self) -> List[str]:
        """Check configuration and return list of warnings (empty = all good)."""
        warnings = []
        if not self.admin_telegram_ids:
            warnings.append("ADMIN_TELEGRAM_IDS is empty — no admins will receive notifications")
        if not self.oxylabs_username:
            warnings.append("OXYLABS_USERNAME not set — proxy disabled (may fail for non-Italian IPs)")
        if not self.buyer_default_email:
            warnings.append("BUYER_EMAIL not set — using placeholder email for bookings")
        return warnings

    def summary(self) -> str:
        """Return a human-readable configuration summary (safe — no secrets)."""
        return (
            f"Config:\n"
            f"  Sheet ID:     {self.google_sheet_id[:20]}...\n"
            f"  Sheet tabs:   {self.master_sheet}, {self.activity_lines_sheet}, "
            f"{self.bookings_sheet}, {self.passengers_sheet}\n"
            f"  Telegram:     token={'✓' if self.telegram_bot_token else '✗'}, "
            f"admins={len(self.admin_telegram_ids)}\n"
            f"  Vatican API:  {self.vatican_base_url}\n"
            f"  Proxy:        {'configured' if self.oxylabs_username else 'DISABLED'}\n"
            f"  Buyer:        {self.buyer_default_email or 'NOT SET'}\n"
            f"  Pipeline:     every {self.pipeline_interval_seconds}s, "
            f"max {self.pipeline_max_bookings_per_cycle} per cycle\n"
            f"  Claude AI:    {'configured' if self.anthropic_api_key else 'DISABLED'}\n"
            f"  Debug:        {self.debug}"
        )


# ── Singleton ────────────────────────────────────────────────────────────────

_config: Config | None = None


def get_config() -> Config:
    """Return the global Config singleton, creating it on first call."""
    global _config
    if _config is None:
        try:
            _config = Config()
            warnings = _config.validate()
            if warnings:
                for w in warnings:
                    print(f"[config] ⚠️  {w}", file=sys.stderr)
        except ConfigError as e:
            print(f"[config] ❌ {e}", file=sys.stderr)
            sys.exit(1)
    return _config


# Convenience: module-level access
config = get_config()
