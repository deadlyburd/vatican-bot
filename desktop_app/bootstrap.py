"""First-run bootstrap.

Ensures a config.json exists and has the browser path + warm source profile
auto-detected, so an operator can launch the app and only needs to paste their
sheet URL + credentials.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from .config import AppConfig, DEFAULT_CONFIG_PATH, _app_data_dir, default_config, load_config, save_config
from .runner import default_source_profile, detect_browser

log = logging.getLogger("sniper")


def setup_logging() -> None:
    """Configure logging to stderr + a rotating file in the user data dir."""
    root = logging.getLogger()
    if root.handlers:
        return
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    root.setLevel(logging.INFO)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    try:
        log_dir = _app_data_dir()
        os.makedirs(log_dir, exist_ok=True)
        fh = RotatingFileHandler(
            os.path.join(log_dir, "vatican-sniper.log"),
            maxBytes=1_000_000, backupCount=3,
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:  # noqa: BLE001
        pass


def _auto_fill(cfg: AppConfig) -> bool:
    """Fill empty settings from auto-detection. Returns True if changed."""
    changed = False
    if not cfg.browser.path:
        b = detect_browser()
        if b:
            cfg.browser.path = b
            changed = True
    if not cfg.browser.source_profile:
        s = default_source_profile()
        if s:
            cfg.browser.source_profile = s
            changed = True
    if not cfg.telemetry.machine_name:
        from .telemetry import default_machine_name
        cfg.telemetry.machine_name = default_machine_name()
        changed = True
    return changed


def ensure_config(path: str | None = None) -> AppConfig:
    """Load config, creating + auto-detecting on first run. Returns the config."""
    from .telemetry import ensure_machine_id

    p = path or os.getenv("VATICAN_CONFIG") or DEFAULT_CONFIG_PATH
    if not os.path.exists(p):
        cfg = default_config()
        _auto_fill(cfg)
        ensure_machine_id(cfg)
        save_config(cfg, p)
        log.info(f"First run — created config at {p}")
        return cfg

    cfg = load_config(p)
    changed = _auto_fill(cfg)
    if not cfg.machine_id:
        ensure_machine_id(cfg)
        changed = True
    if changed:
        save_config(cfg, p)
        log.info(f"Auto-detected settings — updated {p}")
    return cfg
