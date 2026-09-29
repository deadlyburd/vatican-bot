"""Venue-agnostic process runner.

One Chromium process per booking: separate user-data-dir, optional proxy,
optional warm-profile seeding, CDP connection, then the provider's book() flow.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import time
from typing import List, Optional

from .proxies import Proxy

log = logging.getLogger("sniper")

def _browser_candidates() -> List[str]:
    """Platform-specific browser executables, in preference order."""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return [
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    if sys.platform.startswith("linux"):
        return [
            "/usr/bin/brave-browser",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/microsoft-edge",
            os.path.join(home, "Applications/BraveSoftware/Brave-Browser/brave"),
        ]
    if sys.platform == "win32":
        local = os.getenv("LOCALAPPDATA", "")
        progfiles = os.getenv("PROGRAMFILES", "C:\\Program Files")
        progfiles_x86 = os.getenv("PROGRAMFILES(X86)", "C:\\Program Files (x86)")
        return [
            os.path.join(local, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(progfiles, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(progfiles_x86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(progfiles, "Google", "Chrome", "Application", "chrome.exe"),
        ]
    return []


DEFAULT_BROWSERS = _browser_candidates()

REAL_COOKIE_FILES = [
    "Cookies", "Local Storage", "Session Storage", "Preferences",
    "Secure Preferences", "History", "Network",
]


def detect_browser(explicit: str = "") -> str:
    """Return a browser executable path (explicit override, else auto-detect)."""
    if explicit and os.path.exists(explicit):
        return explicit
    for p in DEFAULT_BROWSERS:
        if os.path.exists(p):
            return p
    return explicit or ""


def default_source_profile() -> str:
    """Return the real browser's Default dir to seed cookies/fingerprint from."""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        candidates = [
            os.path.join(home, "Library/Application Support/BraveSoftware/Brave-Browser/Default"),
            os.path.join(home, "Library/Application Support/Google/Chrome/Default"),
        ]
    elif sys.platform.startswith("linux"):
        candidates = [
            os.path.join(home, ".config/BraveSoftware/Brave-Browser/Default"),
            os.path.join(home, ".config/google-chrome/Default"),
        ]
    elif sys.platform == "win32":
        local = os.getenv("LOCALAPPDATA", "")
        candidates = [
            os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data", "Default"),
            os.path.join(local, "Google", "Chrome", "User Data", "Default"),
        ]
    else:
        candidates = []
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    return ""


def build_chrome_cmd(
    browser_path: str,
    port: int,
    profile_dir: str,
    idx: int,
    proxy: Optional[Proxy] = None,
    lang: str = "it-IT",
) -> List[str]:
    """Build the Chromium launch argv for one booking process. Pure + testable."""
    cmd = [
        browser_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run", "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox", "--disable-dev-shm-usage",
        "--window-size=1000,750",
        f"--window-position={50 + (idx % 5) * 210},{50 + (idx // 5) * 400}",
        f"--lang={lang}", "about:blank",
    ]
    if proxy is not None:
        flag = proxy.chrome_flag()
        if flag:                      # auth proxies → None (Chrome CLI can't auth)
            cmd.insert(1, flag)
    return cmd


def clean_profile_locks(profile_dir: str) -> None:
    for lf in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        p = os.path.join(profile_dir, lf)
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def seed_profile(dest: str, source_default: str) -> str:
    """Copy a warm profile's cookie/fingerprint files into a fresh profile dir."""
    os.makedirs(os.path.join(dest, "Default"), exist_ok=True)
    if not source_default or not os.path.isdir(source_default):
        return "no-src"
    copied = []
    for name in REAL_COOKIE_FILES:
        src = os.path.join(source_default, name)
        dst = os.path.join(dest, "Default", name)
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            elif os.path.isfile(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
            copied.append(name)
        except Exception:
            pass
    return ",".join(copied)


async def run_booking(
    provider,
    target,
    slot,
    idx: int,
    *,
    proxy: Optional[Proxy] = None,
    browser_path: str = "",
    port: Optional[int] = None,
    profile_dir: Optional[str] = None,
    seed_source: str = "",
    label: Optional[str] = None,
    on_hold=None,
    on_payment=None,
) -> bool:
    """Launch one Chromium, connect, run provider.book(). Returns True on hold."""
    from playwright.async_api import async_playwright

    label = label or f"T{idx + 1:02d}"
    profile_dir = profile_dir or os.path.join(os.path.expanduser("~"), f"vatican_snipe_profile_{idx}")
    browser_path = detect_browser(browser_path)

    log.info(f"[{label}] browser={browser_path} profile={profile_dir}")
    if not browser_path:
        log.error(f"[{label}] no browser found — install Chrome/Brave/Edge")
        return False

    os.makedirs(profile_dir, exist_ok=True)
    clean_profile_locks(profile_dir)
    if seed_source:
        seed_profile(profile_dir, seed_source)

    launch_kwargs = dict(
        user_data_dir=profile_dir,
        executable_path=browser_path,
        headless=False,
        args=[
            "--no-first-run", "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox", "--disable-dev-shm-usage",
            "--window-size=1000,750",
        ],
        locale="it-IT",
        timezone_id="Europe/Rome",
        viewport=None,
    )
    if proxy is not None:
        launch_kwargs["proxy"] = proxy.playwright_proxy()

    try:
        async with async_playwright() as p:
            log.info(f"[{label}] launching browser via Playwright...")
            context = await p.chromium.launch_persistent_context(**launch_kwargs)
            log.info(f"[{label}] browser launched — opening page")
            page = context.pages[0] if context.pages else await context.new_page()
            log.info(f"[{label}] navigating to Vatican")
            return await provider.book(page, target, slot, label,
                                       on_hold=on_hold, on_payment=on_payment)
    except Exception as e:
        log.error(f"[{label}] booking error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
