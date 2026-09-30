"""Manual slot sniper — watch a specific date+time and book the instant it opens.

No Google Sheets required. You add a watch (date, time, visitors, name, email)
in the dashboard; a background thread polls the Vatican API and, the moment that
exact time slot becomes available, launches a booking and holds it.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import os
import sys
import threading
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

# slot_finder lives at the repo root (outside the package)
_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _root not in sys.path:
    sys.path.insert(0, _root)
from slot_finder import RateLimitError  # noqa: E402

from .config import AppConfig
from .providers import BookingProvider, Slot, default_registry
from .runner import run_booking
from .schema import BookingTarget, parse_date
from .telemetry import send_alert

log = logging.getLogger("sniper")

POLL_INTERVAL = 20       # seconds between slot checks (normal)
MAX_BACKOFF = 4          # exponential backoff cap: 20s * 2^4 = 320s
RETRY_DELAY = 300        # seconds to wait before re-arming a failed booking
MAX_ATTEMPTS = 3         # give up after this many booking attempts per watch


@dataclass
class WatchTarget:
    date: str            # DD/MM/YYYY or YYYY-MM-DD
    time: str            # HH:MM
    visitors: int = 2
    name: str = ""
    email: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: str = "watching"
    slot: Optional[Slot] = None
    attempts: int = 0    # booking attempts so far

    def to_dict(self) -> dict:
        """JSON-safe representation."""
        return {
            "id": self.id,
            "date": self.date,
            "time": self.time,
            "visitors": self.visitors,
            "name": self.name,
            "email": self.email,
            "status": self.status,
            "attempts": self.attempts,
            "slot": None if self.slot is None else {
                "date": self.slot.date,
                "time": self.slot.time,
                "slot_id": self.slot.slot_id,
                "ticket_id": self.slot.ticket_id,
            },
        }


def normalize_time(t: str) -> str:
    """Normalize a time to HH:MM (zero-padded)."""
    t = (t or "").strip()
    if ":" not in t:
        return t
    h, m = t.split(":", 1)
    return f"{int(h):02d}:{int(m):02d}"


def find_time_match(slots: List[Slot], time_str: str) -> Optional[Slot]:
    """Return the first slot matching the desired time (normalized)."""
    want = normalize_time(time_str)
    for s in slots:
        if normalize_time(s.time) == want:
            return s
    return None


def group_by_date_visitors(watches: List[WatchTarget]) -> dict:
    """Group watches by (date, visitors) so each date is polled only once."""
    groups: dict = {}
    for w in watches:
        groups.setdefault((w.date, w.visitors), []).append(w)
    return groups


class Watcher:
    def __init__(self, config: AppConfig, registry=None):
        self.config = config
        self.registry = registry or default_registry()
        self.provider: BookingProvider = self.registry.get("vatican")
        self.watches: dict = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # offset port/profile indices to avoid clashing with sheet-based runs (0..N)
        self._idx = itertools.count(100)
        self._backoff = 0  # current exponential backoff level

    # ── API ──────────────────────────────────────────────────────────────

    def add(self, w: WatchTarget) -> WatchTarget:
        self.watches[w.id] = w
        self.start()
        return w

    def add_multi(self, date: str, times: List[str], visitors: int = 2,
                  name: str = "", email: str = "", groups: int = 1) -> List[WatchTarget]:
        """Add watches for the given times, `groups` bookings per time (same slot)."""
        added = []
        for t in times:
            for _ in range(max(1, int(groups))):
                w = WatchTarget(date=date, time=normalize_time(t), visitors=visitors,
                                name=name, email=email)
                self.watches[w.id] = w
                added.append(w)
        self.start()
        return added

    def remove(self, wid: str) -> bool:
        return self.watches.pop(wid, None) is not None

    def list(self) -> List[WatchTarget]:
        return list(self.watches.values())

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_thread, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # ── Polling ──────────────────────────────────────────────────────────

    def _poll_thread(self) -> None:
        while not self._stop.is_set():
            rate_limited = False
            active = [
                w for w in self.watches.values()
                if w.status not in ("booking", "holding", "paid", "failed", "gave up")
                and w.attempts < MAX_ATTEMPTS
            ]

            # poll each unique (date, visitors) once, then check all its times
            for (date, visitors), ws in group_by_date_visitors(active).items():
                try:
                    slots = self.provider.find_slots(date, visitors)
                except RateLimitError:
                    rate_limited = True
                    for w in ws:
                        w.status = "rate-limited — backing off"
                    continue
                except Exception as e:  # noqa: BLE001
                    for w in ws:
                        w.status = f"error: {e}"
                    log.warning(f"[watcher] poll error for {date}: {e}")
                    continue

                for w in ws:
                    match = find_time_match(slots, w.time)
                    if match:
                        w.status = "booking"
                        w.slot = match
                        w.attempts += 1
                        log.info(f"[watch {w.id}] FOUND {w.date} {w.time} — booking now")
                        threading.Thread(target=self._book_thread, args=(w, match), daemon=True).start()
                    else:
                        w.status = f"watching {w.date} {normalize_time(w.time)}"

            # exponential backoff when rate-limited; reset once a cycle is clean
            if rate_limited:
                self._backoff = min(self._backoff + 1, MAX_BACKOFF)
            else:
                self._backoff = 0
            interval = POLL_INTERVAL * (2 ** self._backoff)
            if rate_limited:
                log.info(f"[watcher] rate-limited — backing off to {interval}s")
            self._stop.wait(interval)

    def _book_thread(self, w: WatchTarget, slot: Slot) -> None:
        try:
            asyncio.run(self._book_async(w, slot))
        except Exception as e:  # noqa: BLE001
            w.status = f"failed: {e}"
            log.exception(f"[watch {w.id}] booking error")

    async def _book_async(self, w: WatchTarget, slot: Slot) -> None:
        iso = parse_date(w.date)
        target = BookingTarget(
            booking_id=w.id,
            activity_date=iso or w.date,
            visitors=w.visitors,
            customer_name=w.name or "Manual Booking",
            customer_email=w.email or f"manual-{w.id}@example.com",
            status="CONFIRMED",
            product_title="Musei Vaticani - Biglietti d'ingresso",
            source=None,  # no sheet to write back to
        )

        def on_hold(label):
            w.status = "holding"
            if self.config.telemetry.notify_holds:
                send_alert(self.config, f"✅ WATCH HOLD — {w.date} {w.time} · {target.customer_name}")

        def on_payment(label, url):
            w.status = "paid"
            send_alert(self.config, f"💳 WATCH PAID — {w.date} {w.time} · {url[:60]}")

        idx = next(self._idx)
        ok = await run_booking(
            self.provider, target, slot, idx,
            browser_path=self.config.browser.path,
            seed_source=self.config.browser.source_profile,
            label=f"W-{w.id[:4]}",
            on_hold=on_hold,
            on_payment=on_payment,
        )
        if not ok:
            w.status = "failed"
            if self.config.telemetry.notify_failures:
                send_alert(self.config, f"🔴 WATCH FAIL — {w.date} {w.time} · {target.customer_name}")
            self._rearm(w)

    def _rearm(self, w: WatchTarget) -> None:
        """Wait RETRY_DELAY then re-arm the watch (unless it gave up or was removed)."""
        def _do():
            if w.attempts >= MAX_ATTEMPTS:
                w.status = "gave up"
                log.warning(f"[watch {w.id}] gave up after {w.attempts} attempts — {w.date} {w.time}")
                send_alert(self.config,
                           f"⚠️ WATCH GAVE UP — {w.date} {w.time} · {w.name or 'Manual'} "
                           f"(failed {w.attempts}×)")
                return
            if w.id not in self.watches:
                return
            w.status = "watching"
            log.info(f"[watch {w.id}] re-arming after failed attempt ({w.attempts}/{MAX_ATTEMPTS})")
        threading.Timer(RETRY_DELAY, _do).start()
