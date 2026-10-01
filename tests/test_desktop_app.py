"""Offline unit tests for the desktop_app slice-1 foundation."""
from __future__ import annotations

import datetime
import unittest

from desktop_app.config import (
    AppConfig, ProxyConfig, SheetConfig, default_config, save_config, load_config,
)
from desktop_app.schema import (
    DEFAULT_COLUMN_MAP, parse_date, suggest_mapping,
)
from desktop_app.proxies import Proxy, ProxyPool
from desktop_app.sheets import rows_to_targets


TODAY = datetime.date(2026, 9, 1)


class TestParseDate(unittest.TestCase):
    def test_iso(self):
        self.assertEqual(parse_date("2026-10-29"), "2026-10-29")

    def test_dmy(self):
        self.assertEqual(parse_date("29/10/2026"), "2026-10-29")

    def test_mdy(self):
        self.assertEqual(parse_date("10/29/2026"), "2026-10-29")

    def test_dash(self):
        self.assertEqual(parse_date("29-10-2026"), "2026-10-29")

    def test_dot(self):
        self.assertEqual(parse_date("29.10.2026"), "2026-10-29")

    def test_invalid(self):
        self.assertIsNone(parse_date("not-a-date"))

    def test_none(self):
        self.assertIsNone(parse_date(None))
        self.assertIsNone(parse_date(""))

    def test_date_object(self):
        self.assertEqual(parse_date(datetime.date(2026, 10, 29)), "2026-10-29")

    def test_explicit_format(self):
        self.assertEqual(parse_date("29|10|2026", fmt="%d|%m|%Y"), "2026-10-29")


class TestSuggestMapping(unittest.TestCase):
    def test_aliases(self):
        headers = ["Booking ID", "Activity Date", "Pax", "Customer Name",
                   "Email", "Product", "Status"]
        m = suggest_mapping(headers)
        self.assertEqual(m["booking_id"], "Booking ID")
        self.assertEqual(m["activity_date"], "Activity Date")
        self.assertEqual(m["visitors"], "Pax")
        self.assertEqual(m["customer_name"], "Customer Name")
        self.assertEqual(m["customer_email"], "Email")
        self.assertEqual(m["product_title"], "Product")
        self.assertEqual(m["status"], "Status")

    def test_partial(self):
        # Only some headers present -> only those fields mapped.
        m = suggest_mapping(["Order ID", "Tour Date", "Guests"])
        self.assertEqual(m["booking_id"], "Order ID")
        self.assertEqual(m["activity_date"], "Tour Date")
        self.assertEqual(m["visitors"], "Guests")
        self.assertNotIn("customer_email", m)


class TestRowsToTargets(unittest.TestCase):
    def _cfg(self, **kw):
        base = dict(
            name="t", sheet_id="x", tab="Activity_Lines",
            column_map=dict(DEFAULT_COLUMN_MAP),
        )
        base.update(kw)
        return SheetConfig(**base)

    def _row(self, **overrides):
        row = {
            "bookingId": "B1",
            "activityDate": "2026-10-29",
            "totalParticipants": "2",
            "customerName": "Mario Rossi",
            "customerEmail": "m@x.com",
            "productTitle": "Musei Vaticani - Biglietti d'ingresso",
            "status": "PENDING",
        }
        row.update(overrides)
        return row

    def test_basic(self):
        targets = rows_to_targets([self._row()], self._cfg(), today=TODAY)
        self.assertEqual(len(targets), 1)
        t = targets[0]
        self.assertEqual(t.booking_id, "B1")
        self.assertEqual(t.activity_date, "2026-10-29")
        self.assertEqual(t.visitors, 2)
        self.assertEqual(t.date_dmy, "29/10/2026")

    def test_filters_non_vatican(self):
        cfg = self._cfg()
        self.assertEqual(rows_to_targets([self._row(productTitle="Colosseum Tour")], cfg, today=TODAY), [])

    def test_filters_past(self):
        cfg = self._cfg()
        self.assertEqual(rows_to_targets([self._row(activityDate="2020-01-01")], cfg, today=TODAY), [])

    def test_filters_status(self):
        cfg = self._cfg()
        self.assertEqual(rows_to_targets([self._row(status="CANCELLED")], cfg, today=TODAY), [])

    def test_custom_column_map(self):
        cfg = self._cfg(column_map={
            "booking_id": "OrderID", "activity_date": "Date", "visitors": "Guests",
            "customer_name": "Client", "customer_email": "Email",
            "product_title": "Tour", "status": "State",
        })
        row = {"OrderID": "B9", "Date": "29/10/2026", "Guests": "3",
               "Client": "Luca", "Email": "l@x.com",
               "Tour": "Musei Vaticani", "State": "CONFIRMED"}
        targets = rows_to_targets([row], cfg, today=TODAY)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].booking_id, "B9")
        self.assertEqual(targets[0].visitors, 3)
        self.assertEqual(targets[0].activity_date, "2026-10-29")

    def test_dedupe(self):
        cfg = self._cfg()
        targets = rows_to_targets([self._row(), self._row(activityDate="2026-11-01")], cfg, today=TODAY)
        self.assertEqual(len(targets), 1)

    def test_sort_by_date(self):
        cfg = self._cfg()
        rows = [
            self._row(bookingId="B2", activityDate="2026-11-01"),
            self._row(bookingId="B1", activityDate="2026-10-20"),
        ]
        targets = rows_to_targets(rows, cfg, today=TODAY)
        self.assertEqual([t.booking_id for t in targets], ["B1", "B2"])

    def test_missing_booking_id_skipped(self):
        cfg = self._cfg()
        self.assertEqual(rows_to_targets([self._row(bookingId="")], cfg, today=TODAY), [])

    def test_source_tagged(self):
        cfg = self._cfg()
        src = {"sheet_id": "S123", "tab": "Activity_Lines"}
        targets = rows_to_targets([self._row()], cfg, today=TODAY, source=src)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].source, src)


class TestProxyPool(unittest.TestCase):
    def _pool(self):
        return ProxyPool([
            Proxy(host="1.1.1.1", port=80),
            Proxy(host="2.2.2.2", port=80),
        ])

    def test_round_robin(self):
        pool = self._pool()
        self.assertEqual(pool.round_robin().host, "1.1.1.1")
        self.assertEqual(pool.round_robin().host, "2.2.2.2")
        self.assertEqual(pool.round_robin().host, "1.1.1.1")

    def test_sticky_deterministic(self):
        pool = self._pool()
        first = pool.sticky_by_date("29/10/2026").host
        for _ in range(5):
            self.assertEqual(pool.sticky_by_date("29/10/2026").host, first)

    def test_active_skips_disabled(self):
        pool = ProxyPool([
            Proxy(host="1.1.1.1", port=80),
            Proxy(host="2.2.2.2", port=80, enabled=False),
        ])
        self.assertEqual(len(pool.active()), 1)
        self.assertEqual(pool.round_robin().host, "1.1.1.1")

    def test_empty_pool(self):
        pool = ProxyPool([])
        self.assertIsNone(pool.round_robin())
        self.assertIsNone(pool.sticky_by_date("x"))

    def test_chrome_flag_no_auth(self):
        p = Proxy(host="1.1.1.1", port=8080)
        self.assertEqual(p.chrome_flag(), "--proxy-server=http://1.1.1.1:8080")

    def test_chrome_flag_auth_none(self):
        p = Proxy(host="1.1.1.1", port=8080, username="u", password="p")
        self.assertIsNone(p.chrome_flag())

    def test_url(self):
        p = Proxy(host="1.1.1.1", port=8080, username="u", password="p")
        self.assertEqual(p.url(), "http://u:p@1.1.1.1:8080")

    def test_playwright_proxy(self):
        p = Proxy(host="1.1.1.1", port=8080, username="u", password="p")
        self.assertEqual(p.playwright_proxy(),
                         {"server": "http://1.1.1.1:8080", "username": "u", "password": "p"})


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = default_config()
        self.assertEqual(len(cfg.sheets), 1)
        self.assertEqual(cfg.sheets[0].column_map, DEFAULT_COLUMN_MAP)
        self.assertEqual(cfg.booking.default_visitors, 2)

    def test_roundtrip(self):
        cfg = default_config()
        cfg.proxies.append(ProxyConfig(host="9.9.9.9", port=3128))
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            save_config(cfg, path)
            loaded = load_config(path)
        self.assertEqual(loaded.booking.max_concurrent, cfg.booking.max_concurrent)
        self.assertEqual(loaded.sheets[0].column_map, cfg.sheets[0].column_map)
        self.assertEqual(loaded.proxies[0].host, "9.9.9.9")

    def test_load_missing_returns_default(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            cfg = load_config(os.path.join(d, "nope.json"))
        self.assertIsInstance(cfg, AppConfig)

    def test_poll_proxies_roundtrip_and_migration(self):
        from dataclasses import asdict
        from desktop_app.config import ProxyConfig
        cfg = default_config()
        cfg.booking.poll_proxies = [
            ProxyConfig(host="31.58.9.4", port=6077, username="u", password="p"),
            ProxyConfig(host="45.38.107.97", port=6014, username="u", password="p"),
        ]
        c2 = AppConfig.from_dict(asdict(cfg))
        self.assertEqual(len(c2.booking.poll_proxies), 2)
        self.assertEqual(c2.booking.poll_proxies[0].host, "31.58.9.4")
        # old single poll_proxy migrates to a 1-item list
        c3 = AppConfig.from_dict({"booking": {"poll_proxy": {"host": "1.2.3.4", "port": 8080}}})
        self.assertEqual(len(c3.booking.poll_proxies), 1)
        self.assertEqual(c3.booking.poll_proxies[0].host, "1.2.3.4")


if __name__ == "__main__":
    unittest.main()
