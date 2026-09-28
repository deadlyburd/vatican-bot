"""Offline tests for orchestrator glue + sheet helpers (slice 3)."""
from __future__ import annotations

import unittest

from desktop_app.sheets import extract_sheet_id
from desktop_app.orchestrator import Orchestrator
from desktop_app.config import default_config


class TestExtractSheetId(unittest.TestCase):
    def test_url(self):
        url = "https://docs.google.com/spreadsheets/d/1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg/edit#gid=0"
        self.assertEqual(extract_sheet_id(url), "1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg")

    def test_bare_id(self):
        self.assertEqual(extract_sheet_id("1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg"),
                         "1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg")

    def test_invalid(self):
        self.assertEqual(extract_sheet_id("not a url"), "")
        self.assertEqual(extract_sheet_id(""), "")

    def test_garbage_short_token(self):
        self.assertEqual(extract_sheet_id("short"), "")


class TestStaggerDelays(unittest.TestCase):
    def test_unique_dates_no_delay(self):
        self.assertEqual(
            Orchestrator.stagger_delays(["a", "b", "c"], 120), [0, 0, 0])

    def test_same_date_staggers(self):
        self.assertEqual(
            Orchestrator.stagger_delays(["a", "a", "b", "a"], 120),
            [0, 120, 0, 240])

    def test_zero_gap(self):
        self.assertEqual(
            Orchestrator.stagger_delays(["a", "a"], 0), [0, 0])


class TestMatchProvider(unittest.TestCase):
    def test_vatican_match(self):
        orch = Orchestrator(default_config())
        self.assertIsNotNone(orch.match_provider("Musei Vaticani - Biglietti"))
        self.assertIsNone(orch.match_provider("Colosseum Underground"))


class TestAssignProxy(unittest.TestCase):
    def test_no_proxies(self):
        orch = Orchestrator(default_config())
        self.assertIsNone(orch.assign_proxy("29/10/2026"))

    def test_sticky(self):
        from desktop_app.config import ProxyConfig
        cfg = default_config()
        cfg.proxies = [
            ProxyConfig(host="1.1.1.1", port=80),
            ProxyConfig(host="2.2.2.2", port=80),
        ]
        orch = Orchestrator(cfg)
        a = orch.assign_proxy("29/10/2026")
        self.assertIsNotNone(a)
        self.assertEqual(a.host, orch.assign_proxy("29/10/2026").host)


if __name__ == "__main__":
    unittest.main()
