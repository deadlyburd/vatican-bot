"""Tests for first-run bootstrap."""
from __future__ import annotations

import os
import tempfile
import unittest

from desktop_app.bootstrap import _auto_fill, ensure_config
from desktop_app.config import AppConfig, load_config


class TestAutoFill(unittest.TestCase):
    def test_returns_bool_and_fills_browser(self):
        cfg = AppConfig()
        changed = _auto_fill(cfg)
        # On a machine with a browser installed this fills path/source_profile.
        # We only assert it returns a bool and doesn't crash.
        self.assertIsInstance(changed, bool)


class TestEnsureConfig(unittest.TestCase):
    def test_creates_config_on_first_run(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            self.assertFalse(os.path.exists(path))
            cfg = ensure_config(path)
            self.assertTrue(os.path.exists(path))
            self.assertIsInstance(cfg, AppConfig)
            reloaded = load_config(path)
            self.assertEqual(reloaded.version, cfg.version)

    def test_does_not_clobber_existing(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            cfg = AppConfig()
            cfg.browser.path = "/custom/browser"
            from desktop_app.config import save_config
            save_config(cfg, path)
            out = ensure_config(path)
            self.assertEqual(out.browser.path, "/custom/browser")


if __name__ == "__main__":
    unittest.main()
