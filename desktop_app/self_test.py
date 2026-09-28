"""Self-test for the packaged app.

Verifies the bundled Playwright node driver can talk CDP to a real browser,
which is the main thing that can silently break under PyInstaller.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import urllib.request

from .runner import build_chrome_cmd, detect_browser


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

    port = 9500
    profile = tempfile.mkdtemp(prefix="vatican_selftest_")
    cmd = build_chrome_cmd(browser, port, profile, 0)
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(30):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            _log("SELF-TEST FAIL: CDP endpoint not reachable")
            return False

        with sync_playwright() as p:
            b = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = b.contexts[0] if b.contexts else b.new_context()
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("about:blank")
            _log("SELF-TEST OK: playwright driver + CDP + browser all working")
            return True
    except Exception as e:  # noqa: BLE001
        _log(f"SELF-TEST FAIL: {e}")
        return False
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
