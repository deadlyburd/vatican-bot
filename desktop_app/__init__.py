"""Desktop sniper app — config, schema-agnostic sheet reader, proxy pool."""
from .config import (
    AppConfig, BrowserConfig, BookingConfig, GoogleConfig, ProxyConfig,
    SheetConfig, TelemetryConfig, default_config, load_config, save_config,
)
from .schema import (
    BookingTarget, CANONICAL_FIELDS, DEFAULT_COLUMN_MAP,
    DEFAULT_VATICAN_KEYWORDS, parse_date, suggest_mapping,
)
from .proxies import Proxy, ProxyPool
from .sheets import (
    connect_sheet, extract_sheet_id, list_tabs, read_bookings, read_headers,
    rows_to_targets,
)
from .providers import (
    BookingProvider, ProviderRegistry, Slot, VaticanProvider, default_registry,
)
from .runner import (
    build_chrome_cmd, clean_profile_locks, detect_browser, run_booking,
    seed_profile,
)
from .orchestrator import Orchestrator, PreparedBooking
from .bootstrap import ensure_config
from .notify import build_command, notify
from .telemetry import (
    ensure_machine_id, heartbeat_loop, machine_info, send_alert, send_telegram,
)
from .watcher import WatchTarget, Watcher, find_time_match, normalize_time

__version__ = "0.7.0"

__all__ = [
    "AppConfig", "BrowserConfig", "BookingConfig", "GoogleConfig",
    "ProxyConfig", "SheetConfig", "TelemetryConfig",
    "default_config", "load_config", "save_config",
    "BookingTarget", "CANONICAL_FIELDS", "DEFAULT_COLUMN_MAP",
    "DEFAULT_VATICAN_KEYWORDS", "parse_date", "suggest_mapping",
    "Proxy", "ProxyPool", "read_bookings", "rows_to_targets",
    "connect_sheet", "extract_sheet_id", "list_tabs", "read_headers",
    "BookingProvider", "ProviderRegistry", "Slot", "VaticanProvider",
    "default_registry",
    "build_chrome_cmd", "clean_profile_locks", "detect_browser",
    "run_booking", "seed_profile",
    "Orchestrator", "PreparedBooking",
    "ensure_config",
    "notify", "build_command",
    "ensure_machine_id", "heartbeat_loop", "machine_info",
    "send_alert", "send_telegram",
    "WatchTarget", "Watcher", "find_time_match", "normalize_time",
    "__version__",
]
