"""Offline tests for the provider abstraction + runner (slice 2)."""
from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace

from desktop_app.providers.base import BookingProvider, ProviderRegistry, Slot
from desktop_app.providers.vatican import VaticanProvider
from desktop_app.providers import default_registry
from desktop_app.schema import BookingTarget
from desktop_app.proxies import Proxy
from desktop_app.runner import (
    DEFAULT_BROWSERS, build_chrome_cmd, clean_profile_locks, detect_browser,
    seed_profile,
)


def _target(**kw) -> BookingTarget:
    base = dict(
        booking_id="B1", activity_date="2026-10-29", visitors=2,
        customer_name="Mario Rossi", customer_email="m@x.com",
        status="PENDING", product_title="Musei Vaticani - Biglietti d'ingresso",
    )
    base.update(kw)
    return BookingTarget(**base)


class TestSlot(unittest.TestCase):
    def test_key(self):
        s = Slot(date="29/10/2026", time="16:00", slot_id="x", ticket_id="y")
        self.assertEqual(s.key, "29/10/2026_16:00_y")


class TestProviderRegistry(unittest.TestCase):
    def test_default_registry_has_vatican(self):
        reg = default_registry()
        self.assertIsNotNone(reg.get("vatican"))

    def test_match(self):
        reg = default_registry()
        v = reg.get("vatican")
        self.assertIs(reg.match("Musei Vaticani - Biglietti d'ingresso"), v)
        self.assertIs(reg.match("Sistine Chapel tour"), v)
        self.assertIsNone(reg.match("Colosseum Underground"))

    def test_register_custom(self):
        class Fake(BookingProvider):
            venue_id = "fake"
            keywords = ["fake-venue"]

        reg = ProviderRegistry()
        reg.register(Fake())
        self.assertIsInstance(reg.match("a fake-venue tour"), Fake)
        self.assertIsNone(reg.match("vatican"))


class TestVaticanProvider(unittest.TestCase):
    def test_matches(self):
        v = VaticanProvider()
        self.assertTrue(v.matches("Musei Vaticani"))
        self.assertFalse(v.matches("Colosseum"))

    def test_entry_url(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        v = VaticanProvider()
        t = _target()
        s = Slot(date="29/10/2026", time="16:00", slot_id="2026*10964", ticket_id="846672502")
        url = v.entry_url(t, s)

        rome = ZoneInfo("Europe/Rome")
        d, m, y = "29/10/2026".split("/")
        ts = int(datetime(int(y), int(m), int(d), tzinfo=rome).timestamp() * 1000)
        self.assertEqual(
            url, f"https://tickets.museivaticani.va/home/fromtag/2/{ts}/MV-Biglietti/1")

    def test_from_available(self):
        raw = SimpleNamespace(
            date="29/10/2026", time="16:00", slot_id="s1", ticket_id="t1",
            ticket_name="Biglietto", visitors=2, price=25.0, residual=5,
        )
        s = VaticanProvider._from_available(raw)
        self.assertEqual(s.date, "29/10/2026")
        self.assertEqual(s.time, "16:00")
        self.assertEqual(s.slot_id, "s1")
        self.assertEqual(s.ticket_id, "t1")
        self.assertEqual(s.visitors, 2)

    def test_keepalive_js_contains_slot(self):
        v = VaticanProvider()
        t = _target()
        s = Slot(date="29/10/2026", time="16:00", slot_id="2026*10964", ticket_id="846672502")
        js = v.keepalive_js(s, t)
        self.assertIn("2026*10964", js)
        self.assertIn("846672502", js)
        self.assertIn("visitId", js)


class TestDetectBrowser(unittest.TestCase):
    def test_explicit_found(self):
        with tempfile.NamedTemporaryFile() as f:
            self.assertEqual(detect_browser(f.name), f.name)

    def test_explicit_missing_falls_to_defaults(self):
        # monkeypatch defaults to a temp file so the test is deterministic
        with tempfile.NamedTemporaryFile() as f:
            import desktop_app.runner as runner
            orig = runner.DEFAULT_BROWSERS
            runner.DEFAULT_BROWSERS = [f.name]
            try:
                self.assertEqual(detect_browser("/no/such/browser"), f.name)
            finally:
                runner.DEFAULT_BROWSERS = orig

    def test_no_browser(self):
        import desktop_app.runner as runner
        orig = runner.DEFAULT_BROWSERS
        runner.DEFAULT_BROWSERS = []
        try:
            self.assertEqual(detect_browser(""), "")
        finally:
            runner.DEFAULT_BROWSERS = orig


class TestBuildChromeCmd(unittest.TestCase):
    def test_base(self):
        cmd = build_chrome_cmd("/usr/bin/brave", 9400, "/tmp/p", 0)
        self.assertEqual(cmd[0], "/usr/bin/brave")
        self.assertIn("--remote-debugging-port=9400", cmd)
        self.assertIn("--user-data-dir=/tmp/p", cmd)
        self.assertIn("about:blank", cmd)

    def test_noauth_proxy_flag_inserted(self):
        p = Proxy(host="1.1.1.1", port=8080)
        cmd = build_chrome_cmd("/b", 9400, "/p", 0, proxy=p)
        self.assertIn("--proxy-server=http://1.1.1.1:8080", cmd)

    def test_auth_proxy_no_flag(self):
        p = Proxy(host="1.1.1.1", port=8080, username="u", password="p")
        cmd = build_chrome_cmd("/b", 9400, "/p", 0, proxy=p)
        self.assertFalse(any(a.startswith("--proxy-server") for a in cmd))


class TestProfileHelpers(unittest.TestCase):
    def test_clean_locks(self):
        with tempfile.TemporaryDirectory() as d:
            lock = os.path.join(d, "SingletonLock")
            open(lock, "w").close()
            clean_profile_locks(d)
            self.assertFalse(os.path.exists(lock))

    def test_seed_profile(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dest:
            default = os.path.join(src, "Default")
            os.makedirs(default)
            with open(os.path.join(default, "Cookies"), "w") as f:
                f.write("c")
            with open(os.path.join(default, "History"), "w") as f:
                f.write("h")

            result = seed_profile(dest, default)
            self.assertIn("Cookies", result)
            self.assertTrue(os.path.isfile(os.path.join(dest, "Default", "Cookies")))
            self.assertTrue(os.path.isfile(os.path.join(dest, "Default", "History")))

    def test_seed_profile_no_src(self):
        with tempfile.TemporaryDirectory() as dest:
            self.assertEqual(seed_profile(dest, "/no/such/default"), "no-src")


if __name__ == "__main__":
    unittest.main()
