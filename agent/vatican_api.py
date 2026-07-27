"""
Vatican Museums API — slot checking via search + timeavail endpoints.

No browser needed. Uses plain HTTP requests with optional proxy support.
This is the "eyes" of the agent — find available slots before booking.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import requests

from agent.config import config

logger = logging.getLogger(__name__)

VATICAN_BASE = "https://tickets.museivaticani.va"
HEADERS = {
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36"
    ),
    "Referer": f"{VATICAN_BASE}/",
    "Origin": VATICAN_BASE,
}


# ── Data Models ─────────────────────────────────────────────────────────────

@dataclass
class Slot:
    """An available time slot for a Vatican Museums ticket."""
    date: str           # DD/MM/YYYY
    time: str           # HH:MM
    slot_id: str        # Used for booking
    ticket_id: str      # The ticket type ID
    ticket_name: str    # Human-readable ticket name
    visitors: int       # Number of visitors this slot was checked for
    price: float = 0.0
    residual: int = 0   # Remaining tickets

    def __str__(self):
        return f"{self.date} {self.time} — {self.ticket_name} ({self.residual} left, €{self.price})"


# ── Slot Finder ─────────────────────────────────────────────────────────────

class SlotFinder:
    """Check Vatican API for available ticket slots."""

    def __init__(self):
        self._cache: Dict[str, tuple[float, list[Slot]]] = {}
        self._cache_ttl = 60  # seconds

    # ── Public API ──────────────────────────────────────────────────────

    def find_slots(
        self,
        target_date: str,
        visitors: int = 2,
        use_cache: bool = True,
    ) -> List[Slot]:
        """
        Find available slots for a given date and visitor count.

        Args:
            target_date: Date in DD/MM/YYYY format
            visitors: Number of visitors (1-20)
            use_cache: Whether to use cached results (60s TTL)

        Returns:
            List of available Slot objects, sorted by time (earliest first).
            Empty list if no slots available or API error.
        """
        # Normalize date format
        date_str = self._normalize_date(target_date)

        # Check cache
        cache_key = f"{date_str}:{visitors}"
        if use_cache and cache_key in self._cache:
            ts, cached = self._cache[cache_key]
            if time.time() - ts < self._cache_ttl:
                logger.debug("Cache hit: %s", cache_key)
                return cached

        # Step 1: Search for ticket IDs
        ticket = self._search_ticket(date_str, visitors)
        if not ticket:
            logger.info("No Vatican ticket found for %s (%d visitors)", date_str, visitors)
            return []

        # Step 2: Get available time slots
        slots = self._get_time_slots(date_str, visitors, ticket)

        # Cache
        self._cache[cache_key] = (time.time(), slots)
        logger.info(
            "Found %d slots for %s (%d visitors)",
            len(slots), date_str, visitors,
        )
        return slots

    def find_next_available(
        self,
        start_date: str | None = None,
        max_days: int = 60,
        visitors: int = 2,
    ) -> Optional[Slot]:
        """
        Scan forward from start_date looking for the first available slot.

        Args:
            start_date: DD/MM/YYYY, defaults to today
            max_days: Maximum days to scan
            visitors: Number of visitors

        Returns:
            First available Slot, or None if nothing found in range.
        """
        from datetime import date, timedelta

        if start_date:
            d = date.today()
            # Parse start_date
            parts = start_date.split("/")
            d = date(int(parts[2]), int(parts[1]), int(parts[0]))
        else:
            d = date.today() + timedelta(days=1)

        for i in range(max_days):
            check_date = (d + timedelta(days=i)).strftime("%d/%m/%Y")
            slots = self.find_slots(check_date, visitors, use_cache=False)
            if slots:
                logger.info("First available: %s", slots[0])
                return slots[0]
            time.sleep(1)  # Rate limit between API calls

        logger.info("No slots found in next %d days from %s", max_days, start_date or "today")
        return None

    # ── API Calls ───────────────────────────────────────────────────────

    def _search_ticket(self, date_str: str, visitors: int) -> Optional[dict]:
        """Call the Vatican search API and return the matching ticket dict."""
        session = self._make_session()
        try:
            resp = session.get(
                f"{VATICAN_BASE}/api/search/resultPerTag",
                params={
                    "lang": "it",
                    "visitorNum": str(visitors),
                    "visitDate": date_str,
                    "area": "1",
                    "who": "",
                    "page": "0",
                    "tag": "MV-Biglietti",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning("Search API returned %d", resp.status_code)
                return None

            data = resp.json()
            visits = data.get("visits", [])

            for visit in visits:
                name = (visit.get("name") or "").lower()
                # Match standard entry tickets
                if "musei vaticani" not in name:
                    continue
                if "ingresso" not in name and "biglietti" not in name:
                    continue
                # Exclude special ticket types
                if any(ex in name for ex in config.vatican_excluded_keywords):
                    continue
                # Must be available
                if visit.get("availability") != "AVAILABLE":
                    continue
                return visit

        except requests.RequestException as e:
            logger.error("Search API error: %s", e)

        return None

    def _get_time_slots(
        self, date_str: str, visitors: int, ticket: dict
    ) -> List[Slot]:
        """Call the time availability API and return available slots."""
        session = self._make_session()
        try:
            resp = session.get(
                f"{VATICAN_BASE}/api/visit/timeavail",
                params={
                    "lang": "it",
                    "visitLang": "",
                    "visitTypeId": str(ticket["id"]),
                    "visitorNum": str(visitors),
                    "visitDate": date_str,
                },
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning("Timeavail API returned %d", resp.status_code)
                return []

            data = resp.json()
            timetable = data.get("timetable", [])

            slots = []
            for entry in timetable:
                status = entry.get("availability", "")

                # Skip unavailable
                if status in ("SOLD_OUT", "NOT_ALLOWED", "UNAVAILABLE"):
                    continue
                # Skip low availability with 0 residual
                if status == "LOW_AVAILABILITY" and entry.get("residual", 0) <= 0:
                    continue

                slots.append(Slot(
                    date=date_str,
                    time=entry.get("time", ""),
                    slot_id=str(entry.get("id", "")),
                    ticket_id=str(ticket.get("id", "")),
                    ticket_name=ticket.get("name", "Musei Vaticani"),
                    visitors=visitors,
                    price=float(entry.get("price", 0)),
                    residual=int(entry.get("residual", 0)),
                ))

            # Sort by time
            slots.sort(key=lambda s: s.time)
            return slots

        except requests.RequestException as e:
            logger.error("Timeavail API error: %s", e)

        return []

    # ── Helpers ──────────────────────────────────────────────────────────

    def _make_session(self) -> requests.Session:
        """Create a requests session, optionally with proxy."""
        s = requests.Session()
        s.headers.update(HEADERS)
        proxy = config.proxy_url
        if proxy:
            s.proxies = {"http": proxy, "https": proxy}
        return s

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """Ensure date is in DD/MM/YYYY format."""
        date_str = date_str.strip()
        # If YYYY-MM-DD, convert
        if "-" in date_str:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                return dt.strftime("%d/%m/%Y")
            except ValueError:
                pass
        return date_str


# ── Singleton ────────────────────────────────────────────────────────────────

_finder: SlotFinder | None = None


def get_finder() -> SlotFinder:
    global _finder
    if _finder is None:
        _finder = SlotFinder()
    return _finder


# ── Quick check function ────────────────────────────────────────────────────

def check_availability(date_str: str, visitors: int = 2) -> List[Slot]:
    """Convenience: check slots for a date. Returns list of available Slot objects."""
    return get_finder().find_slots(date_str, visitors, use_cache=False)
