"""Schema-agnostic Google Sheets reader.

Reads any configured sheet, maps its columns onto the canonical schema, filters
to upcoming Vatican bookings, and returns normalized BookingTarget objects.

The live read_bookings() is a thin wrapper around the pure rows_to_targets()
so the mapping/filter logic is unit-testable offline.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime
from typing import List, Optional

from .config import AppConfig, SheetConfig
from .schema import BookingTarget, DEFAULT_COLUMN_MAP, parse_date

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_path(p: str) -> str:
    """Resolve a credential path, auto-discovering from common locations.

    If the configured value points somewhere that doesn't exist, fall back to
    searching common spots by filename so a non-technical user who dropped
    google_credentials.json in Downloads or ~/.vatican-sniper/ still works.
    """
    if not p:
        return p
    if os.path.exists(p):
        return p

    base = os.path.basename(p) if os.path.isabs(p) else p
    candidates = [
        base,                                                  # relative to cwd
        os.path.join(_APP_DIR, base),                          # app package dir
        os.path.join(os.path.expanduser("~"), ".vatican-sniper", base),
        os.path.join(os.path.expanduser("~"), "Downloads", base),
        os.path.join(os.path.expanduser("~"), "Downloads", "dist", base),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return p  # original (may not exist) so errors show what was configured


def _to_int(value, default: int = 2) -> int:
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return default


def _get_field(row: dict, field: str, column_map: dict) -> str:
    """Pull a canonical field from a row using the mapping (case-insensitive fallback)."""
    header = column_map.get(field)
    if header:
        if header in row:
            return row[header]
        target = str(header).strip().lower()
        for k, v in row.items():
            if k is not None and str(k).strip().lower() == target:
                return v
    return ""


def rows_to_targets(
    records: List[dict],
    cfg: SheetConfig,
    default_visitors: int = 2,
    today: Optional[date] = None,
    source: Optional[dict] = None,
) -> List[BookingTarget]:
    """Map raw sheet rows to normalized BookingTargets. Pure — no I/O."""
    cmap = {**DEFAULT_COLUMN_MAP, **(cfg.column_map or {})}
    keywords = [k.lower() for k in (cfg.vatican_keywords or [])]
    statuses = {s.upper() for s in (cfg.status_values or ["PENDING", "CONFIRMED"])}
    today = today or date.today()

    targets: List[BookingTarget] = []
    seen: set = set()

    for row in records:
        def get(field: str) -> str:
            return _get_field(row, field, cmap)

        title = str(get("product_title") or "")
        if keywords and not any(k in title.lower() for k in keywords):
            continue

        status = str(get("status") or "").upper()
        if status not in statuses:
            continue

        d = parse_date(get("activity_date"), cfg.date_format)
        if d is None:
            continue
        if datetime.strptime(d, "%Y-%m-%d").date() < today:
            continue

        booking_id = str(get("booking_id") or "").strip()
        if not booking_id or booking_id in seen:
            continue
        seen.add(booking_id)

        targets.append(BookingTarget(
            booking_id=booking_id,
            activity_date=d,
            visitors=_to_int(get("visitors"), default_visitors),
            customer_name=str(get("customer_name") or "").strip(),
            customer_email=str(get("customer_email") or "").strip(),
            status=status,
            product_title=title,
            source=source,
        ))

    targets.sort(key=lambda t: t.activity_date)
    return targets


def read_bookings(config: AppConfig) -> List[BookingTarget]:
    """Connect to Google Sheets and return upcoming, pending Vatican bookings."""
    import gspread
    from google.oauth2.service_account import Credentials

    creds_path = _resolve_path(config.google.service_account_file)
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    client = gspread.authorize(creds)

    all_targets: List[BookingTarget] = []
    for scfg in config.sheets:
        if not scfg.sheet_id:
            continue
        sheet = client.open_by_key(scfg.sheet_id)
        ws = sheet.worksheet(scfg.tab) if scfg.tab else sheet.sheet1
        records = ws.get_all_records()
        targets = rows_to_targets(
            records, scfg,
            default_visitors=config.booking.default_visitors,
            source={"sheet_id": scfg.sheet_id, "tab": scfg.tab},
        )
        all_targets.extend(targets)

    # dedupe across sheets by booking_id
    deduped: List[BookingTarget] = []
    seen: set = set()
    for t in all_targets:
        if t.booking_id in seen:
            continue
        seen.add(t.booking_id)
        deduped.append(t)
    deduped.sort(key=lambda t: t.activity_date)
    return deduped


# ── Connection helpers (used by the dashboard) ────────────────────────────────

def extract_sheet_id(url_or_id: str) -> str:
    """Pull a sheet ID out of a pasted URL, or pass through a bare ID."""
    s = (url_or_id or "").strip()
    if not s:
        return ""
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", s):
        return s
    return ""


def _authorize(service_account_file: str):
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_file(
        _resolve_path(service_account_file), scopes=SCOPES)
    return gspread.authorize(creds)


def list_tabs(sheet_id: str, service_account_file: str) -> List[str]:
    """Return the worksheet (tab) titles for a sheet. Raises on bad auth/access."""
    client = _authorize(service_account_file)
    sheet = client.open_by_key(sheet_id)
    return [ws.title for ws in sheet.worksheets()]


def read_headers(sheet_id: str, tab: str, service_account_file: str) -> List[str]:
    """Return the first row (header) of a worksheet as a list of strings."""
    client = _authorize(service_account_file)
    sheet = client.open_by_key(sheet_id)
    ws = sheet.worksheet(tab) if tab else sheet.sheet1
    rows = ws.get_values()
    if not rows:
        return []
    return [str(c).strip() for c in rows[0]]


def connect_sheet(url_or_id: str, service_account_file: str, tab: str = "") -> dict:
    """Open a sheet by URL/ID and return its ID, tabs, headers, and a suggested map.

    The GUI uses this for the "connect + auto-detect columns" flow.
    """
    from .schema import suggest_mapping

    sheet_id = extract_sheet_id(url_or_id)
    if not sheet_id:
        raise ValueError("Could not find a Google Sheet ID in that input")

    tabs = list_tabs(sheet_id, service_account_file)
    if tab and tab not in tabs:
        tab = tabs[0] if tabs else ""
    elif not tab and tabs:
        tab = tabs[0]

    headers = read_headers(sheet_id, tab, service_account_file)
    suggested = suggest_mapping(headers)

    return {
        "sheet_id": sheet_id,
        "tab": tab,
        "tabs": tabs,
        "headers": headers,
        "suggested_mapping": suggested,
    }


def write_booking_result(
    config: AppConfig,
    source: dict,
    booking_id: str,
    status: str,
    payment_link: str = "",
    confirmation: str = "",
) -> bool:
    """Write a booking's result back to its source sheet (status/payment/confirmation).

    Finds the row by booking_id and updates the configured write columns.
    """
    if not source or not source.get("sheet_id"):
        return False

    scfg = next((s for s in config.sheets if s.sheet_id == source.get("sheet_id")), None)
    if not scfg:
        return False

    cmap = {**DEFAULT_COLUMN_MAP, **(scfg.column_map or {})}
    id_header = cmap.get("booking_id", "bookingId")
    status_header = scfg.write_status_column or cmap.get("status", "status")
    payment_header = scfg.write_payment_column or ""
    confirm_header = scfg.write_confirmation_column or ""

    client = _authorize(config.google.service_account_file)
    sheet = client.open_by_key(source["sheet_id"])
    ws = sheet.worksheet(source.get("tab") or scfg.tab) if (source.get("tab") or scfg.tab) else sheet.sheet1

    values = ws.get_all_values()
    if not values:
        return False
    headers = [str(h).strip() for h in values[0]]

    def col_index(header: str) -> Optional[int]:
        if not header:
            return None
        try:
            return headers.index(header) + 1  # 1-indexed
        except ValueError:
            return None

    id_col = col_index(id_header)
    status_col = col_index(status_header)
    if id_col is None or status_col is None:
        return False

    target_row = None
    for r, row in enumerate(values[1:], start=2):
        cell = row[id_col - 1] if len(row) >= id_col else ""
        if str(cell).strip() == str(booking_id).strip():
            target_row = r
            break
    if target_row is None:
        return False

    updates = [(target_row, status_col, status)]
    payment_col = col_index(payment_header)
    if payment_col and payment_link:
        updates.append((target_row, payment_col, payment_link))
    confirm_col = col_index(confirm_header)
    if confirm_col and confirmation:
        updates.append((target_row, confirm_col, confirmation))

    for row, c, v in updates:
        ws.update_cell(row, c, v)
    return True
