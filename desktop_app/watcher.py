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
from .runner import STEALTH_JS, detect_browser, run_booking
from .schema import BookingTarget, parse_date
from .telemetry import send_alert

log = logging.getLogger("sniper")

POLL_INTERVAL = 3        # default seconds between slot checks (overridden by config.booking.poll_interval_seconds)
MAX_BACKOFF = 4          # exponential backoff cap: base * 2^4
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
    prewarm: bool = False  # keep a browser warm on the page, ready to click instantly
    # Ticket type: "standard" (MV-Biglietti) or "guided" (MV-Visite-Guidate)
    ticket_type: str = "standard"
    # Language code for guided tours (ignored for standard tickets)
    language: str = "ENG"

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
            "prewarm": self.prewarm,
            "ticket_type": self.ticket_type,
            "language": self.language,
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
        self._poll_idx = 0  # round-robin counter for the datacenter poll proxies
        # pre-warm: a persistent asyncio loop that keeps warm browsers alive
        self._warm_pages: dict = {}     # watch_id -> (playwright, context, page)
        self._warm_loop = None
        self._warm_thread: Optional[threading.Thread] = None

    # ── API ──────────────────────────────────────────────────────────────

    def add(self, w: WatchTarget) -> WatchTarget:
        self.watches[w.id] = w
        self.start()
        if w.prewarm:
            self._prewarm(w)
        return w

    def add_multi(self, date: str, times: List[str], visitors: int = 2,
                  name: str = "", email: str = "", groups: int = 1,
                  prewarm: bool = False, ticket_type: str = "standard",
                  language: str = "ENG") -> List[WatchTarget]:
        """Add watches for the given times, `groups` bookings per time (same slot)."""
        added = []
        for t in times:
            for _ in range(max(1, int(groups))):
                w = WatchTarget(date=date, time=normalize_time(t), visitors=visitors,
                                name=name, email=email, prewarm=prewarm,
                                ticket_type=ticket_type, language=language)
                self.watches[w.id] = w
                added.append(w)
        self.start()
        for w in added:
            if w.prewarm:
                self._prewarm(w)
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

            # rotate through the datacenter poll proxies so no single IP gets throttled
            proxies = [p for p in self.config.booking.poll_proxies if p.host]
            poll_proxy = ""
            if proxies:
                poll_proxy = proxies[self._poll_idx % len(proxies)].url()
                self._poll_idx += 1

            # poll each unique (date, visitors) once, then check all its times
            for (date, visitors), ws in group_by_date_visitors(active).items():
                # All watches in the group share the same date+visitors.
                # Use the ticket_type/language from the first watch in the group.
                first = ws[0]
                try:
                    slots = self.provider.find_slots(
                        date, visitors,
                        poll_proxy=poll_proxy,
                        ticket_type=first.ticket_type,
                        language=first.language,
                    )
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
                        if w.prewarm and w.id in self._warm_pages:
                            # book on the already-warm page (no launch delay)
                            self._run_on_warm_loop(self._book_warm(w, match))
                        else:
                            threading.Thread(target=self._book_thread, args=(w, match), daemon=True).start()
                    else:
                        w.status = f"watching {w.date} {normalize_time(w.time)}"

            # exponential backoff when rate-limited; reset once a cycle is clean
            if rate_limited:
                self._backoff = min(self._backoff + 1, MAX_BACKOFF)
            else:
                self._backoff = 0
            base = self.config.booking.poll_interval_seconds or POLL_INTERVAL
            interval = base * (2 ** self._backoff)
            if rate_limited:
                log.info(f"[watcher] rate-limited — backing off to {interval}s")
            self._stop.wait(interval)

    def _book_thread(self, w: WatchTarget, slot: Slot) -> None:
        try:
            asyncio.run(self._book_async(w, slot))
        except Exception as e:  # noqa: BLE001
            w.status = f"failed: {e}"
            log.exception(f"[watch {w.id}] booking error")

    def _make_target(self, w: WatchTarget) -> BookingTarget:
        iso = parse_date(w.date)
        product = (
            "Musei Vaticani - Visita Guidata"
            if w.ticket_type.lower() == "guided"
            else "Musei Vaticani - Biglietti d'ingresso"
        )
        return BookingTarget(
            booking_id=w.id,
            activity_date=iso or w.date,
            visitors=w.visitors,
            customer_name=w.name or "Manual Booking",
            customer_email=w.email or f"manual-{w.id}@example.com",
            status="CONFIRMED",
            product_title=product,
            ticket_type=w.ticket_type,
            language=w.language,
            source=None,  # no sheet to write back to
        )

    def _make_callbacks(self, w: WatchTarget, target: BookingTarget):
        def on_hold(label):
            w.status = "holding"
            if self.config.telemetry.notify_holds:
                send_alert(self.config, f"✅ WATCH HOLD — {w.date} {w.time} · {target.customer_name}")

        def on_payment(label, url):
            w.status = "paid"
            send_alert(self.config, f"💳 WATCH PAID — {w.date} {w.time} · {url[:60]}")

        return on_hold, on_payment

    async def _book_async(self, w: WatchTarget, slot: Slot) -> None:
        target = self._make_target(w)
        on_hold, on_payment = self._make_callbacks(w, target)
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

    # ── Pre-warm (browser already open on the page, no launch delay) ──────

    def _ensure_warm_loop(self) -> None:
        if self._warm_thread and self._warm_thread.is_alive():
            return
        self._warm_thread = threading.Thread(target=self._warm_loop_main, daemon=True)
        self._warm_thread.start()

    def _warm_loop_main(self) -> None:
        self._warm_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._warm_loop)
        self._warm_loop.run_forever()

    def _run_on_warm_loop(self, coro) -> None:
        self._ensure_warm_loop()
        asyncio.run_coroutine_threadsafe(coro, self._warm_loop)

    def _prewarm(self, w: WatchTarget) -> None:
        """Launch a browser + navigate to the deep link, keep it warm."""
        if w.id in self._warm_pages:
            return
        self._run_on_warm_loop(self._launch_warm(w))

    async def _launch_warm(self, w: WatchTarget) -> None:
        from playwright.async_api import async_playwright

        target = self._make_target(w)
        placeholder = Slot(date=target.date_dmy, time=w.time, slot_id="", ticket_id="")
        url = self.provider.entry_url(target, placeholder)
        browser = detect_browser(self.config.browser.path)
        pw = context = page = None
        try:
            pw = await async_playwright().start()
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=os.path.join(os.path.expanduser("~"), f"vatican_warm_{w.id}"),
                executable_path=browser,
                headless=False,
                ignore_default_args=["--enable-automation"],
                args=[
                    "--no-first-run", "--no-default-browser-check",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--window-size=1000,750",
                ],
                locale="it-IT", timezone_id="Europe/Rome", viewport=None,
            )
            await context.add_init_script(STEALTH_JS)
            page = context.pages[0] if context.pages else await context.new_page()
            # Patch the already-open about:blank immediately
            try:
                await page.evaluate(STEALTH_JS)
            except Exception:
                pass
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._warm_pages[w.id] = (pw, context, page)
            w.status = f"prewarmed {w.date} {normalize_time(w.time)}"
            log.info(f"[watch {w.id}] prewarm ready — browser waiting on the page")
            # keep warm + refresh periodically so availability is fresh when the slot opens
            elapsed = 0
            while w.id in self.watches and w.status not in ("booking", "holding", "paid", "gave up"):
                await asyncio.sleep(5)
                elapsed += 5
                if elapsed >= 30:
                    elapsed = 0
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=30000)
                    except Exception:
                        pass
        except Exception as e:  # noqa: BLE001
            log.warning(f"[watch {w.id}] prewarm failed: {e}")
        finally:
            self._warm_pages.pop(w.id, None)
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            if pw:
                try:
                    await pw.stop()
                except Exception:
                    pass

    async def _book_warm(self, w: WatchTarget, slot: Slot) -> None:
        entry = self._warm_pages.get(w.id)
        if not entry:
            threading.Thread(target=self._book_thread, args=(w, slot), daemon=True).start()
            return
        pw, context, page = entry
        target = self._make_target(w)
        on_hold, on_payment = self._make_callbacks(w, target)
        try:
            ok = await self.provider.book(page, target, slot, f"W-{w.id[:4]}",
                                          on_hold=on_hold, on_payment=on_payment,
                                          navigate=False)
            if not ok:
                w.status = "failed"
                if self.config.telemetry.notify_failures:
                    send_alert(self.config, f"🔴 WATCH FAIL — {w.date} {w.time} · {target.customer_name}")
                self._rearm(w)
        except Exception as e:  # noqa: BLE001
            w.status = f"failed: {e}"
            log.exception(f"[watch {w.id}] warm booking error")
        finally:
            self._warm_pages.pop(w.id, None)
            try:
                await context.close()
            except Exception:
                pass
            try:
                await pw.stop()
            except Exception:
                pass

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
