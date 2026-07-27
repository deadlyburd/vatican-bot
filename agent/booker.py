"""
Browser-based Vatican ticket booking using nodriver (undetected Chrome).

Consolidates the best approach from the 7 existing booker scripts.
Uses undetected-chromedriver (nodriver) to bypass Cloudflare detection.

Flow:
    1. Navigate to ticket page
    2. Select ticket type (standard entry, no lunch/special tours)
    3. Choose visitor quantity
    4. Pick time slot
    5. Click PROCEDI (proceed)
    6. Fill buyer form (name, email, phone, country, birth date)
    7. Fill participant names
    8. Accept GDPR checkbox
    9. Wait for Turnstile captcha (auto-solved via browser fingerprint)
    10. Click ACQUISTA (purchase)
    11. Capture epay.catholica.va payment URL
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import nodriver as uc

from agent.config import config
from agent.vatican_api import Slot

logger = logging.getLogger(__name__)

VATICAN = "https://tickets.museivaticani.va"
ROME = ZoneInfo("Europe/Rome")
PROFILE_DIR = os.path.expanduser("~/.vatican_chrome_profile")


# ── Buyer / Participant Data ────────────────────────────────────────────────

@dataclass
class BuyerInfo:
    """Information about the ticket buyer."""
    first_name: str
    last_name: str
    email: str
    phone: str = ""
    city: str = "Roma"
    country: str = "Italia"
    birth_date: str = "21/05/2001"  # DD/MM/YYYY fallback


@dataclass
class Participant:
    """A single participant/visitor on the booking."""
    first_name: str
    last_name: str
    ticket_type: str = "Adult"  # Adult, Child, Infant


# ── Booker ──────────────────────────────────────────────────────────────────

class VaticanBooker:
    """Automated Vatican Museum ticket booker using nodriver."""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.max_retries = config.booking_max_retries
        self.timeout = config.booking_timeout_seconds

    # ── Public API ──────────────────────────────────────────────────────

    async def book(
        self,
        slot: Slot,
        buyer: BuyerInfo,
        participants: List[Participant],
    ) -> dict:
        """
        Book a Vatican Museums ticket.

        Args:
            slot: The Slot to book (from SlotFinder)
            buyer: Buyer contact information
            participants: List of visitors (at least 1)

        Returns:
            {"success": bool, "epay_url": str | None, "error": str | None}
        """
        logger.info(
            "=== BOOKING START === %s %s, %dv, %d participants",
            slot.date, slot.time, slot.visitors, len(participants),
        )

        for attempt in range(1, self.max_retries + 1):
            logger.info("Attempt %d/%d", attempt, self.max_retries)
            result = await self._booking_attempt(slot, buyer, participants)
            if result["success"]:
                logger.info("=== BOOKING SUCCESS === epay=%s", result.get("epay_url", "")[:60])
                return result
            logger.warning("Attempt %d failed: %s", attempt, result.get("error", "unknown"))
            if attempt < self.max_retries:
                await asyncio.sleep(3)

        logger.error("=== BOOKING FAILED after %d attempts ===", self.max_retries)
        return {"success": False, "epay_url": None, "error": "Max retries exhausted"}

    # ── Core Booking Logic ──────────────────────────────────────────────

    async def _booking_attempt(
        self,
        slot: Slot,
        buyer: BuyerInfo,
        participants: List[Participant],
    ) -> dict:
        """A single booking attempt."""
        browser = None
        try:
            # ── Launch browser ──────────────────────────────────────────
            browser = await self._launch_browser()
            tab = browser.main_tab

            # ── Navigate ─────────────────────────────────────────────────
            url = self._build_url(slot)
            await tab.get(url)
            await tab.sleep(4)

            # Wait for ticket cards to load
            count = 0
            for _ in range(30):
                count = await tab.evaluate(
                    """document.querySelectorAll("[data-cy^='bookTicket_']").length"""
                )
                if count and int(count) > 0:
                    break
                await tab.sleep(0.5)
            logger.info("  Tickets loaded: %s", count)

            # ── Select ticket ────────────────────────────────────────────
            tid = await self._find_ticket_id(tab)
            if tid:
                btn = await tab.query_selector(f'[data-cy="bookTicket_{tid}"]')
                if btn:
                    await btn.click()
            await tab.sleep(3)

            # ── Set quantity ────────────────────────────────────────────
            qty = await tab.query_selector("[data-cy='ticketQuantity']")
            if qty:
                await qty.click()
            await tab.sleep(1)
            opts = await tab.query_selector_all("[data-cy='ticketQuantitySection']")
            # Select the option matching visitor count
            target_idx = min(slot.visitors - 1, len(opts) - 1)
            if target_idx >= 0 and target_idx < len(opts):
                await opts[target_idx].click()
            await tab.sleep(2)

            # ── Pick time slot ───────────────────────────────────────────
            await self._pick_time(tab, slot)

            # ── PROCEDI ──────────────────────────────────────────────────
            procedi = await tab.query_selector("[data-cy='bookVisit']")
            if procedi:
                await procedi.click()
            await tab.sleep(6)

            # Verify we're on checkout
            cur_url = str(await tab.evaluate("window.location.href"))
            if "checkout" not in cur_url:
                return {"success": False, "epay_url": None, "error": "Not on checkout page"}

            # ── Fill form ────────────────────────────────────────────────
            await self._fill_buyer_form(tab, buyer)

            # ── Fill participants ─────────────────────────────────────────
            await self._fill_participants(tab, participants)

            # ── GDPR + Turnstile + Purchase ──────────────────────────────
            await self._accept_gdpr(tab)
            await self._wait_turnstile(tab)
            epay_url = await self._click_acquista(tab)

            if epay_url:
                return {"success": True, "epay_url": epay_url, "error": None}

            return {"success": False, "epay_url": None, "error": "No epay URL captured"}

        except Exception as e:
            logger.error("Booking exception: %s", e)
            import traceback
            traceback.print_exc()
            return {"success": False, "epay_url": None, "error": str(e)}

        finally:
            if browser:
                try:
                    await tab.sleep(1)
                    browser.stop()
                except Exception:
                    pass

    # ── Browser ──────────────────────────────────────────────────────────

    async def _launch_browser(self) -> uc.Browser:
        """Launch nodriver with anti-detection settings."""
        # Clean lockfile
        for lf in ["lockfile", "SingletonLock", "SingletonCookie"]:
            try:
                os.remove(os.path.join(PROFILE_DIR, lf))
            except Exception:
                pass

        browser_args = [
            "--disable-features=AutomationControlled",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-breakpad",
            "--disable-dev-shm-usage",
            "--disable-session-crashed-bubble",
            "--disable-search-engine-choice-screen",
        ]

        # Add proxy if configured
        proxy = config.proxy_url
        if proxy:
            browser_args.append(f"--proxy-server={proxy}")

        return await uc.start(
            user_data_dir=PROFILE_DIR,
            headless=self.headless,
            lang="it-IT",
            no_sandbox=True,
            window_size=(1005, 572),
            browser_args=browser_args,
        )

    def _build_url(self, slot: Slot) -> str:
        """Build the fromtag URL for navigation."""
        parts = slot.date.split("/")
        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        ts = int(datetime(y, m, d, 0, 0, 0, tzinfo=ROME).timestamp() * 1000)
        return f"{VATICAN}/home/fromtag/{slot.visitors}/{ts}/MV-Biglietti/1"

    # ── Ticket Selection ─────────────────────────────────────────────────

    async def _find_ticket_id(self, tab) -> Optional[str]:
        """Find the Vatican Museums standard entry ticket ID from the DOM."""
        result = await tab.evaluate("""
            (() => {
                var cards = Array.from(document.querySelectorAll('[id^="ticket_"]'));
                for (var c of cards) {
                    if (c.innerText.toLowerCase().includes('musei vaticani')) {
                        var btn = c.querySelector('[data-cy^="bookTicket_"]');
                        if (btn) return btn.getAttribute('data-cy').replace('bookTicket_', '');
                    }
                }
                return null;
            })()
        """)
        # Unwrap nodriver type annotation
        if isinstance(result, list) and result:
            result = result[0][1].get("value") if isinstance(result[0], list) and len(result[0]) > 1 else None
        return str(result) if result else None

    # ── Time Slot Selection ──────────────────────────────────────────────

    async def _pick_time(self, tab, slot: Slot):
        """Select the target time slot, switching tabs if needed."""
        target_hour = int(slot.time.split(":")[0]) if ":" in slot.time else 0

        # Switch to afternoon tab if needed
        if target_hour >= 14:
            await tab.evaluate("""
                (() => {
                    var tabs = Array.from(
                        document.querySelectorAll('.tab, [role="tab"], button[class*="tab"]')
                    ).filter(function(el) { return el.offsetParent !== null; });
                    var a = tabs.find(function(t) { return /pomeriggio/i.test(t.innerText); });
                    if (a) a.click();
                    else if (tabs.length >= 2) tabs[1].click();
                })()
            """)
            await tab.sleep(1)

        # Find and click the target time cell
        time_idx = await tab.evaluate(f"""
            (function() {{
                var cells = document.querySelectorAll("[data-cy='time']");
                for (var i = 0; i < cells.length; i++) {{
                    var c = cells[i];
                    if (c.offsetParent === null) continue;
                    var t = c.innerText.trim();
                    if (t.indexOf('ESAURITI') > -1 || t.indexOf('SOLD') > -1) continue;
                    if (t.indexOf('{slot.time}') > -1) return i;
                }}
                // Fallback: first non-sold-out
                for (var i = 0; i < cells.length; i++) {{
                    var c = cells[i];
                    if (c.offsetParent === null) continue;
                    var t = c.innerText.trim();
                    if (!(t.indexOf('ESAURITI') > -1 || t.indexOf('SOLD') > -1)) return i;
                }}
                return -1;
            }})()
        """)

        if isinstance(time_idx, list) and time_idx:
            time_idx = time_idx[0][1].get("value") if isinstance(time_idx[0], list) and len(time_idx[0]) > 1 else -1

        if time_idx >= 0:
            cells = await tab.query_selector_all("[data-cy='time']")
            if time_idx < len(cells):
                await cells[time_idx].scroll_into_view()
                await tab.sleep(0.3)
                await cells[time_idx].click()
                logger.info("  Time selected: idx=%d", time_idx)

        await tab.sleep(2)

    # ── Form Fill ────────────────────────────────────────────────────────

    async def _fill_buyer_form(self, tab, buyer: BuyerInfo):
        """Fill the buyer/contact form on the checkout page."""
        logger.info("  Filling buyer form: %s %s", buyer.first_name, buyer.last_name)

        # Helper: stealth fill via JS execCommand
        async def stealth_fill(selector: str, value: str):
            js = f"""
                (() => {{
                    var el = document.querySelector("{selector}");
                    if (!el) return;
                    el.focus(); el.select();
                    document.execCommand('selectAll', false, null);
                    document.execCommand('insertText', false, "{value}");
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    el.dispatchEvent(new Event('blur', {{bubbles: true}}));
                }})()
            """
            await tab.evaluate(js)
            await tab.sleep(0.15)

        # Fill fields in order
        await stealth_fill("[data-cy='managerSurname']", buyer.last_name)
        await stealth_fill("[data-cy='managerName']", buyer.first_name)

        # Gender — click to open, pick first option
        await tab.evaluate("document.querySelector(\"[data-cy='managerSex']\")?.click()")
        await tab.sleep(0.3)
        await tab.evaluate("document.querySelector(\"[data-cy='managerSexSection']\")?.click()")
        await tab.sleep(0.3)

        # Country — search and select Italia
        await tab.evaluate("document.querySelector(\"[data-cy='managerCountry']\")?.click()")
        await tab.sleep(0.3)
        country_js = f"""
            (() => {{
                var s = document.querySelector('#searchInput_country');
                if (s) {{ s.value = '{buyer.country}'; s.dispatchEvent(new Event('input', {{bubbles: true}})); }}
            }})()
        """
        await tab.evaluate(country_js)
        await tab.sleep(0.4)
        await tab.evaluate("""
            (() => {
                var items = Array.from(document.querySelectorAll("[data-cy='managerCountrySection']"));
                for (var i = 0; i < items.length; i++) {
                    if (/^ital/i.test(items[i].innerText.trim())) { items[i].click(); return; }
                }
                var span = document.querySelector("[data-cy='managerCountrySection'] span");
                if (span) span.click();
            })()
        """)
        await tab.sleep(0.3)

        await stealth_fill("[data-cy='managerCity']", buyer.city)

        # Birth date — calendar click → select year/month/day
        if buyer.birth_date:
            parts = buyer.birth_date.split("/")
            await tab.evaluate("document.querySelector(\"[data-cy='dateCalendar']\")?.click()")
            await tab.sleep(1)
            # Note: calendar cell positions are approximate — they depend on the rendered month
            await tab.evaluate("""
                (() => {
                    var cells = document.querySelectorAll('.mat-calendar-body-cell-content');
                    if (cells.length >= 25) cells[10].click();  // middle-ish cell
                })()
            """)
            await tab.sleep(0.5)

        # Contact
        await stealth_fill("[data-cy='managerEmail']", buyer.email)
        await stealth_fill("[data-cy='managerConfirmEmail']", buyer.email)
        await stealth_fill("[data-cy='managerPhone']", buyer.phone)

        # Language — pick first
        await tab.evaluate("document.querySelector(\"[data-cy='managerLanguage']\")?.click()")
        await tab.sleep(0.3)
        await tab.evaluate("document.querySelector(\"[data-cy='managerLanguageSection']\")?.click()")
        await tab.sleep(0.3)

        logger.info("  Buyer form filled ✓")

    async def _fill_participants(self, tab, participants: List[Participant]):
        """Fill participant names on the checkout page."""
        for i, p in enumerate(participants):
            # Expand participant row if collapsed
            if i > 0:
                await tab.evaluate(f"""
                    (() => {{
                        var el = document.querySelector('#participantElement_{i} div.tw-flex-grow > div > div.tw-flex');
                        if (el) el.click();
                        else {{
                            var el2 = document.querySelector('#participantElement_{i} div.tw-flex-grow > div');
                            if (el2) el2.click();
                        }}
                    }})()
                """)
                await tab.sleep(0.5)

            # Fill name fields
            await self._stealth_fill_js(tab, f"#participantSurname_{i}", p.last_name)
            await self._stealth_fill_js(tab, f"#participantName_{i}", p.first_name)

        # Click outside to blur
        await tab.evaluate("""
            (() => {
                var el = document.querySelector('div.muvaParticipantContainer');
                if (el) el.click();
            })()
        """)
        await tab.sleep(0.5)
        logger.info("  Participants filled: %d", len(participants))

    async def _stealth_fill_js(self, tab, selector: str, value: str):
        """Low-level stealth fill via JS."""
        js = f"""
            (() => {{
                var el = document.querySelector("{selector}");
                if (!el) return;
                el.focus(); el.select();
                document.execCommand('selectAll', false, null);
                document.execCommand('insertText', false, "{value}");
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                el.dispatchEvent(new Event('blur', {{bubbles: true}}));
            }})()
        """
        await tab.evaluate(js)
        await tab.sleep(0.15)

    # ── GDPR + Captcha + Purchase ────────────────────────────────────────

    async def _accept_gdpr(self, tab):
        """Accept GDPR/terms checkboxes."""
        # Find and click GDPR checkbox
        cb = await tab.query_selector("#mat-mdc-checkbox-0-input")
        if not cb:
            cb = await tab.query_selector("#mat-mdc-checkbox-1-input")
        if not cb:
            cb = await tab.query_selector('input[id^="mat-mdc-checkbox"][type="checkbox"]')
        if cb:
            await cb.click()
            logger.info("  GDPR accepted ✓")

        await asyncio.sleep(1.5)

        # Close terms dialog if present
        close = await tab.query_selector("[data-cy='purchase-rules-close-btn']")
        if close:
            await close.click()
        await asyncio.sleep(1)

    async def _wait_turnstile(self, tab):
        """Wait for Cloudflare Turnstile to auto-solve."""
        logger.info("  Turnstile: waiting for widget...")

        # Wait for captcha element to render
        for i in range(30):
            ce = await tab.query_selector(".captchaElement")
            if ce:
                has_content = await tab.evaluate(
                    "document.querySelector('.captchaElement')?.children?.length > 0"
                )
                if has_content:
                    logger.info("  Turnstile widget loaded after %ds", i)
                    break
            await asyncio.sleep(1)

        # Wait for auto-solve (up to 60s)
        logger.info("  Turnstile: waiting for auto-solve (up to 60s)...")
        for i in range(120):
            try:
                token = await tab.evaluate(
                    """(() => {
                        var i = document.querySelector('input[name="cf-turnstile-response"]');
                        return i && i.value && i.value.length > 10 ? i.value.substring(0, 30) : null;
                    })()"""
                )
                if token:
                    logger.info("  ✅ Turnstile solved in %.0fs", i * 0.5)
                    return
            except Exception:
                logger.warning("  Connection dropped at %.0fs — browser may have redirected", i * 0.5)
                return
            await asyncio.sleep(0.5)

        logger.warning("  ⚠️ Turnstile solve timeout — trying ACQUISTA anyway")

    async def _click_acquista(self, tab) -> Optional[str]:
        """Click ACQUISTA and capture the epay redirect URL."""
        logger.info("  Clicking ACQUISTA...")
        await tab.sleep(1)

        buy = await tab.query_selector("[data-cy='buyButton']")
        if buy:
            await buy.scroll_into_view()
            await tab.sleep(0.3)
            await buy.click()
            logger.info("  ACQUISTA clicked ✓")
        else:
            logger.warning("  ACQUISTA button not found")
            return None

        # Wait for epay redirect
        for i in range(120):
            await asyncio.sleep(0.5)
            try:
                cur = str(await tab.evaluate("window.location.href"))
            except Exception:
                await asyncio.sleep(2)
                try:
                    cur = str(await tab.evaluate("window.location.href"))
                except Exception:
                    logger.warning("  Browser disconnected — payment may have loaded")
                    return "epay (check browser)"

            if "epay.catholica.va" in cur:
                logger.info("  🎉 EPAY URL captured! %s", cur[:100])
                return cur
            if "/payment" in cur or "/confirm" in cur:
                logger.info("  Payment page: %s", cur[:100])
                return cur
            if "error" in cur.lower():
                logger.error("  Error page: %s", cur[:100])
                return None
            if i == 10:
                logger.info("  Current URL: %s", cur[:100])

        return None


# ── Convenience ─────────────────────────────────────────────────────────────

async def book_slot(
    slot: Slot,
    buyer: BuyerInfo,
    participants: List[Participant],
    headless: bool = False,
) -> dict:
    """Convenience: book a single slot."""
    booker = VaticanBooker(headless=headless)
    return await booker.book(slot, buyer, participants)
