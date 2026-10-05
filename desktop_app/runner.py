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

# Runs before any page script: patches all navigator/window signals that
# Cloudflare Turnstile and BotD use to detect Playwright/CDP automation.
#
# Covers:
#   - navigator.webdriver        (the obvious one — but NOT the only one)
#   - window.chrome              (missing entirely in Playwright contexts)
#   - navigator.plugins          (empty array is a bot signal)
#   - navigator.languages        (single-entry array is a bot signal)
#   - navigator.permissions      (Notification query returns wrong state)
#   - navigator.connection       (missing in headless)
#   - window.outerWidth/Height   (0 in headless → Cloudflare checks this)
#   - WebGL vendor/renderer      (headless GPU string is a known bot signal)
#   - Removes Playwright's __pw_ internal markers from window
STEALTH_JS = """
(() => {
    // 1. webdriver — DELETE it. Defining it as undefined still leaves the
    //    property present, and `'webdriver' in navigator` is a bot signal.
    try { delete Object.getPrototypeOf(navigator).webdriver; } catch (e) {}
    try { delete navigator.webdriver; } catch (e) {}

    // 2. window.chrome — missing in Playwright CDP contexts
    if (!window.chrome) {
        window.chrome = {
            app: {isInstalled: false, InstallState: {DISABLED:'a',INSTALLED:'b',NOT_INSTALLED:'c'},
                  RunningState: {CANNOT_RUN:'a',READY_TO_RUN:'b',RUNNING:'c'}},
            runtime: {OnInstalledReason: {CHROME_UPDATE:'a',INSTALL:'b',SHARED_MODULE_UPDATE:'c',UPDATE:'d'},
                      PlatformArch: {ARM:'a',ARM64:'b',MIPS:'c',MIPS64:'d',X86_32:'e',X86_64:'f'},
                      PlatformNaclArch: {ARM:'a',MIPS:'b',MIPS64:'c',X86_32:'d',X86_64:'e'},
                      PlatformOs: {ANDROID:'a',CROS:'b',LINUX:'c',MAC:'d',OPENBSD:'e',WIN:'f'},
                      RequestUpdateCheckStatus: {NO_UPDATE:'a',THROTTLED:'b',UPDATE_AVAILABLE:'c'}},
            csi: function(){}, loadTimes: function(){}
        };
    }

    // 3. plugins — empty = bot; fake a realistic set
    if (navigator.plugins.length === 0) {
        const fakePDF = {0:{type:'application/x-google-chrome-pdf',suffixes:'pdf',description:'Portable Document Format',enabledPlugin:null},
                         description:'Portable Document Format', filename:'internal-pdf-viewer',
                         length:1, name:'Chrome PDF Plugin'};
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const arr = [fakePDF];
                arr.item   = i => arr[i];
                arr.namedItem = n => arr.find(p => p.name === n) || null;
                arr.refresh = () => {};
                return arr;
            }, configurable: true
        });
    }

    // 4. languages — single entry is a strong bot signal
    Object.defineProperty(navigator, 'languages', {
        get: () => ['it-IT', 'it', 'en-US', 'en'], configurable: true
    });

    // 5. Notification permissions — headless returns 'denied' immediately
    const origQuery = window.Notification && Notification.requestPermission;
    if (window.Permissions && window.Permissions.prototype.query) {
        const origPermQuery = Permissions.prototype.query;
        Permissions.prototype.query = function(params) {
            if (params && params.name === 'notifications') {
                return Promise.resolve({state: 'prompt', onchange: null});
            }
            return origPermQuery.call(this, params);
        };
    }

    // 6. window outer dimensions — 0 in headless
    if (window.outerWidth === 0)  Object.defineProperty(window, 'outerWidth',  {get: () => window.innerWidth  || 1000, configurable: true});
    if (window.outerHeight === 0) Object.defineProperty(window, 'outerHeight', {get: () => window.innerHeight || 750,  configurable: true});

    // 7. navigator.connection — missing in headless
    if (!navigator.connection) {
        Object.defineProperty(navigator, 'connection', {
            get: () => ({effectiveType: '4g', downlink: 10, rtt: 50, saveData: false}),
            configurable: true,
        });
    }

    // 8. WebGL — only override if headless GPU renderer is detected.
    // Brave randomises WebGL itself; only patch if we see the headless signature.
    try {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (gl) {
            const ext = gl.getExtension('WEBGL_debug_renderer_info');
            if (ext) {
                const renderer = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) || '';
                const isHeadless = /SwiftShader|llvmpipe|softpipe|ANGLE.*SwiftShader/i.test(renderer);
                if (isHeadless) {
                    const getParam = WebGLRenderingContext.prototype.getParameter;
                    WebGLRenderingContext.prototype.getParameter = function(param) {
                        if (param === 37445) return 'Intel Inc.';
                        if (param === 37446) return 'Intel Iris OpenGL Engine';
                        return getParam.call(this, param);
                    };
                    if (window.WebGL2RenderingContext) {
                        const getParam2 = WebGL2RenderingContext.prototype.getParameter;
                        WebGL2RenderingContext.prototype.getParameter = function(param) {
                            if (param === 37445) return 'Intel Inc.';
                            if (param === 37446) return 'Intel Iris OpenGL Engine';
                            return getParam2.call(this, param);
                        };
                    }
                }
                // If real GPU — leave Brave's own randomisation untouched
            }
        }
    } catch(e) {}

    // 9. Remove Playwright's internal __pw_ markers from window
    const pwKeys = Object.getOwnPropertyNames(window).filter(k => k.startsWith('__pw'));
    pwKeys.forEach(k => { try { delete window[k]; } catch(e) {} });

    // 10. hairline iframe — used by some Cloudflare checks, block detection
    const origCreateElement = document.createElement.bind(document);
    document.createElement = function(tag) {
        const el = origCreateElement(tag);
        if (tag.toLowerCase() === 'iframe') {
            Object.defineProperty(el, 'contentWindow', {
                get: function() { return window; }, configurable: true
            });
        }
        return el;
    };
})();
"""

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
        "--no-first-run",
        "--no-default-browser-check",
        # ── Automation signal removal ──────────────────────────────────────
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",                        # hides "controlled by automation" bar
        # Note: --excludeSwitches and --useAutomationExtension are CDP/DevTools
        # options, not valid CLI flags — they are silently ignored and omitted.
        # ── Realistic browser behaviour ───────────────────────────────────
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=TranslateUI",
        "--no-sandbox",                              # required in PyInstaller/packaged env
        "--disable-dev-shm-usage",
        # ── Window ────────────────────────────────────────────────────────
        "--window-size=1000,750",
        f"--window-position={50 + (idx % 6) * 180},{50 + ((idx // 6) % 4) * 180}",
        f"--lang={lang}",
        "about:blank",
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
    """Launch one Chromium (minimal, human-like argv), connect via CDP, book.

    NOTE: we deliberately launch Brave ourselves instead of using Playwright's
    launch_persistent_context — Playwright injects ~40 automation flags
    (--no-sandbox, --disable-dev-shm-usage, --enable-unsafe-swiftshader,
    --disable-extensions, --use-mock-keychain, …) that make Cloudflare serve the
    "verify you're not a robot" challenge. A bare argv + connect_over_cdp passes.
    """
    import urllib.request
    from playwright.async_api import async_playwright

    label = label or f"T{idx + 1:02d}"
    port = port or (9400 + idx)
    profile_dir = profile_dir or os.path.join(os.path.expanduser("~"), f"vatican_snipe_profile_{idx}")
    browser_path = detect_browser(browser_path)

    log.info(f"[{label}] browser={browser_path} port={port} profile={profile_dir}")
    if not browser_path:
        log.error(f"[{label}] no browser found — install Chrome/Brave/Edge")
        return False

    os.makedirs(profile_dir, exist_ok=True)
    clean_profile_locks(profile_dir)
    if seed_source:
        seed_profile(profile_dir, seed_source)

    cmd = build_chrome_cmd(browser_path, port, profile_dir, idx, proxy=proxy)
    log.info(f"[{label}] launching browser (bare argv)...")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log.info(f"[{label}] browser PID={proc.pid}")

    try:
        await asyncio.sleep(2 + idx * 0.2)
        log.info(f"[{label}] waiting for CDP on port {port}...")
        for _ in range(40):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
                break
            except Exception:
                await asyncio.sleep(0.5)
        else:
            log.error(f"[{label}] CDP never became ready on port {port}")
            return False

        log.info(f"[{label}] CDP ready — connecting...")
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context(
                locale="it-IT", timezone_id="Europe/Rome")

            # Apply stealth on every new page the context creates (covers all
            # navigations, not just the first one).
            await ctx.add_init_script(STEALTH_JS)

            # Also patch any pages that are already open (the about:blank we
            # launched with, and any pre-existing tabs).
            for existing_page in ctx.pages:
                try:
                    await existing_page.add_init_script(STEALTH_JS)
                    # Run immediately in-page too so the current document is patched
                    await existing_page.evaluate(STEALTH_JS)
                except Exception:
                    pass

            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            log.info(f"[{label}] navigating to Vatican")
            return await provider.book(page, target, slot, label,
                                       on_hold=on_hold, on_payment=on_payment)
    except Exception as e:
        log.error(f"[{label}] booking error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
