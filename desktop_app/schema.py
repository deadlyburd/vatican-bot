"""Canonical booking schema + sheet column mapping.

The whole point of the desktop app is that *any* Google Sheet layout can be
mapped onto these canonical fields, so the booking engine always consumes the
same shape regardless of what the source sheet's columns are actually named.

This module is pure (no network / browser), so it can be unit-tested offline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

# Canonical fields the booking engine needs.
CANONICAL_FIELDS = [
    "booking_id", "activity_date", "visitors",
    "customer_name", "customer_email", "product_title", "status",
    # Ticket type fields (optional — safe to leave unmapped for standard tickets)
    "ticket_type", "language",
]

# Default mapping = the existing CRM sheet's column names.
DEFAULT_COLUMN_MAP = {
    "booking_id": "bookingId",
    "activity_date": "activityDate",
    "visitors": "totalParticipants",
    "customer_name": "customerName",
    "customer_email": "customerEmail",
    "product_title": "productTitle",
    "status": "status",
    # ticket_type / language intentionally not mapped by default (standard tickets)
}

# Valid ticket_type values (case-insensitive matching applied on ingest)
TICKET_TYPE_STANDARD = "standard"
TICKET_TYPE_GUIDED   = "guided"
VALID_TICKET_TYPES   = {TICKET_TYPE_STANDARD, TICKET_TYPE_GUIDED}

DEFAULT_VATICAN_KEYWORDS = ["vatican", "sistine", "vaticani", "musei"]
DEFAULT_GUIDED_KEYWORDS  = ["guided", "tour guidato", "visite guidate", "visita guidata", "guided tour"]

DATE_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
    "%d-%m-%Y", "%m-%d-%Y", "%Y/%m/%d",
    "%d.%m.%Y", "%m.%d.%Y",
    "%d/%m/%y", "%m/%d/%y",
]


@dataclass
class BookingTarget:
    """One booking, normalized to the canonical shape."""
    booking_id: str
    activity_date: str          # YYYY-MM-DD
    visitors: int
    customer_name: str
    customer_email: str
    status: str
    product_title: str
    # ── Ticket type ─────────────────────────────────────────────────────────
    # "standard"  → MV-Biglietti (default, backwards-compatible)
    # "guided"    → MV-Visite-Guidate  (requires language)
    ticket_type: str = "standard"
    # Language code for guided tours: ENG, ITA, ESP, FRA, DEU, POR, …
    # Ignored (and left empty) for standard tickets.
    language: str = ""
    # ────────────────────────────────────────────────────────────────────────
    slot: Optional[object] = None   # filled by the slot finder at booking time
    source: Optional[dict] = None   # {"sheet_id": ..., "tab": ...} for write-back

    @property
    def is_guided(self) -> bool:
        return self.ticket_type.lower().strip() == "guided"

    @property
    def tag(self) -> str:
        """Vatican API search tag."""
        return "MV-Visite-Guidate" if self.is_guided else "MV-Biglietti"

    @property
    def date_dmy(self) -> str:
        """DD/MM/YYYY for the Vatican API."""
        try:
            return datetime.strptime(self.activity_date, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return self.activity_date


def parse_date(value, fmt: str = "auto") -> Optional[str]:
    """Normalize a date-like value to ISO 'YYYY-MM-DD'; None if unparseable."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")

    s = str(value).strip()
    if not s:
        return None

    fmts = [fmt] if (fmt and fmt != "auto") else DATE_FORMATS
    for f in fmts:
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# ── Header auto-detection (used by the GUI to suggest a mapping) ──────────────

FIELD_ALIASES = {
    "booking_id": ["bookingid", "booking id", "booking", "orderid", "order id",
                   "reservation", "reservation id", "confirmation code", "confirmation"],
    "activity_date": ["activitydate", "activity date", "date", "tour date",
                      "travel date", "visit date", "service date", "departure date"],
    "visitors": ["totalparticipants", "participants", "pax", "guests", "visitors",
                 "number of people", "people", "qty", "quantity", "adults"],
    "customer_name": ["customername", "customer name", "client name", "lead name",
                      "contact name", "full name", "name"],
    "customer_email": ["customeremail", "email", "client email", "contact email",
                       "e-mail", "email address"],
    "product_title": ["producttitle", "product title", "product", "activity",
                      "tour", "experience", "ticket type", "item", "service"],
    "status": ["status", "booking status", "state"],
    "ticket_type": ["tickettype", "ticket type", "type", "ticket kind",
                    "tour type", "product type"],
    "language": ["language", "lang", "tour language", "guide language",
                 "lingua", "sprache"],
}


def _normalize_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(h).lower())


def suggest_mapping(headers: List[str]) -> dict:
    """Guess the canonical->header mapping for a list of header names.

    Returns a dict keyed by canonical field, e.g.
        {"booking_id": "Booking ID", "activity_date": "Activity Date", ...}
    """
    norm_aliases = {
        field: [_normalize_header(a) for a in aliases]
        for field, aliases in FIELD_ALIASES.items()
    }
    out: dict = {}
    for h in headers:
        key = _normalize_header(h)
        if not key:
            continue
        for field in CANONICAL_FIELDS:
            if field in out:
                continue
            if key in norm_aliases[field]:
                out[field] = h
                break
    return out
