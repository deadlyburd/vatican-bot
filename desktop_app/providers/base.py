"""Provider abstraction for the desktop sniper.

Each venue (Vatican, a future Colosseum/Uffizi/... adapter) subclasses
BookingProvider and supplies the venue-specific bits: slot discovery, the entry
URL template, and the browser booking flow. The orchestration + process
management lives in runner.py and is venue-agnostic.

This module is pure (no browser launch), so it can be unit-tested offline.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from ..schema import BookingTarget


@dataclass
class Slot:
    """A bookable time slot, normalized across venues."""
    date: str           # DD/MM/YYYY (the format Vatican's API uses)
    time: str           # HH:MM
    slot_id: str
    ticket_id: str
    ticket_name: str = ""
    visitors: int = 0
    price: float = 0.0
    residual: int = 0

    @property
    def key(self) -> str:
        return f"{self.date}_{self.time}_{self.ticket_id}"


# ── Shared async helpers (work on a Playwright page) ──────────────────────────

async def wait_for(page, js, timeout=15, interval=0.4, label=""):
    """Poll a Playwright page until `js` evaluates truthy."""
    for _ in range(max(1, int(timeout / interval))):
        try:
            val = await page.evaluate(js)
            if val:
                return val
        except Exception:
            pass
        await page.wait_for_timeout(int(interval * 1000))
    return None


async def pfill(page, selector, value):
    """Fill an input by setting value + dispatching input/change events."""
    safe = str(value).replace("`", "\\`")
    try:
        await page.evaluate(f"""
            (() => {{
                const el = document.querySelector(`{selector}`);
                if (!el) return;
                el.focus();
                el.value = `{safe}`;
                el.dispatchEvent(new Event('input',  {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                el.blur();
            }})()
        """)
    except Exception:
        pass


# ── Provider ABC ──────────────────────────────────────────────────────────────

class BookingProvider(abc.ABC):
    venue_id: str = ""
    display_name: str = ""
    keywords: List[str] = []   # used to recognize this venue from a sheet row

    def matches(self, product_title: str) -> bool:
        t = (product_title or "").lower()
        return any(k.lower() in t for k in self.keywords)

    def find_slots(self, date_dmy: str, visitors: int) -> List[Slot]:
        raise NotImplementedError

    def entry_url(self, target: "BookingTarget", slot: Slot) -> str:
        raise NotImplementedError

    async def book(self, page, target: "BookingTarget", slot: Slot, label: str,
                   on_hold=None, on_payment=None, navigate: bool = True) -> bool:
        """Run the full booking flow on an already-open page. Return True on hold.

        on_hold(label) is called once the hold is established; on_payment(label, url)
        is called when a payment redirect is captured. Both are optional.
        Set navigate=False if the page is already on the deep link (pre-warm).
        """
        raise NotImplementedError


# ── Registry ──────────────────────────────────────────────────────────────────

class ProviderRegistry:
    def __init__(self, providers: Optional[List[BookingProvider]] = None):
        self._providers: List[BookingProvider] = list(providers or [])

    def register(self, provider: BookingProvider) -> BookingProvider:
        self._providers.append(provider)
        return provider

    def all(self) -> List[BookingProvider]:
        return list(self._providers)

    def get(self, venue_id: str) -> Optional[BookingProvider]:
        for p in self._providers:
            if p.venue_id == venue_id:
                return p
        return None

    def match(self, product_title: str) -> Optional[BookingProvider]:
        for p in self._providers:
            if p.matches(product_title):
                return p
        return None
