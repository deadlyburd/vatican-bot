#!/usr/bin/env python3
"""
CDP BOOKER — Backend drives Chrome directly via DevTools Protocol
==================================================================
1. SlotFinder finds available slots via API (search + timeavail)
2. CDP connects to Chrome, navigates to Vatican URL
3. Injects JavaScript to click through: ticket → time → PROCEDI → form → ACQUISTA
4. Monitors for ePay URL
5. Reports results → sheet + Telegram

No extension needed. Backend has direct Chrome control via WebSocket.
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime, date
from typing import Optional, Dict, List

import websockets
import urllib.request

from slot_finder import SlotFinder

logger = logging.getLogger(__name__)

# Chrome debug port (configured per container)
CDP_HOST = "chrome_bot_1"
CDP_PORT = 9222
CDP_BASE = f"http://{CDP_HOST}:{CDP_PORT}"

# ── Booking JS (injected into Vatican page) ──────────────────────────
# This is the same flow as the extension content.js, but injected via CDP
BOOKING_JS = r"""
(async function vaticanAutoBook() {
    'use strict';
    const LOG = [];
    function log(m) { LOG.push('[' + new Date().toISOString().substr(11,8) + '] ' + m); console.log('[VAB] ' + m); }
    function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

    const B = __BOOKING__;
    let result = { success: false, steps: [], epayUrl: null, error: null };

    try {
        log('Starting auto-booking: ' + B.date + ' | ' + B.visitors + 'v');
        result.steps.push('start');

        // Navigate to ticket page if not already there
        if (!window.location.href.includes('/home/fromtag')) {
            log('Navigating to: ' + B.targetUrl);
            window.location.href = B.targetUrl;
            return { status: 'navigating', targetUrl: B.targetUrl };
        }

        // Step 1: Wait for ticket buttons and click
        log('Waiting for ticket buttons...');
        let ticketFound = false;
        for (let i = 0; i < 30; i++) {
            const buttons = document.querySelectorAll("[data-cy^='bookTicket']");
            for (const btn of buttons) {
                if (btn.disabled || btn.textContent.trim() !== 'PRENOTA') continue;
                const card = btn.closest('[class*="card"], [class*="ticket"]');
                let name = '';
                if (card) {
                    const n = card.querySelector('h3, h4, [class*="title"]');
                    if (n) name = n.textContent.trim().toLowerCase();
                }
                const isVatican = name.includes('musei') || name.includes('vatican');
                const isEntry = name.includes('ingresso') || name.includes('biglietti');
                if (isVatican && isEntry) {
                    btn.scrollIntoView({behavior:'smooth',block:'center'});
                    await sleep(800);
                    btn.click();
                    log('Clicked Vatican ticket: ' + name);
                    ticketFound = true;
                    break;
                }
            }
            if (ticketFound) break;
            await sleep(1000);
        }
        if (!ticketFound) {
            // Fallback: first PRENOTA
            const btns = document.querySelectorAll("[data-cy^='bookTicket']");
            for (const b of btns) {
                if (!b.disabled && b.textContent.trim() === 'PRENOTA') {
                    b.click();
                    log('Clicked first PRENOTA (fallback)');
                    ticketFound = true;
                    break;
                }
            }
        }
        if (!ticketFound) { result.error = 'No ticket button found'; return result; }
        result.steps.push('ticket_clicked');
        await sleep(3000); // Wait for Angular to render time slots

        // Step 2: Select time slot
        log('Looking for time slots...');
        let timeSlots = [];
        for (let i = 0; i < 30; i++) {
            const containers = document.querySelectorAll("[data-cy='time']");
            for (const c of containers) {
                const divs = c.querySelectorAll('div');
                for (const d of divs) {
                    const txt = d.textContent.trim();
                    if (/^\d{1,2}:\d{2}$/.test(txt) && d.offsetParent !== null) {
                        const disabled = d.classList.contains('disabled');
                        if (!disabled) timeSlots.push({el: d, time: txt});
                    }
                }
            }
            if (timeSlots.length > 0) break;
            await sleep(500);
        }

        if (timeSlots.length === 0) {
            // Fallback: any element with time pattern
            const all = document.querySelectorAll('div, span, button');
            for (const el of all) {
                const txt = el.textContent.trim();
                if (/^\d{1,2}:\d{2}$/.test(txt) && el.offsetParent !== null && el.children.length === 0) {
                    timeSlots.push({el: el, time: txt});
                }
            }
        }
        log('Found ' + timeSlots.length + ' time slots: ' + timeSlots.map(s=>s.time).join(', '));

        if (timeSlots.length === 0) { result.error = 'No time slots'; return result; }

        // Pick slot: preferred time > afternoon > first
        let target = null;
        if (B.time) target = timeSlots.find(s => s.time === B.time);
        if (!target) target = timeSlots.find(s => {const h=parseInt(s.time.split(':')[0]); return h>=12 && h<=16;});
        if (!target) target = timeSlots[0];
        log('Selected: ' + target.time);

        target.el.scrollIntoView({behavior:'smooth',block:'center'});
        await sleep(400);
        target.el.click();
        await sleep(300);
        target.el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
        result.steps.push('time_selected:' + target.time);
        await sleep(1500);

        // Step 3: Click PROCEDI
        const procedi = document.querySelector("[data-cy='bookVisit']");
        if (!procedi) { result.error = 'PROCEDI not found'; return result; }
        procedi.scrollIntoView({behavior:'smooth',block:'center'});
        await sleep(500);
        procedi.click();
        log('PROCEDI clicked');
        result.steps.push('procedi_clicked');
        await sleep(5000);

        // Handle recap page
        if (window.location.href.includes('recap')) {
            log('On recap page, PROCEDI again...');
            await sleep(2000);
            const p2 = document.querySelector("[data-cy='bookVisit']");
            if (p2) { p2.click(); await sleep(5000); }
        }
        result.steps.push('checkout_page');

        // Step 4: Fill form
        await sleep(3000);
        log('Filling form...');
        let filled = 0;

        function fill(sel, val) {
            const el = document.querySelector(sel);
            if (!el || !val) return false;
            el.focus(); el.value = val;
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
            el.dispatchEvent(new Event('blur', {bubbles:true}));
            return true;
        }

        const P = B.profile || {};
        if (fill("[data-cy='managerSurname']", P.last_name || P.lastName)) filled++;
        await sleep(200);
        if (fill("[data-cy='managerName']", P.first_name || P.firstName)) filled++;
        await sleep(200);
        if (fill("[data-cy='managerEmail']", P.email)) filled++;
        await sleep(200);
        if (fill("[data-cy='managerConfirmEmail']", P.email)) filled++;
        await sleep(200);
        if (fill("[data-cy='managerPhone']", (P.phone||'').replace(/[+ ]/g,''))) filled++;
        await sleep(200);
        if (fill("[data-cy='managerCity']", P.city || 'ROMA')) filled++;
        await sleep(300);

        // Country
        const ctry = document.querySelector("[data-cy='managerCountry']");
        if (ctry) {
            ctry.click(); await sleep(500);
            const search = document.querySelector('#searchInput_country');
            if (search) { search.value = 'Italia'; search.dispatchEvent(new Event('input',{bubbles:true})); await sleep(400); }
            const opts = document.querySelectorAll("[data-cy='managerCountrySection'] div, [data-cy='managerCountrySection'] span");
            for (const o of opts) { if (o.textContent.trim().toLowerCase().startsWith('ital')) { o.click(); filled++; break; } }
            await sleep(300);
        }

        // Gender
        const sex = document.querySelector("[data-cy='managerSex']");
        if (sex) { sex.click(); await sleep(300);
            const opts = document.querySelectorAll("[data-cy='managerSexSection'] div, [data-cy='managerSexSection'] span");
            for (const o of opts) { if (o.textContent.trim().toUpperCase().startsWith('M')) { o.click(); filled++; break; } }
            await sleep(300);
        }

        // Participants
        const participants = B.participants || [];
        const visitors = B.visitors || 1;
        for (let i = 0; i < visitors; i++) {
            const p = participants[i] || participants[0] || {};
            if (i > 0) {
                const expand = document.querySelector('#participantElement_' + i + ' div.tw-flex-grow > div');
                if (expand) { expand.click(); await sleep(400); }
            }
            if (fill('#participantSurname_' + i, p.last_name || p.lastName || 'Cognome'+(i+1))) filled++;
            await sleep(200);
            if (fill('#participantName_' + i, p.first_name || p.firstName || 'Nome'+(i+1))) filled++;
            await sleep(200);
        }
        log('Filled ' + filled + ' fields');
        result.steps.push('form_filled:' + filled);

        // GDPR checkboxes
        const cb1 = document.querySelector('#mat-mdc-checkbox-1-input');
        if (cb1 && !cb1.checked) { cb1.click(); await sleep(1500);
            const close = document.querySelector("[data-cy='purchase-rules-close-btn']");
            if (close) { close.click(); await sleep(800); }
        }
        const cb2 = document.querySelector('#mat-mdc-checkbox-4-input');
        if (cb2 && !cb2.checked) { cb2.click(); await sleep(500); }
        // Fallback checkboxes
        const allCbs = document.querySelectorAll('input[type="checkbox"]:not(:checked)');
        for (const cb of allCbs) { if (cb.offsetParent) { cb.click(); await sleep(300); } }
        result.steps.push('gdpr_done');

        // Step 5: Wait for Turnstile
        log('Waiting for Turnstile...');
        for (let i = 0; i < 60; i++) {
            const buy = document.querySelector("[data-cy='buyButton']");
            if (buy && !buy.disabled && buy.offsetParent) { log('Turnstile solved!'); break; }
            await sleep(500);
        }
        result.steps.push('turnstile_ready');

        // Step 6: Click ACQUISTA
        log('Clicking ACQUISTA...');
        for (let i = 0; i < 30; i++) {
            const buy = document.querySelector("[data-cy='buyButton']");
            if (buy && !buy.disabled && buy.offsetParent) {
                buy.scrollIntoView({behavior:'smooth',block:'center'});
                await sleep(1000);
                buy.click();
                log('ACQUISTA CLICKED!');
                result.steps.push('acquista_clicked');
                await sleep(3000);
                break;
            }
            // Alt: text match
            const alt = Array.from(document.querySelectorAll('button')).find(b => /ACQUISTA/i.test(b.textContent) && !b.disabled);
            if (alt) { alt.click(); log('ACQUISTA via alt'); result.steps.push('acquista_clicked'); await sleep(3000); break; }
            await sleep(1000);
        }

        // Step 7: Capture ePay
        for (let i = 0; i < 60; i++) {
            const url = window.location.href;
            if (url.includes('epay.catholica.va') || url.includes('/payment') || url.includes('grazie')) {
                result.epayUrl = url;
                result.success = true;
                result.steps.push('epay_captured');
                log('SUCCESS: ' + url.substring(0, 120));
                return result;
            }
            await sleep(500);
        }
        result.steps.push('epay_timeout');
        result.error = 'ePay URL not captured';
        if (window.location.href.includes('epay')) {
            result.epayUrl = window.location.href;
            result.success = true;
        }
        return result;

    } catch (err) {
        log('ERROR: ' + err.message);
        result.error = err.message;
        return result;
    }
})();
"""


class CdpBooker:
    """Drives Chrome via CDP to book Vatican tickets."""

    def __init__(self, cdp_host: str = CDP_HOST, cdp_port: int = CDP_PORT):
        self.cdp_base = f"http://{cdp_host}:{cdp_port}"
        self.ws_url: Optional[str] = None
        self.tab_id: Optional[str] = None
        self.messages: List[str] = []

    # ── Connection ──────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Connect to Chrome and get the active tab."""
        try:
            resp = urllib.request.urlopen(f"{self.cdp_base}/json", timeout=10)
            tabs = json.loads(resp.read())
            tab = next((t for t in tabs if t.get("type") == "page"), None)
            if not tab:
                logger.error("No page tab found in Chrome")
                return False

            self.tab_id = tab["id"]
            self.ws_url = tab["webSocketDebuggerUrl"]
            logger.info(f"Connected to tab {self.tab_id}: {tab.get('url', '')[:80]}")
            return True
        except Exception as e:
            logger.error(f"CDP connect error: {e}")
            return False

    # ── Book ────────────────────────────────────────────────────────

    async def book(self, booking: dict) -> dict:
        """
        Execute a full booking via CDP.

        Args:
            booking: {
                "date": "28/07/2026",
                "time": "10:00",  # optional
                "visitors": 2,
                "profile": {first_name, last_name, email, phone, city},
                "participants": [{first_name, last_name}, ...],
            }

        Returns:
            {"success": bool, "epayUrl": str, "steps": [...], "error": str}
        """
        if not self.ws_url:
            if not await self.connect():
                return {"success": False, "error": "CDP connection failed"}

        # Build target URL
        target_url = self._build_url(booking)

        try:
            async with websockets.connect(self.ws_url, max_size=2**24) as ws:
                # Enable runtime + console
                await ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
                await ws.recv()
                await ws.send(json.dumps({"id": 2, "method": "Page.enable"}))
                await ws.recv()
                await ws.send(json.dumps({"id": 3, "method": "Console.enable"}))
                await ws.recv()

                # Navigate to target URL
                logger.info(f"Navigating to: {target_url}")
                await ws.send(json.dumps({
                    "id": 4, "method": "Page.navigate",
                    "params": {"url": target_url}
                }))
                await asyncio.wait_for(ws.recv(), timeout=15)
                await asyncio.sleep(8)  # Wait for page + Angular to load

                # Inject booking JavaScript
                js = BOOKING_JS.replace("__BOOKING__", json.dumps({
                    **booking,
                    "targetUrl": target_url,
                }))

                logger.info("Injecting booking script...")
                await ws.send(json.dumps({
                    "id": 10, "method": "Runtime.evaluate",
                    "params": {
                        "expression": js,
                        "returnByValue": True,
                        "awaitPromise": True,
                    }
                }))

                # Wait for result with monitoring
                start = time.time()
                result = None

                while time.time() - start < 120:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=2)
                        data = json.loads(msg)

                        # Check for console logs
                        if data.get("method") == "Runtime.consoleAPICalled":
                            for arg in data.get("params", {}).get("args", []):
                                val = str(arg.get("value", ""))
                                if "[VAB]" in val:
                                    logger.info(val.replace("[VAB] ", ""))
                                    self.messages.append(val)

                        # Check for evaluation result
                        if data.get("id") == 10:
                            r = data.get("result", {}).get("result", {})
                            val = r.get("value")
                            if isinstance(val, dict):
                                result = val
                            elif isinstance(val, str):
                                try:
                                    result = json.loads(val)
                                except json.JSONDecodeError:
                                    pass

                            if result:
                                logger.info(f"Booking result: success={result.get('success')} | {result.get('epayUrl', '')[:80]}")
                                break

                        # Check navigation events
                        if data.get("method") == "Page.frameNavigated":
                            url = data.get("params", {}).get("frame", {}).get("url", "")
                            if "epay" in url:
                                logger.info(f"ePay detected: {url[:120]}")
                                if not result:
                                    result = {"success": True, "epayUrl": url, "steps": ["epay_detected"]}

                    except asyncio.TimeoutError:
                        pass
                    except Exception as e:
                        logger.warning(f"WS message error: {e}")

                if not result:
                    # Final check - evaluate current URL
                    await ws.send(json.dumps({
                        "id": 99, "method": "Runtime.evaluate",
                        "params": {
                            "expression": "JSON.stringify({url: window.location.href, result: window.__vabResult})",
                            "returnByValue": True,
                        }
                    }))
                    try:
                        final = await asyncio.wait_for(ws.recv(), timeout=10)
                        final_data = json.loads(final)
                        final_val = final_data.get("result", {}).get("result", {}).get("value", "{}")
                        try:
                            result = json.loads(final_val)
                        except Exception:
                            result = {"success": False, "error": "No result captured"}
                    except Exception:
                        result = {"success": False, "error": "Final check failed"}

                duration = time.time() - start
                if result:
                    result["duration"] = round(duration, 1)
                logger.info(f"Booking attempt completed in {duration:.1f}s")
                return result or {"success": False, "error": "No response"}

        except Exception as e:
            logger.error(f"CDP booking error: {e}")
            return {"success": False, "error": str(e)}

    # ── URL Builder ──────────────────────────────────────────────────

    @staticmethod
    def _build_url(booking: dict) -> str:
        from datetime import date as date_cls
        date_str = booking["date"]  # DD/MM/YYYY
        visitors = booking.get("visitors", 2)
        day, month, year = date_str.split("/")
        ts = int(date_cls(int(year), int(month), int(day)).strftime("%s")) * 1000
        # Adjust for Rome timezone (UTC+2 summer)
        ts = ts + (2 * 3600 * 1000)
        category = "MV-Biglietti"
        return f"https://tickets.museivaticani.va/home/fromtag/{visitors}/{ts}/{category}/1"


# ── Snipe Function ───────────────────────────────────────────────────

async def snipe_and_book(
    date_str: str,
    visitors: int = 2,
    preferred_time: str = None,
    cdp_host: str = CDP_HOST,
    cdp_port: int = CDP_PORT,
) -> dict:
    """
    Full snipe pipeline:
    1. Find slots via API
    2. Book via CDP

    Returns result dict with success, epayUrl, steps, error
    """
    # Step 1: Find available slots
    logger.info(f"🔍 Finding slots for {date_str}...")
    finder = SlotFinder()
    slots = finder.find_slots(date_str, visitors, use_cache=False)

    if not slots:
        logger.info(f"No slots available for {date_str}")
        return {"success": False, "error": "No available slots", "slots_found": 0}

    slot = slots[0]
    if preferred_time:
        match = next((s for s in slots if s.time == preferred_time), None)
        if match:
            slot = match

    logger.info(f"🎯 Booking: {date_str} at {slot.time} — {visitors}v")

    # Step 2: Book via CDP
    booker = CdpBooker(cdp_host, cdp_port)
    result = await booker.book({
        "date": date_str,
        "time": slot.time,
        "visitors": visitors,
        "profile": {
            "first_name": "Marco",
            "last_name": "Rossi",
            "email": "marco.rossi@email.it",
            "phone": "3331234567",
            "city": "ROMA",
        },
        "participants": [
            {"first_name": "Marco", "last_name": "Rossi"},
            {"first_name": "Sofia", "last_name": "Bianchi"},
        ][:visitors],
    })

    result["slot"] = {"time": slot.time, "ticket": slot.ticket_name}
    return result


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    if len(sys.argv) < 2:
        print("Usage: python cdp_booker.py <DD/MM/YYYY> [visitors] [time]")
        print("Example: python cdp_booker.py 28/07/2026 2 10:00")
        sys.exit(1)

    date_str = sys.argv[1]
    visitors = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    preferred_time = sys.argv[3] if len(sys.argv) > 3 else None

    result = asyncio.run(snipe_and_book(date_str, visitors, preferred_time))

    print("\n" + "=" * 60)
    print("📋 RESULT")
    print("=" * 60)
    print(json.dumps(result, indent=2, ensure_ascii=False))
