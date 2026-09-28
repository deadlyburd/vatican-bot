"""Orchestration glue: read bookings → match provider → find slots → run.

This is the piece the dashboard's Start button calls. It ties together the
schema-agnostic sheet reader, the provider registry, the proxy pool, and the
per-process runner.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional

from .config import AppConfig
from .notify import notify
from .proxies import Proxy, ProxyPool
from .providers import BookingProvider, ProviderRegistry, Slot, default_registry
from .runner import default_source_profile, run_booking
from .schema import BookingTarget
from .sheets import read_bookings
from .telemetry import send_alert

log = logging.getLogger("sniper")


@dataclass
class PreparedBooking:
    target: BookingTarget
    provider: BookingProvider
    slot: Slot
    proxy: Optional[Proxy]
    label: str


class Orchestrator:
    def __init__(self, config: AppConfig, registry: Optional[ProviderRegistry] = None):
        self.config = config
        self.registry = registry or default_registry()
        self.proxy_pool = ProxyPool([
            Proxy(host=p.host, port=p.port, username=p.username,
                  password=p.password, enabled=p.enabled)
            for p in config.proxies
        ])
        self.status: dict = {}
        self.state = "idle"          # idle | running | stopped
        self._stop = threading.Event()
        self._tasks: List[asyncio.Task] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ── Pure decision helpers (unit-testable) ────────────────────────────────

    def match_provider(self, product_title: str) -> Optional[BookingProvider]:
        return self.registry.match(product_title)

    def assign_proxy(self, date_dmy: str) -> Optional[Proxy]:
        return self.proxy_pool.sticky_by_date(date_dmy)

    @staticmethod
    def stagger_delays(dates: List[str], gap: int) -> List[int]:
        """Seconds to wait before each booking, spacing same-date bookings apart."""
        seen: dict = defaultdict(int)
        out: List[int] = []
        for d in dates:
            out.append(seen[d] * gap)
            seen[d] += 1
        return out

    # ── Prepare (network: sheets + slot discovery) ───────────────────────────

    def prepare(self) -> List[PreparedBooking]:
        targets = read_bookings(self.config)
        prepared: List[PreparedBooking] = []
        for i, t in enumerate(targets):
            provider = self.match_provider(t.product_title)
            if provider is None:
                log.info(f"[{t.booking_id}] no provider for '{t.product_title[:40]}'")
                continue
            slots = provider.find_slots(t.date_dmy, t.visitors)
            if not slots:
                log.warning(f"[{t.booking_id}] no slots for {t.date_dmy}")
                continue
            prepared.append(PreparedBooking(
                target=t,
                provider=provider,
                slot=slots[0],
                proxy=self.assign_proxy(t.date_dmy),
                label=f"T{i + 1:02d}",
            ))
        return prepared

    # ── Run (async, one process per booking) ─────────────────────────────────

    async def _run_prepared(self, prepared: List[PreparedBooking]) -> List[object]:
        dates = [pb.target.date_dmy for pb in prepared]
        delays = self.stagger_delays(dates, self.config.booking.stagger_same_date_seconds)
        self._tasks = [
            asyncio.create_task(self._run_one(i, pb, delays[i]))
            for i, pb in enumerate(prepared)
        ]
        return await asyncio.gather(*self._tasks, return_exceptions=True)

    def _write_result(self, pb: PreparedBooking, status: str,
                      payment_link: str = "", confirmation: str = "") -> None:
        """Write a booking result back to the source sheet (in a worker thread)."""
        if not pb.target.source:
            return
        try:
            from .sheets import write_booking_result
            write_booking_result(self.config, pb.target.source, pb.target.booking_id,
                                 status, payment_link=payment_link, confirmation=confirmation)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[{pb.label}] write-back failed: {e}")

    async def _run_one(self, i: int, pb: PreparedBooking, delay: int) -> bool:
        label = pb.label
        if delay:
            self.status[label] = {"step": f"waiting {delay // 60}m (stagger)", "ok": False}
            await asyncio.sleep(delay)
        self.status[label] = {"step": "launching", "ok": False}

        # Mark attempt in the sheet (non-blocking)
        threading.Thread(target=self._write_result,
                         args=(pb, "BOOKING"), daemon=True).start()

        def on_hold(lbl):
            threading.Thread(target=self._write_result,
                             args=(pb, "HELD"), daemon=True).start()

        def on_payment(lbl, url):
            threading.Thread(target=self._write_result,
                             args=(pb, "PAID", url), daemon=True).start()

        seed = self.config.browser.source_profile or default_source_profile()
        ok = await run_booking(
            pb.provider, pb.target, pb.slot, i,
            proxy=pb.proxy,
            browser_path=self.config.browser.path,
            label=label,
            seed_source=seed,
            on_hold=on_hold,
            on_payment=on_payment,
        )
        if ok:
            self.status[label] = {"step": "HOLDING", "ok": True}
            notify("Hold active",
                   f"{pb.target.customer_name} · {pb.slot.date} {pb.slot.time}")
            if self.config.telemetry.notify_holds:
                threading.Thread(
                    target=send_alert,
                    args=(self.config,
                          f"✅ HOLD — {pb.target.customer_name} · {pb.slot.date} {pb.slot.time}"),
                    daemon=True,
                ).start()
        else:
            self.status[label] = {"step": "FAILED", "ok": False}
            threading.Thread(target=self._write_result,
                             args=(pb, "FAILED"), daemon=True).start()
            notify("Booking failed",
                   f"{pb.target.customer_name} · {pb.slot.date} {pb.slot.time}")
            if self.config.telemetry.notify_failures:
                threading.Thread(
                    target=send_alert,
                    args=(self.config,
                          f"🔴 FAIL — {pb.target.customer_name} · {pb.slot.date} {pb.slot.time}"),
                    daemon=True,
                ).start()
        return ok

    def run(self) -> None:
        """Blocking run. Call in a worker thread (own event loop)."""
        self._stop.clear()
        self.state = "running"
        prepared = self.prepare()
        if not prepared:
            log.info("Nothing to book (no targets or no open slots).")
            self.state = "idle"
            return
        log.info(f"Orchestrating {len(prepared)} booking(s)...")
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._run_prepared(prepared))
        except asyncio.CancelledError:
            pass
        finally:
            self.state = "stopped"

    def stop(self) -> None:
        self._stop.set()
        if self._loop and self._tasks:
            for t in self._tasks:
                self._loop.call_soon_threadsafe(t.cancel)
        self.state = "stopped"
