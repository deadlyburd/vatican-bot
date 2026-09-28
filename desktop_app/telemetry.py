"""Telemetry: machine identity + Telegram notifications.

Gives the operator a lightweight way to know WHICH machines are running and
WHEN one errors, without a central server — each install sends Telegram
messages directly via the Bot API.
"""
from __future__ import annotations

import logging
import platform
import socket
import threading
import time
import uuid

from .config import AppConfig

log = logging.getLogger("sniper")


def machine_info() -> str:
    return f"{socket.gethostname()} ({platform.system()} {platform.machine()})"


def default_machine_name() -> str:
    return socket.gethostname()


def ensure_machine_id(cfg: AppConfig) -> str:
    """Set a stable install id if one isn't set yet (does not save)."""
    if not cfg.machine_id:
        cfg.machine_id = uuid.uuid4().hex[:12]
    return cfg.machine_id


def _enabled(cfg: AppConfig) -> bool:
    return bool(cfg.telemetry.telegram_bot_token and cfg.telemetry.telegram_chat_id)


def send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    """POST a message to Telegram. Never raises."""
    import requests
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:  # noqa: BLE001
        log.warning(f"Telegram send failed: {e}")
        return False


def send_alert(cfg: AppConfig, text: str) -> bool:
    """Send a Telegram alert prefixed with the machine name + install id."""
    if not _enabled(cfg):
        return False
    name = cfg.telemetry.machine_name or default_machine_name()
    prefix = f"🤖 [{name}] ({cfg.machine_id or '?'})"
    return send_telegram(cfg.telemetry.telegram_bot_token,
                         cfg.telemetry.telegram_chat_id, f"{prefix}\n{text}")


def heartbeat_loop(cfg: AppConfig) -> None:
    """Background thread: send an 'alive' message every N hours (0 = off)."""
    hours = cfg.telemetry.heartbeat_hours
    if hours <= 0 or not _enabled(cfg):
        return

    def _run():
        while True:
            time.sleep(hours * 3600)
            send_alert(cfg, f"💓 alive — {machine_info()}")

    threading.Thread(target=_run, daemon=True).start()
