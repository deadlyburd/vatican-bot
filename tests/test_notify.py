"""Tests for cross-platform notifications + browser detection."""
from __future__ import annotations

import unittest
from unittest import mock

from desktop_app.notify import build_command, notify
from desktop_app.runner import DEFAULT_BROWSERS, _browser_candidates


class TestBuildCommand(unittest.TestCase):
    def test_macos(self):
        cmd = build_command("Title", "Hello", platform="darwin")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd[0], "osascript")
        joined = " ".join(cmd)
        self.assertIn("display notification", joined)
        self.assertIn("Hello", joined)

    def test_linux_present(self):
        with mock.patch("desktop_app.notify.shutil.which", return_value="/usr/bin/notify-send"):
            cmd = build_command("Title", "Hello", platform="linux")
        self.assertEqual(cmd, ["notify-send", "Title", "Hello"])

    def test_linux_missing(self):
        with mock.patch("desktop_app.notify.shutil.which", return_value=None):
            cmd = build_command("Title", "Hello", platform="linux")
        self.assertIsNone(cmd)

    def test_windows(self):
        cmd = build_command("Title", "Hello", platform="win32")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd[0], "powershell")
        self.assertIn("CreateToastNotifier", cmd[-1])

    def test_unknown_platform(self):
        self.assertIsNone(build_command("T", "M", platform="haiku"))


class TestNotify(unittest.TestCase):
    def test_notify_unknown_platform_returns_false(self):
        self.assertFalse(notify("T", "M", platform="haiku"))

    def test_notify_macos_spawns(self):
        with mock.patch("desktop_app.notify.subprocess.Popen") as popen:
            self.assertTrue(notify("T", "M", platform="darwin"))
            popen.assert_called_once()


class TestBrowserCandidates(unittest.TestCase):
    def test_default_browsers_is_nonempty(self):
        self.assertIsInstance(DEFAULT_BROWSERS, list)
        self.assertGreater(len(DEFAULT_BROWSERS), 0)
        for p in DEFAULT_BROWSERS:
            self.assertIsInstance(p, str)

    def test_platform_lists_are_wellformed(self):
        # exercise each branch by faking sys.platform
        for platform, prefix in [("darwin", "/Applications"), ("linux", "/usr/bin"),
                                 ("win32", "brave.exe")]:
            with mock.patch("desktop_app.runner.sys.platform", platform):
                cands = _browser_candidates()
            self.assertIsInstance(cands, list)
            self.assertGreater(len(cands), 0)
            self.assertTrue(any(prefix in c for c in cands),
                            f"{platform} candidates should contain '{prefix}'")


if __name__ == "__main__":
    unittest.main()
