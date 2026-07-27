#!/usr/bin/env python3
"""
API-ONLY SLOT FINDER
=====================
Uses ONLY search + timeavail APIs to find available Vatican slots.
Never touches the recap endpoint — booking is done via browser extension.

This is the eyes of the system. The extension is the hands.
"""

import os
import json
import logging
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────
VATICAN_BASE = "https://tickets.museivaticani.va"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{VATICAN_BASE}/",
    "Origin": VATICAN_BASE,
}

# Excluded ticket types (not Vatican Museums standard entry)
EXCLUDED = [
    'pellegrinaggi', 'lunch', 'pranzo', 'gruppi', 'specola',
    'palazzo', 'didattiche', 'scuole', 'pellegrinaggio',
]

# Realistic Rome phone prefixes for random data
ROME_PREFIXES = ['06', '333', '338', '339', '347', '328', '349', '340']


@dataclass
class AvailableSlot:
    """A bookable Vatican time slot."""
    date: str               # DD/MM/YYYY
    time: str               # HH:MM
    slot_id: str            # Vatican's internal slot ID
    ticket_id: str          # Vatican's ticket type ID
    ticket_name: str        # Human-readable ticket name
    visitors: int
    price: float = 0.0
    residual: int = 0

    @property
    def key(self) -> str:
        return f"{self.date}_{self.time}_{self.ticket_id}"

    def to_command(self, profile: dict = None, participants: list = None) -> dict:
        """Convert to a booking command for the extension."""
        return {
            "date": self.date,
            "time": self.time,
            "visitors": self.visitors,
            "ticket_id": self.ticket_id,
            "ticket_name": self.ticket_name,
            "slot_id": self.slot_id,
            "profile": profile or {},
            "participants": participants or [],
            "priority": 1,
        }


class SlotFinder:
    """
    Finds available Vatican time slots using only search + timeavail APIs.
    """

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        self._cache: Dict[str, list] = {}  # date_str → slots
        self._cache_time: Dict[str, float] = {}

    # ── Public API ──────────────────────────────────────────────────

    def find_slots(
        self,
        target_date: str,
        visitors: int = 2,
        use_cache: bool = True,
        prefer_afternoon: bool = True,
    ) -> List[AvailableSlot]:
        """
        Find all available time slots for a given date.

        Args:
            target_date: DD/MM/YYYY OR YYYY-MM-DD format (auto-detected)
            visitors: Number of visitors
            use_cache: If True, use cached results if < 60s old
            prefer_afternoon: Sort afternoon slots first

        Returns:
            List of AvailableSlot, sorted by preference
        """
        # Normalize date to DD/MM/YYYY for Vatican API
        target_date = self._normalize_date(target_date)
        cache_key = f"{target_date}_{visitors}"
        if use_cache and cache_key in self._cache:
            age = time.time() - self._cache_time.get(cache_key, 0)
            if age < 60:
                logger.debug(f"Using cached slots for {target_date} ({age:.0f}s old)")
                return self._cache[cache_key]

        # Step 1: Search API — get ticket type IDs
        ticket = self._search_ticket(target_date, visitors)
        if not ticket:
            logger.info(f"No Vatican ticket found for {target_date}")
            return []

        # Step 2: Timeavail API — get time slots
        slots = self._timeavail_slots(target_date, visitors, ticket)

        # Cache
        self._cache[cache_key] = slots
        self._cache_time[cache_key] = time.time()

        # Sort: afternoon first if preferred
        if prefer_afternoon:
            slots.sort(key=lambda s: (
                0 if 12 <= self._parse_hour(s.time) <= 16 else 1,
                s.time,
            ))

        return slots

    def find_next_available(
        self,
        start_date: str = None,
        max_days: int = 30,
        visitors: int = 2,
        min_slots: int = 1,
    ) -> List[AvailableSlot]:
        """
        Scan forward from start_date to find the next date with available slots.

        Returns first date that has at least min_slots available.
        """
        if start_date is None:
            start_date = date.today().strftime("%d/%m/%Y")

        day, month, year = start_date.split('/')
        current = date(int(year), int(month), int(day))

        for offset in range(max_days):
            check_date = current + timedelta(days=offset)
            date_str = check_date.strftime("%d/%m/%Y")

            logger.info(f"Scanning {date_str} ({offset + 1}/{max_days})...")
            slots = self.find_slots(date_str, visitors, use_cache=False)

            if len(slots) >= min_slots:
                logger.info(f"✅ Found {len(slots)} slots on {date_str}")
                return slots

            # Respect rate limits
            time.sleep(1)

        logger.info(f"No available slots found in {max_days} days from {start_date}")
        return []

    def find_vatican_ticket_for_date(
        self, target_date: str, visitors: int
    ) -> Optional[Dict]:
        """Low-level: find the Vatican ticket entry from search API."""
        return self._search_ticket(target_date, visitors)

    def find_time_slots_for_ticket(
        self, target_date: str, visitors: int, ticket: Dict
    ) -> List[AvailableSlot]:
        """Low-level: find time slots for a specific ticket."""
        return self._timeavail_slots(target_date, visitors, ticket)

    # ── API Calls ───────────────────────────────────────────────────

    def _search_ticket(self, target_date: str, visitors: int) -> Optional[Dict]:
        """Call search/resultPerTag — find the Vatican Museums standard ticket."""
        try:
            r = self._session.get(
                f"{VATICAN_BASE}/api/search/resultPerTag",
                params={
                    "lang": "it",
                    "visitorNum": str(visitors),
                    "visitDate": target_date,
                    "area": "1",
                    "who": "",
                    "page": "0",
                    "tag": "MV-Biglietti",
                },
                timeout=15,
            )

            if r.status_code != 200:
                logger.warning(f"Search API returned {r.status_code}")
                return None

            data = r.json()
            visits = data.get("visits", [])

            for v in visits:
                name = v.get("name", "").lower()

                # Must be Vatican Museums standard entry
                is_vatican = any(w in name for w in ('musei vaticani', 'vatican'))
                is_entry = any(w in name for w in ('ingresso', 'biglietti', 'entrance'))
                excluded = any(w in name for w in EXCLUDED)

                if is_vatican and is_entry and not excluded:
                    avail = v.get("availability", "")
                    if avail == "SOLD_OUT" or avail == "NOT_ALLOWED":
                        logger.info(f"Vatican ticket found but {avail}")
                        return None

                    logger.info(f"Found ticket: {v.get('name')} (id={v.get('id')})")
                    return v

            logger.debug(f"No Vatican ticket in {len(visits)} results")
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Search API error: {e}")
            return None

    def _timeavail_slots(
        self, target_date: str, visitors: int, ticket: Dict
    ) -> List[AvailableSlot]:
        """Call visit/timeavail — get time slots for a ticket."""
        try:
            r = self._session.get(
                f"{VATICAN_BASE}/api/visit/timeavail",
                params={
                    "lang": "it",
                    "visitLang": "",
                    "visitTypeId": str(ticket["id"]),
                    "visitorNum": str(visitors),
                    "visitDate": target_date,
                },
                timeout=15,
            )

            # Vatican returns 500 for sold-out tickets
            if r.status_code == 500:
                logger.debug(f"Timeavail 500 — likely sold out for {target_date}")
                return []

            if r.status_code != 200:
                logger.warning(f"Timeavail returned {r.status_code}")
                return []

            data = r.json()
            timetable = data.get("timetable", [])
            ticket_name = ticket.get("name", "Unknown")
            ticket_id = str(ticket.get("id", ""))

            slots = []
            for t in timetable:
                availability = t.get("availability", "")
                if availability in ("SOLD_OUT", "NOT_ALLOWED", "UNAVAILABLE"):
                    continue

                # Residual: only skip if explicitly zero AND availability is LOW
                residual = t.get("residual")
                if residual is not None and residual <= 0 and availability == "LOW_AVAILABILITY":
                    continue

                price = t.get("price", 0) or 0
                if isinstance(price, dict):
                    price = price.get("value", 0) or 0

                slot = AvailableSlot(
                    date=target_date,
                    time=t.get("time", ""),
                    slot_id=str(t.get("id", "")),
                    ticket_id=ticket_id,
                    ticket_name=ticket_name,
                    visitors=visitors,
                    price=float(price),
                    residual=residual or 0,
                )
                slots.append(slot)

            logger.info(
                f"Timeavail: {len(slots)} available / {len(timetable)} total "
                f"for {target_date}"
            )
            return slots

        except requests.exceptions.RequestException as e:
            logger.error(f"Timeavail error: {e}")
            return []

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """Convert YYYY-MM-DD → DD/MM/YYYY if needed."""
        if '-' in date_str:
            parts = date_str.split('-')
            if len(parts) == 3 and len(parts[0]) == 4:
                return f"{parts[2]}/{parts[1]}/{parts[0]}"
        return date_str

    @staticmethod
    def _parse_hour(time_str: str) -> int:
        try:
            return int(time_str.split(':')[0])
        except (ValueError, IndexError):
            return 0


# ── CRM Integration ──────────────────────────────────────────────────

def find_slots_for_crm_booking(
    booking_date: str,
    visitors: int,
    finder: SlotFinder = None,
) -> List[AvailableSlot]:
    """
    Given a CRM booking, find available Vatican slots.
    Returns list of AvailableSlot sorted by preference.
    """
    if finder is None:
        finder = SlotFinder()

    return finder.find_slots(booking_date, visitors)


def find_next_available_for_crm(
    start_date: str,
    visitors: int,
    max_days: int = 30,
    finder: SlotFinder = None,
) -> List[AvailableSlot]:
    """
    For urgent CRM bookings without a fixed date, find the next available date.
    """
    if finder is None:
        finder = SlotFinder()

    return finder.find_next_available(start_date, max_days, visitors)


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    finder = SlotFinder()
    target = sys.argv[1] if len(sys.argv) > 1 else date.today().strftime("%d/%m/%Y")
    visitors = int(sys.argv[2]) if len(sys.argv) > 2 else 2

    print(f"\n🔍 Slot Finder — {target} | {visitors} visitors\n")

    slots = finder.find_slots(target, visitors)

    if slots:
        print(f"✅ {len(slots)} available slots:\n")
        for s in slots:
            print(f"  ⏰ {s.time} | id={s.slot_id} | ticket={s.ticket_id} | €{s.price}")
    else:
        print(f"❌ No available slots for {target}")

        # Scan forward
        print(f"\n📅 Scanning forward for next available...")
        next_slots = finder.find_next_available(target, max_days=14, visitors=visitors)
        if next_slots:
            d = next_slots[0].date
            print(f"✅ Next available: {d} — {len(next_slots)} slots")
            for s in next_slots[:5]:
                print(f"  ⏰ {s.time}")
