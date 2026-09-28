"""Configuration model for the desktop sniper app.

Everything the app needs to run is stored in a single config.json:
  - one or more Google Sheets with a column mapping (any sheet layout works)
  - a proxy pool
  - booking + browser preferences

This module is pure (no network / browser), so it can be unit-tested offline.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Dict, List

from .schema import DEFAULT_COLUMN_MAP, DEFAULT_VATICAN_KEYWORDS

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _app_data_dir() -> str:
    """Writable dir for config/credentials (home dir when frozen/PyInstaller)."""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.expanduser("~"), ".vatican-sniper")
    return APP_DIR


DEFAULT_CONFIG_PATH = os.path.join(_app_data_dir(), "config.json")


def _config_path(path: str | None = None) -> str:
    return path or os.getenv("VATICAN_CONFIG") or DEFAULT_CONFIG_PATH


@dataclass
class GoogleConfig:
    service_account_file: str = "google_credentials.json"

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        return cls(service_account_file=d.get("service_account_file", "google_credentials.json"))


@dataclass
class SheetConfig:
    name: str = ""
    sheet_id: str = ""
    tab: str = "Activity_Lines"
    date_format: str = "auto"                              # "auto" or strptime fmt e.g. "%d/%m/%Y"
    column_map: Dict[str, str] = field(default_factory=dict)  # canonical field -> sheet header
    vatican_keywords: List[str] = field(default_factory=lambda: list(DEFAULT_VATICAN_KEYWORDS))
    status_values: List[str] = field(default_factory=lambda: ["PENDING", "CONFIRMED"])
    # write-back column headers (empty = use column_map["status"])
    write_status_column: str = ""
    write_payment_column: str = ""
    write_confirmation_column: str = ""

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        return cls(
            name=d.get("name", ""),
            sheet_id=d.get("sheet_id", ""),
            tab=d.get("tab", "Activity_Lines"),
            date_format=d.get("date_format", "auto"),
            column_map=dict(d.get("column_map") or {}),
            vatican_keywords=list(d.get("vatican_keywords") or DEFAULT_VATICAN_KEYWORDS),
            status_values=list(d.get("status_values") or ["PENDING", "CONFIRMED"]),
            write_status_column=d.get("write_status_column", ""),
            write_payment_column=d.get("write_payment_column", ""),
            write_confirmation_column=d.get("write_confirmation_column", ""),
        )


@dataclass
class ProxyConfig:
    host: str = ""
    port: int = 8080
    username: str = ""
    password: str = ""
    enabled: bool = True

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        return cls(
            host=d.get("host", ""),
            port=int(d.get("port", 8080)),
            username=d.get("username", ""),
            password=d.get("password", ""),
            enabled=bool(d.get("enabled", True)),
        )


@dataclass
class BookingConfig:
    max_concurrent: int = 4
    stagger_same_date_seconds: int = 120
    default_visitors: int = 2

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        return cls(
            max_concurrent=int(d.get("max_concurrent", 4)),
            stagger_same_date_seconds=int(d.get("stagger_same_date_seconds", 120)),
            default_visitors=int(d.get("default_visitors", 2)),
        )


@dataclass
class BrowserConfig:
    path: str = ""               # empty = auto-detect Brave/Chrome
    source_profile: str = ""     # real profile's Default dir to seed warm cookies from

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        return cls(
            path=d.get("path", ""),
            source_profile=d.get("source_profile", ""),
        )


@dataclass
class TelemetryConfig:
    machine_name: str = ""           # friendly name (default = hostname)
    telegram_bot_token: str = ""     # Telegram bot token (BotFather)
    telegram_chat_id: str = ""       # your Telegram chat/user id to alert
    heartbeat_hours: float = 0.0     # 0 = disabled; send "alive" every N hours
    notify_startup: bool = True
    notify_holds: bool = True
    notify_failures: bool = True

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        return cls(
            machine_name=d.get("machine_name", ""),
            telegram_bot_token=d.get("telegram_bot_token", ""),
            telegram_chat_id=d.get("telegram_chat_id", ""),
            heartbeat_hours=float(d.get("heartbeat_hours", 0.0)),
            notify_startup=bool(d.get("notify_startup", True)),
            notify_holds=bool(d.get("notify_holds", True)),
            notify_failures=bool(d.get("notify_failures", True)),
        )


@dataclass
class AppConfig:
    version: int = 1
    machine_id: str = ""               # auto-generated persistent install id
    google: GoogleConfig = field(default_factory=GoogleConfig)
    sheets: List[SheetConfig] = field(default_factory=list)
    proxies: List[ProxyConfig] = field(default_factory=list)
    booking: BookingConfig = field(default_factory=BookingConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        return cls(
            version=int(d.get("version", 1)),
            machine_id=d.get("machine_id", ""),
            google=GoogleConfig.from_dict(d.get("google")),
            sheets=[SheetConfig.from_dict(s) for s in (d.get("sheets") or [])],
            proxies=[ProxyConfig.from_dict(p) for p in (d.get("proxies") or [])],
            booking=BookingConfig.from_dict(d.get("booking")),
            browser=BrowserConfig.from_dict(d.get("browser")),
            telemetry=TelemetryConfig.from_dict(d.get("telemetry")),
        )

    def to_dict(self) -> dict:
        return asdict(self)


def default_config() -> AppConfig:
    """A ready-to-run config seeded with the existing CRM sheet + default mapping."""
    cfg = AppConfig()
    cfg.sheets = [SheetConfig(
        name="Main CRM",
        sheet_id=os.getenv("GOOGLE_SHEET_ID", "1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg"),
        tab="Activity_Lines",
        column_map=dict(DEFAULT_COLUMN_MAP),
    )]
    return cfg


def load_config(path: str | None = None) -> AppConfig:
    p = _config_path(path)
    if not os.path.exists(p):
        return default_config()
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return AppConfig.from_dict(data)


def save_config(cfg: AppConfig, path: str | None = None) -> str:
    p = _config_path(path)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg.to_dict(), f, indent=2, ensure_ascii=False)
    return p
