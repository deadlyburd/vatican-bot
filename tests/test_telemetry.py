"""Tests for telemetry: machine id + Telegram alerts."""
from __future__ import annotations

import unittest
from unittest import mock

from desktop_app.config import AppConfig, TelemetryConfig, default_config
from desktop_app.telemetry import (
    ensure_machine_id, machine_info, send_alert, send_telegram,
)


class TestMachineId(unittest.TestCase):
    def test_generates_and_is_stable(self):
        cfg = AppConfig()
        mid = ensure_machine_id(cfg)
        self.assertEqual(len(mid), 12)
        self.assertEqual(ensure_machine_id(cfg), mid)

    def test_keeps_existing(self):
        cfg = AppConfig(machine_id="fixed123")
        self.assertEqual(ensure_machine_id(cfg), "fixed123")


class TestMachineInfo(unittest.TestCase):
    def test_nonempty(self):
        self.assertTrue(machine_info())


class TestSendAlert(unittest.TestCase):
    def test_disabled_without_creds(self):
        cfg = AppConfig()  # no token/chat id
        self.assertFalse(send_alert(cfg, "hello"))

    def test_sends_when_configured(self):
        cfg = AppConfig(telemetry=TelemetryConfig(
            machine_name="TestMac", telegram_bot_token="tok", telegram_chat_id="123"))
        with mock.patch("requests.post") as post:
            post.return_value.status_code = 200
            self.assertTrue(send_alert(cfg, "hello"))
            args, kwargs = post.call_args
            self.assertIn("hello", kwargs["json"]["text"])
            self.assertIn("TestMac", kwargs["json"]["text"])


class TestSendTelegram(unittest.TestCase):
    def test_returns_false_on_error(self):
        with mock.patch("requests.post", side_effect=Exception("boom")):
            self.assertFalse(send_telegram("tok", "123", "hi"))


class TestConfigRoundtrip(unittest.TestCase):
    def test_telemetry_fields_persist(self):
        from dataclasses import asdict
        cfg = default_config()
        cfg.machine_id = "abc123"
        cfg.telemetry.telegram_bot_token = "tok"
        cfg.telemetry.telegram_chat_id = "999"
        cfg2 = AppConfig.from_dict(asdict(cfg))
        self.assertEqual(cfg2.machine_id, "abc123")
        self.assertEqual(cfg2.telemetry.telegram_bot_token, "tok")
        self.assertEqual(cfg2.telemetry.telegram_chat_id, "999")


if __name__ == "__main__":
    unittest.main()
