"""
Local Booking Worker — runs on the admin's desktop/laptop.

This is the "hands" of the system. It polls the Booking_Queue sheet for
pending tasks and executes them using the LOCAL machine's real Chrome
via CDP (Chrome DevTools Protocol).

Why this works when cloud-based booking doesn't:
    1. Real Chrome browser fingerprint (not nodriver, not Playwright)
    2. Real residential/home IP address (not a datacenter IP)
    3. Persistent Chrome profile with browsing history
    4. Real GPU, real window manager, real audio stack
    → Cloudflare Turnstile trusts this environment.

Usage:
    python -m agent.local_worker
    python -m agent.local_worker --cdp-port 9222 --interval 30

Prerequisites:
    Chrome must be running with remote debugging enabled:
    /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \\
        --remote-debugging-port=9222 \\
        --user-data-dir="$HOME/.vatican_chrome_profile"
"""

import asyncio
import json
import logging
import signal
import sys
import time
from datetime import datetime
from typing import Optional
from urllib.parse import quote

import requests
from agent.config import config
from agent.notifier import (
    notify_admins,
    notify_booking_failed,
    notify_booking_success,
    notify_startup,
)
from agent.sheets import get_sheets

logger = logging.getLogger(__name__)

VATICAN = "https://tickets.museivaticani.va"

# ── CDP Client ──────────────────────────────────────────────────────────────

class CDPClient:
    """
    Minimal Chrome DevTools Protocol client.
    Connects to a running Chrome instance via its debug port.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 9222):
        self.host = host
        self.port = port
        self.base = f"http://{host}:{port}"
        self.ws_url: str | None = None
        self.session = requests.Session()
        self._msg_id = 0

    # ── Connection ──────────────────────────────────────────────────────

    def connect(self, tab_url_pattern: str = "") -> bool:
        """
        Connect to Chrome and pick a tab.
        If tab_url_pattern is provided, find a tab matching it.
        Otherwise use the first tab.
        """
        try:
            resp = self.session.get(f"{self.base}/json", timeout=5)
            tabs = resp.json()
        except requests.RequestException as e:
            logger.error("Cannot connect to Chrome on port %d: %s", self.port, e)
            return False

        if not tabs:
            logger.error("No tabs open in Chrome")
            return False

        # Pick the right tab
        target = tabs[0]  # Default: first tab
        for tab in tabs:
            if tab.get("type") == "page" and tab_url_pattern in tab.get("url", ""):
                target = tab
                break

        self.ws_url = target.get("webSocketDebuggerUrl", "")
        if not self.ws_url:
            logger.error("Tab has no debugger URL")
            return False

        logger.info("Connected to Chrome tab: %s", target.get("url", "unknown")[:80])
        return True

    def navigate(self, url: str) -> bool:
        """Navigate the current tab to a URL."""
        result = self._send("Page.navigate", {"url": url})
        if result and "error" not in result:
            logger.info("Navigated to: %s", url[:80])
            return True
        return False

    def evaluate(self, js: str) -> any:
        """Execute JavaScript and return the result."""
        result = self._send(
            "Runtime.evaluate",
            {"expression": js, "returnByValue": True},
        )
        if result and "result" in result:
            return result["result"].get("value")
        return None

    def wait_for_selector(self, selector: str, timeout: int = 30) -> bool:
        """Wait for a CSS selector to appear in the DOM."""
        for _ in range(timeout * 2):
            found = self.evaluate(
                f"document.querySelector('{selector}') !== null"
            )
            if found:
                return True
            time.sleep(0.5)
        return False

    def click(self, selector: str) -> bool:
        """Click an element by CSS selector."""
        result = self._send(
            "Runtime.evaluate",
            {
                "expression": (
                    f"(function() {{"
                    f"var el = document.querySelector('{selector}');"
                    f"if (el) {{ el.scrollIntoView({{block:'center'}}); el.click(); return true; }}"
                    f"return false;"
                    f"}})()"
                ),
                "returnByValue": True,
            },
        )
        if result and "result" in result:
            return result["result"].get("value", False)
        return False

    def fill_input(self, selector: str, value: str) -> bool:
        """Fill an input field with stealth (simulates real typing)."""
        safe_value = value.replace("'", "\\'")
        js = (
            f"(function() {{"
            f"var el = document.querySelector('{selector}');"
            f"if (!el) return false;"
            f"el.focus(); el.select();"
            f"document.execCommand('selectAll', false, null);"
            f"document.execCommand('insertText', false, '{safe_value}');"
            f"el.dispatchEvent(new Event('input', {{bubbles: true}}));"
            f"el.dispatchEvent(new Event('change', {{bubbles: true}}));"
            f"el.dispatchEvent(new Event('blur', {{bubbles: true}}));"
            f"return true;"
            f"}})()"
        )
        result = self._send(
            "Runtime.evaluate",
            {"expression": js, "returnByValue": True},
        )
        if result and "result" in result:
            return result["result"].get("value", False)
        return False

    def get_url(self) -> str:
        """Get the current tab URL."""
        url = self.evaluate("window.location.href")
        return str(url) if url else ""

    def get_text(self, selector: str) -> str:
        """Get text content of an element."""
        text = self.evaluate(
            f"(function() {{"
            f"var el = document.querySelector('{selector}');"
            f"return el ? el.textContent.trim() : '';"
            f"}})()"
        )
        return str(text) if text else ""

    # ── Internal ────────────────────────────────────────────────────────

    def _send(self, method: str, params: dict = None) -> dict:
        """Send a CDP command via HTTP (synchronous fallback)."""
        self._msg_id += 1
        payload = {
            "id": self._msg_id,
            "method": method,
            "params": params or {},
        }
        try:
            # Use HTTP endpoint (not WebSocket — simpler, good enough for our use case)
            resp = self.session.post(
                f"{self.base}/json/{method}",
                json=payload,
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass

        # Fallback: try the /json/protocol endpoint
        try:
            resp = self.session.post(
                f"{self.base}/json/protocol",
                json=payload,
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass

        return {}


# ── Local Worker ────────────────────────────────────────────────────────────

class LocalWorker:
    """
    Polls Booking_Queue sheet for PENDING tasks, books them via local Chrome.

    Runs on the admin's desktop/laptop — the machine with real Chrome
    that can pass Cloudflare Turnstile.
    """

    def __init__(self, cdp_port: int = 9222, poll_interval: int = 30):
        self.sheets = get_sheets()
        self.cdp = CDPClient(port=cdp_port)
        self.poll_interval = poll_interval
        self.running = True
        self.stats = {"booked": 0, "failed": 0}

    # ── Main loop ───────────────────────────────────────────────────────

    def run(self):
        """Run the worker loop — poll queue, execute tasks."""
        logger.info("=" * 60)
        logger.info("LOCAL WORKER STARTED")
        logger.info("  CDP port: %d", self.cdp.port)
        logger.info("  Poll interval: %ds", self.poll_interval)
        logger.info("  Sheet: %s", config.google_sheet_id[:20])
        logger.info("=" * 60)

        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        # Verify Chrome is reachable
        if not self.cdp.connect():
            logger.error(
                "Cannot connect to Chrome. Start it with:\n"
                "  chrome --remote-debugging-port=%d", self.cdp.port
            )
            notify_admins("⚠️ Local worker started but Chrome is not reachable on port %d" % self.cdp.port)
        else:
            notify_admins("🟢 Local worker started — polling Booking_Queue every %ds" % self.poll_interval)

        while self.running:
            try:
                tasks = self.sheets.get_pending_tasks()
                if tasks:
                    logger.info("Found %d pending task(s)", len(tasks))
                    for task in tasks:
                        if not self.running:
                            break
                        self._execute_task(task)
                        time.sleep(3)  # Brief pause between bookings
                else:
                    logger.debug("No pending tasks")
            except Exception as e:
                logger.error("Worker cycle error: %s", e, exc_info=True)

            # Sleep, checking for shutdown
            for _ in range(self.poll_interval):
                if not self.running:
                    break
                time.sleep(1)

        logger.info("Worker stopped. Stats: %s", self.stats)

    def _shutdown(self, signum, frame):
        logger.info("Shutting down...")
        self.running = False

    # ── Task execution ──────────────────────────────────────────────────

    def _execute_task(self, task: dict):
        """Execute a single booking task."""
        name = task["customer_name"]
        date = task["date"]
        time_slot = task["time"]
        visitors = task["visitors"]
        task_row = task["row"]

        logger.info("Booking: %s | %s at %s | %dv", name, date, time_slot, visitors)

        # Verify Chrome is still connected
        if not self.cdp.ws_url:
            if not self.cdp.connect():
                self.sheets.mark_task_failed(task_row, "Chrome not reachable")
                return

        try:
            result = self._book_ticket(task)
        except Exception as e:
            logger.error("Booking exception: %s", e)
            result = {"success": False, "epay_url": None, "error": str(e)}

        if result["success"] and result.get("epay_url"):
            # Mark task as booked in Booking_Queue
            self.sheets.mark_task_booked(task_row, result["epay_url"])

            # Also update the Master sheet
            from agent.sheets import Booking
            booking = self.sheets.lookup_booking(task["booking_id"])
            if booking:
                self.sheets.write_payment_link(booking, result["epay_url"])
                self.sheets.write_status(booking, "BOOKED")

            # Notify
            notify_booking_success(
                date=date,
                time=time_slot,
                first_name=name,
                last_name="",
                visitors=visitors,
                epay_url=result["epay_url"],
                booking_id=task["booking_id"],
            )
            self.stats["booked"] += 1
            logger.info("✅ Booked: %s", result["epay_url"][:80])
        else:
            error = result.get("error", "Unknown")
            self.sheets.mark_task_failed(task_row, error)
            notify_booking_failed(
                date=date, time=time_slot,
                first_name=name, last_name="",
                error=error,
            )
            self.stats["failed"] += 1
            logger.error("❌ Failed: %s", error)

    # ── Booking via CDP ─────────────────────────────────────────────────

    def _book_ticket(self, task: dict) -> dict:
        """
        Execute the full booking flow via CDP against local Chrome.

        This is the same flow as agent/booker.py but uses CDP commands
        to control real Chrome rather than nodriver automation.
        """
        date = task["date"]
        time_str = task["time"]
        visitors = task["visitors"]
        ticket_id = task["ticket_id"]
        slot_id = task["slot_id"]

        # Parse date for URL
        parts = date.split("/")
        from datetime import datetime
        from zoneinfo import ZoneInfo
        rome = ZoneInfo("Europe/Rome")
        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        ts = int(datetime(y, m, d, 0, 0, 0, tzinfo=rome).timestamp() * 1000)

        # 1. NAVIGATE to ticket page
        url = f"{VATICAN}/home/fromtag/{visitors}/{ts}/MV-Biglietti/1"
        logger.info("  Navigating to: %s", url[:100])
        self.cdp.navigate(url)
        time.sleep(4)

        # Wait for ticket cards
        if not self.cdp.wait_for_selector("[data-cy^='bookTicket_']", timeout=30):
            return {"success": False, "epay_url": None, "error": "Ticket cards did not load"}

        # 2. CLICK Vatican ticket
        ticket_clicked = self.cdp.evaluate(
            "(function() {"
            "var cards = Array.from(document.querySelectorAll('[id^=\"ticket_\"]'));"
            "for (var c of cards) {"
            "  if (c.innerText.toLowerCase().includes('musei vaticani')) {"
            "    var btn = c.querySelector('[data-cy^=\"bookTicket_\"]');"
            "    if (btn) { btn.click(); return true; }"
            "  }"
            "}"
            "return false;"
            "})()"
        )
        logger.info("  Ticket clicked: %s", ticket_clicked)
        time.sleep(3)

        # 3. SELECT QUANTITY
        self.cdp.click("[data-cy='ticketQuantity']")
        time.sleep(1)
        opts = self.cdp.evaluate(
            "document.querySelectorAll('[data-cy=\"ticketQuantitySection\"]').length"
        )
        target_idx = min(visitors - 1, int(opts or 1) - 1)
        self.cdp.evaluate(
            f"document.querySelectorAll('[data-cy=\"ticketQuantitySection\"]')[{target_idx}].click()"
        )
        time.sleep(2)

        # 4. PICK TIME SLOT
        target_hour = int(time_str.split(":")[0]) if ":" in time_str else 0
        if target_hour >= 14:
            self.cdp.evaluate(
                "(function() {"
                "var tabs = Array.from(document.querySelectorAll('.tab, [role=\"tab\"], button[class*=\"tab\"]'))"
                "  .filter(function(el) { return el.offsetParent !== null; });"
                "var a = tabs.find(function(t) { return /pomeriggio/i.test(t.innerText); });"
                "if (a) a.click();"
                "})()"
            )
            time.sleep(1)

        # Click the time slot
        time_clicked = self.cdp.evaluate(
            f"(function() {{"
            f"var cells = document.querySelectorAll(\"[data-cy='time']\");"
            f"for (var i = 0; i < cells.length; i++) {{"
            f"  var c = cells[i];"
            f"  if (c.offsetParent === null) continue;"
            f"  var t = c.innerText.trim();"
            f"  if (t.indexOf('ESAURITI') > -1 || t.indexOf('SOLD') > -1) continue;"
            f"  if (t.indexOf('{time_str}') > -1) {{ c.click(); return true; }}"
            f"}}"
            f"return false;"
            f"}})()"
        )
        logger.info("  Time clicked: %s", time_clicked)
        time.sleep(2)

        # 5. PROCEDI
        self.cdp.click("[data-cy='bookVisit']")
        time.sleep(6)

        cur_url = self.cdp.get_url()
        logger.info("  URL after PROCEDI: %s", cur_url[:100])
        if "checkout" not in cur_url:
            return {"success": False, "epay_url": None, "error": f"Not on checkout: {cur_url[:100]}"}

        # 6. FILL BUYER FORM
        buyer_name = task.get("customer_name", "Guest Guest").split()
        first = buyer_name[0] if len(buyer_name) > 0 else "Guest"
        last = buyer_name[1] if len(buyer_name) > 1 else "Guest"

        self.cdp.fill_input("[data-cy='managerSurname']", last)
        self.cdp.fill_input("[data-cy='managerName']", first)

        # Gender
        self.cdp.click("[data-cy='managerSex']")
        time.sleep(0.3)
        self.cdp.click("[data-cy='managerSexSection']")
        time.sleep(0.3)

        # Country — select Italia
        self.cdp.click("[data-cy='managerCountry']")
        time.sleep(0.3)
        self.cdp.evaluate(
            "(function() {"
            "var s = document.querySelector('#searchInput_country');"
            "if (s) { s.value = 'Italia'; s.dispatchEvent(new Event('input', {bubbles: true})); }"
            "})()"
        )
        time.sleep(0.4)
        self.cdp.evaluate(
            "(function() {"
            "var items = Array.from(document.querySelectorAll(\"[data-cy='managerCountrySection']\"));"
            "for (var i = 0; i < items.length; i++) {"
            "  if (/^ital/i.test(items[i].innerText.trim())) { items[i].click(); return; }"
            "}"
            "})()"
        )
        time.sleep(0.3)

        self.cdp.fill_input("[data-cy='managerCity']", config.buyer_default_city)

        # Birth date
        self.cdp.click("[data-cy='dateCalendar']")
        time.sleep(1)
        self.cdp.evaluate(
            "var cells = document.querySelectorAll('.mat-calendar-body-cell-content');"
            "if (cells.length >= 15) cells[10].click();"
        )
        time.sleep(0.5)

        # Contact
        email = config.buyer_default_email or "booking@example.com"
        self.cdp.fill_input("[data-cy='managerEmail']", email)
        self.cdp.fill_input("[data-cy='managerConfirmEmail']", email)
        self.cdp.fill_input("[data-cy='managerPhone']", config.buyer_default_phone or "0000000000")

        # Language
        self.cdp.click("[data-cy='managerLanguage']")
        time.sleep(0.3)
        self.cdp.click("[data-cy='managerLanguageSection']")
        time.sleep(0.3)

        logger.info("  Form filled ✓")

        # 7. FILL PARTICIPANTS
        for i in range(visitors):
            if i > 0:
                self.cdp.evaluate(
                    f"(function() {{"
                    f"var el = document.querySelector('#participantElement_{i} div');"
                    f"if (el) el.click();"
                    f"}})()"
                )
                time.sleep(0.5)
            self.cdp.fill_input(f"#participantSurname_{i}", last)
            self.cdp.fill_input(f"#participantName_{i}", first if i == 0 else f"Guest{i+1}")

        logger.info("  Participants filled: %d", visitors)

        # 8. GDPR CHECKBOX
        self.cdp.evaluate(
            "var cb = document.querySelector('#mat-mdc-checkbox-0-input') "
            "|| document.querySelector('#mat-mdc-checkbox-1-input') "
            "|| document.querySelector('input[id^=\"mat-mdc-checkbox\"][type=\"checkbox\"]');"
            "if (cb) cb.click();"
        )
        time.sleep(1.5)

        # Close terms dialog
        self.cdp.click("[data-cy='purchase-rules-close-btn']")
        time.sleep(1)

        # 9. WAIT FOR TURNSTILE
        logger.info("  Waiting for Turnstile (up to 60s)...")
        token_found = False
        for i in range(120):
            token = self.cdp.evaluate(
                "(function() {"
                "var i = document.querySelector('input[name=\"cf-turnstile-response\"]');"
                "return i && i.value && i.value.length > 10 ? i.value.substring(0, 30) : null;"
                "})()"
            )
            if token:
                logger.info("  ✅ Turnstile solved in %.0fs", i * 0.5)
                token_found = True
                break
            time.sleep(0.5)

        if not token_found:
            logger.warning("  ⚠️ Turnstile timeout — trying ACQUISTA anyway")

        # 10. ACQUISTA
        time.sleep(1)
        self.cdp.click("[data-cy='buyButton']")
        logger.info("  ACQUISTA clicked — waiting for epay redirect...")

        # 11. CAPTURE EPAY URL
        for i in range(120):
            time.sleep(0.5)
            cur = self.cdp.get_url()
            if "epay.catholica.va" in cur:
                logger.info("  🎉 EPAY: %s", cur[:100])
                return {"success": True, "epay_url": cur, "error": None}
            if "/payment" in cur or "/confirm" in cur:
                logger.info("  Payment page: %s", cur[:100])
                return {"success": True, "epay_url": cur, "error": None}
            if "error" in cur.lower():
                logger.error("  Error page: %s", cur[:100])
                return {"success": False, "epay_url": None, "error": f"Error page: {cur[:100]}"}

        return {"success": False, "epay_url": None, "error": "No epay redirect after ACQUISTA"}


# ── Entry point ─────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Local Booking Worker")
    parser.add_argument("--cdp-port", type=int, default=9222, help="Chrome DevTools port")
    parser.add_argument("--interval", type=int, default=30, help="Poll interval in seconds")
    args = parser.parse_args()

    worker = LocalWorker(cdp_port=args.cdp_port, poll_interval=args.interval)
    worker.run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
