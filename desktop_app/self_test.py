"""Self-test for the packaged app.

Verifies the bundled Playwright node driver can talk CDP to a real browser,
which is the main thing that can silently break under PyInstaller.
"""
from __future__ import annotations

import os
import tempfile

from .runner import detect_browser


def _log(msg: str) -> None:
    """Write to the result file (always) and stdout (if available)."""
    try:
        from .config import _app_data_dir
        d = _app_data_dir()
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "self_test_result.txt"), "w") as f:
            f.write(msg + "\n")
    except Exception:
        pass
    try:
        print(msg, flush=True)
    except Exception:
        pass


def run_self_test() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        _log(f"SELF-TEST FAIL: playwright import error: {e}")
        return False

    browser = detect_browser()
    if not browser:
        _log("SELF-TEST FAIL: no browser detected")
        return False

    profile = tempfile.mkdtemp(prefix="vatican_selftest_")
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=profile,
                executable_path=browser,
                headless=False,
                args=["--no-first-run", "--no-default-browser-check", "--no-sandbox"],
                viewport=None,
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("about:blank")
            _log("SELF-TEST OK: playwright driver + CDP + browser all working")
            ctx.close()
            return True
    except Exception as e:  # noqa: BLE001
        _log(f"SELF-TEST FAIL: {e}")
        return False
