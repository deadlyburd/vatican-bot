#!/usr/bin/env python3
"""
Live guided tour booking flow test.
Opens Brave, navigates to Dec 1 Italian guided tour, selects language,
sets quantity to 2, picks the first available time, and stops just before PROCEDI.
Watch the browser — you'll see every step happen automatically.

Run with:
    .venv/bin/python test_guided_live.py
"""
import asyncio
import subprocess
import urllib.request
import os
import sys
import time

from datetime import datetime
from zoneinfo import ZoneInfo

BRAVE_PATH = (
    os.path.join(os.getenv("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
    if sys.platform == "win32"
    else "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
)
PORT        = 9500
PROFILE_DIR = os.path.join(os.path.expanduser("~"), "vatican_test_profile_9500")
VATICAN_URL = "https://tickets.museivaticani.va/home/visit/2/1796079600000/1"  # Dec 1 2026

# ── Stealth script (same as runner.py) ───────────────────────────────────────
STEALTH_JS = """
(() => {
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined, configurable: true});
    if (!window.chrome) {
        window.chrome = { app:{isInstalled:false}, runtime:{}, csi:function(){}, loadTimes:function(){} };
    }
    if (navigator.plugins.length === 0) {
        Object.defineProperty(navigator, 'plugins', {
            get: () => { const a=[{description:'PDF',filename:'internal-pdf-viewer',length:1,name:'Chrome PDF Plugin'}];
                         a.item=i=>a[i]; a.namedItem=n=>null; a.refresh=()=>{}; return a; },
            configurable: true });
    }
    Object.defineProperty(navigator, 'languages', {get: () => ['it-IT','it','en-US','en'], configurable:true});
    if (window.outerWidth===0) Object.defineProperty(window,'outerWidth',{get:()=>window.innerWidth||1000,configurable:true});
    if (window.outerHeight===0) Object.defineProperty(window,'outerHeight',{get:()=>window.innerHeight||750,configurable:true});
    const pwKeys = Object.getOwnPropertyNames(window).filter(k=>k.startsWith('__pw'));
    pwKeys.forEach(k=>{try{delete window[k];}catch(e){}});
})();
"""

async def run():
    from playwright.async_api import async_playwright

    # ── Launch Brave ─────────────────────────────────────────────────────────
    os.makedirs(PROFILE_DIR, exist_ok=True)
    for lock in ["SingletonLock","SingletonCookie","SingletonSocket"]:
        p = os.path.join(PROFILE_DIR, lock)
        if os.path.exists(p):
            os.remove(p)

    cmd = [
        BRAVE_PATH,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run", "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--window-size=1100,820",
        "--window-position=100,50",
        "about:blank",
    ]
    print(f"[1] Launching Brave on port {PORT}...")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"    PID={proc.pid}")

    # Wait for CDP
    for i in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
            print(f"[2] CDP ready (after {i * 0.5:.1f}s)")
            break
        except Exception:
            await asyncio.sleep(0.5)
    else:
        print("❌ CDP never became ready")
        proc.terminate()
        return

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context(
            locale="it-IT", timezone_id="Europe/Rome")
        await ctx.add_init_script(STEALTH_JS)

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # Patch the already-open about:blank
        try:
            await page.evaluate(STEALTH_JS)
        except Exception:
            pass

        # ── [1] Navigate ─────────────────────────────────────────────────────
        print(f"[3] Navigating to {VATICAN_URL}")
        await page.goto(VATICAN_URL, wait_until="domcontentloaded", timeout=30000)
        print("    Page loaded — waiting for ticket buttons...")
        await page.wait_for_timeout(3000)

        # ── [2] Wait for ticket buttons ───────────────────────────────────────
        for attempt in range(20):
            count = await page.evaluate(
                "document.querySelectorAll(\"[data-cy^='bookTicket_']\").length")
            if count and int(count) > 0:
                print(f"    ✅ {count} ticket button(s) found")
                break
            await page.wait_for_timeout(500)
        else:
            print("❌ No ticket buttons appeared — check browser manually")
            input("Press Enter to close...")
            proc.terminate()
            return

        # ── [3] Click the guided tour ticket by name ─────────────────────
        print("[4] Clicking guided tour ticket by name...")
        result = await page.evaluate("""
            (() => {
                function cardName(card) {
                    const t = card.querySelector('.muvaTicketTitle, [data-cy="ticketName"], h2.visitName');
                    return (t ? t.innerText : card.innerText).toLowerCase().trim();
                }
                for (const card of document.querySelectorAll("[id^='ticket_']")) {
                    const btn = card.querySelector("[data-cy^='bookTicket_']");
                    if (!btn) continue;
                    const name = cardName(card);
                    const isGuided = name.includes('visita') || name.includes('guidat') ||
                                     name.includes('guided') || name.includes('singoli');
                    if (isGuided) {
                        btn.scrollIntoView({block:'center'}); btn.click();
                        return 'clicked-guided: ' + name.slice(0,60);
                    }
                }
                return 'no-guided-ticket-found';
            })()
        """)
        print(f"    result: {result}")
        await page.wait_for_timeout(1500)

        # ── [4] Language = Italian ────────────────────────────────────────────
        print("[5] Selecting language (Italian = position 4)...")
        lang_visible = await page.evaluate(
            "!!document.querySelector(\"[data-cy='visitLang']\")")
        if lang_visible:
            await page.click("[data-cy='visitLang']")
            await page.wait_for_timeout(700)

            # Show what options are available
            options = await page.evaluate("""
                (() => {
                    const items = document.querySelectorAll(
                        'app-ticket-visit-language app-dropdown article section > div, '
                        + 'app-ticket-visit-language [data-cy="visitLangSection"]'
                    );
                    return Array.from(items).map((el, i) => i + ': ' + el.innerText.trim());
                })()
            """)
            print(f"    Language options: {options}")

            # Click Italian (index 3 = 4th item)
            clicked = await page.evaluate("""
                (() => {
                    const items = document.querySelectorAll(
                        'app-ticket-visit-language app-dropdown article section > div, '
                        + 'app-ticket-visit-language [data-cy="visitLangSection"]'
                    );
                    // Try to find 'Italiano' by text first
                    for (const [i, el] of [...items].entries()) {
                        if (/italian|ital/i.test(el.innerText || '')) {
                            el.click(); return 'text-match:' + i + ':' + el.innerText.trim();
                        }
                    }
                    // Fallback: position 4 (index 3)
                    const idx = Math.min(3, items.length - 1);
                    if (items[idx]) { items[idx].click(); return 'pos:' + idx; }
                    return 'none';
                })()
            """)
            print(f"    Language selected: {clicked}")
            await page.wait_for_timeout(800)
        else:
            print("    [data-cy='visitLang'] not visible — may be standard ticket or already set")

        # ── [5] Quantity = 2 ──────────────────────────────────────────────────
        print("[6] Setting quantity to 2...")
        qty_visible = await page.evaluate(
            "!!document.querySelector(\"[data-cy='ticketQuantity']\")")
        if qty_visible:
            await page.evaluate("document.querySelector(\"[data-cy='ticketQuantity']\").click()")
            await page.wait_for_timeout(500)

            qty_result = await page.evaluate("""
                (() => {
                    const sections = document.querySelectorAll("[data-cy='ticketQuantitySection']");
                    for (const s of sections) {
                        if (s.innerText.trim() === '2') { s.click(); return 'exact:2'; }
                    }
                    if (sections[1]) { sections[1].click(); return 'idx:1'; }
                    return 'none';
                })()
            """)
            print(f"    Qty result: {qty_result}")
        await page.wait_for_timeout(1500)

        # ── [6] Show available times ──────────────────────────────────────────
        await page.wait_for_timeout(1000)
        times = await page.evaluate("""
            (() => {
                return Array.from(document.querySelectorAll("[data-cy='time']"))
                    .map(el => el.innerText.trim().split('\\n')[0])
                    .filter(t => t && !t.includes('ESAURITI'));
            })()
        """)
        print(f"[7] Available times: {times}")

        if times:
            # Click first available time
            print(f"    Clicking first time: {times[0]}")
            await page.evaluate("""
                (() => {
                    const cells = document.querySelectorAll("[data-cy='time']");
                    for (const cell of cells) {
                        const txt = cell.innerText || '';
                        if (!txt.includes('ESAURITI') && !txt.includes('SOLD') && txt.trim()) {
                            cell.scrollIntoView({behavior:'smooth', block:'center'});
                            cell.click();
                            return;
                        }
                    }
                })()
            """)
            await page.wait_for_timeout(1500)
            print("    ✅ Time clicked — PROCEDI button should now be active")
            print("")
            print("=" * 55)
            print("  Flow complete up to PROCEDI. Check Brave now.")
            print("  The bot stops here — you can manually click PROCEDI")
            print("  to verify the checkout flow works.")
            print("=" * 55)
        else:
            print("    ⚠️  No available times found on page — check browser")

        # Keep the browser open for inspection
        print("\nBrave stays open. Press Ctrl+C or close this terminal when done.")
        try:
            while True:
                await asyncio.sleep(5)
                cur_url = page.url
                print(f"  page: {cur_url[:80]}")
        except KeyboardInterrupt:
            pass

    proc.terminate()
    print("Done.")

if __name__ == "__main__":
    asyncio.run(run())
