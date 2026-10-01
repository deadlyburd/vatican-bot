"""Vatican Museums provider.

Extracts the Vatican-specific logic (slot discovery via the search/timeavail
API, the deep-link URL template, and the browser booking flow) out of the old
local_sniper.py/test_10tabs.py into a single adapter. Adding another venue means
writing another class like this one and registering it.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from typing import List
from zoneinfo import ZoneInfo

from ..schema import BookingTarget
from .base import BookingProvider, Slot, pfill, wait_for

log = logging.getLogger("sniper")

VATICAN_BASE = "https://tickets.museivaticani.va"

# Confirmed-working GDPR checkbox keeper (ticks 'norme generali' + 'offerte').
KEEPER_JS = """
(() => {
    if (window._vaticanCbObserver) window._vaticanCbObserver.disconnect();
    if (window._vaticanCbInterval) clearInterval(window._vaticanCbInterval);
    function keepVaticanBoxesChecked() {
        document.querySelectorAll('input[type="checkbox"]').forEach(box => {
            if (box.disabled) return;
            let el = box.parentElement, text = '';
            for (let i = 0; i < 8 && el; i++) {
                const t = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                if (t.length > 4) { text = t.toLowerCase(); break; }
                el = el.parentElement;
            }
            const isTerms  = text.includes('norme generali') || text.includes('accetto le');
            const isOffers = text.includes('informazioni sulle offerte');
            if ((isTerms || isOffers) && !box.checked) {
                box.click();
                console.log('[keeper] ticked:', text.slice(0, 60));
            }
        });
        const close = document.querySelector("[data-cy='purchase-rules-close-btn']")
                   || [...document.querySelectorAll('button')]
                        .find(b => /chiudi|close/i.test(b.textContent));
        if (close) close.click();
    }
    keepVaticanBoxesChecked();
    window._vaticanCbObserver = new MutationObserver(() => keepVaticanBoxesChecked());
    window._vaticanCbObserver.observe(document.documentElement, {
        childList: true, subtree: true,
        attributes: true, attributeFilter: ['checked', 'disabled']
    });
    window._vaticanCbInterval = setInterval(keepVaticanBoxesChecked, 1000);
    return 'keeper-ok';
})()
"""


class VaticanProvider(BookingProvider):
    venue_id = "vatican"
    display_name = "Vatican Museums"
    keywords = ["vatican", "sistine", "vaticani", "musei"]

    # ── Slot discovery ──────────────────────────────────────────────────────

    def _slot_finder(self, proxy: str = ""):
        # slot_finder lives at repo root; ensure it's importable even when packaged.
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if root not in sys.path:
            sys.path.insert(0, root)
        from slot_finder import SlotFinder
        return SlotFinder(proxy=proxy)

    def find_slots(self, date_dmy: str, visitors: int, poll_proxy: str = "") -> List[Slot]:
        from slot_finder import AvailableSlot
        raw: List[AvailableSlot] = self._slot_finder(proxy=poll_proxy).find_slots(
            date_dmy, visitors, use_cache=False
        )
        return [self._from_available(s) for s in raw]

    @staticmethod
    def _from_available(s: "AvailableSlot") -> Slot:
        return Slot(
            date=s.date,
            time=s.time,
            slot_id=s.slot_id,
            ticket_id=s.ticket_id,
            ticket_name=s.ticket_name,
            visitors=s.visitors,
            price=s.price,
            residual=s.residual,
        )

    # ── URL + payload templates ─────────────────────────────────────────────

    @staticmethod
    def _rome_timezone():
        """Europe/Rome tz, with a fallback if tzdata isn't installed (Windows)."""
        try:
            return ZoneInfo("Europe/Rome")
        except Exception:
            from datetime import timezone, timedelta
            # Rome is UTC+1 (winter) / UTC+2 (summer); use a sane fixed offset.
            return timezone(timedelta(hours=2))

    def entry_url(self, target: BookingTarget, slot: Slot) -> str:
        rome = self._rome_timezone()
        d, m, y = slot.date.split("/")
        ts = int(datetime(int(y), int(m), int(d), tzinfo=rome).timestamp() * 1000)
        return f"{VATICAN_BASE}/home/fromtag/{target.visitors}/{ts}/MV-Biglietti/1"

    def keepalive_js(self, slot: Slot, target: BookingTarget) -> str:
        v = target.visitors
        return f"""
        (() => {{
            if (window._keepalive) clearInterval(window._keepalive);
            window._keepalive = setInterval(() => {{
                fetch('/api/visit/recap', {{
                    method:'POST',
                    headers:{{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'}},
                    credentials:'include',
                    body:JSON.stringify({{
                        visitId:'{slot.slot_id}',
                        visitTypeId:parseInt('{slot.ticket_id}'),
                        visitorNum:{v}, lang:'it',
                        tickets:[{{id:60,name:'Biglietto Intero',price:20,quantity:'{v}'}},
                                 {{id:61,name:'Biglietto Ridotto',price:10,quantity:0}}],
                        additionalCosts:{{'service-0':{{id:58,name:'Diritti di Prevendita',price:5,quantity:{v}}}}},
                        services:[{{id:58,name:'Diritti di Prevendita',price:5,quantity:{v}}}]
                    }})
                }}).then(r=>console.log('[kp]',r.status)).catch(e=>console.log('[kp]',e));
            }},60000);
        }})()
        """

    # ── Booking flow (runs on an already-open Playwright page) ──────────────

    async def book(self, page, target: BookingTarget, slot: Slot, label: str,
                   on_hold=None, on_payment=None, navigate: bool = True) -> bool:
        tid = slot.ticket_id
        visitors = target.visitors
        slot_time = slot.time
        url = self.entry_url(target, slot)

        def llog(msg):
            log.info(f"[{label}] {msg}")

        llog(f"→ {slot.date} {slot_time} | {target.customer_name} ({visitors}v)")

        if navigate:
            # [1] Visit home first (fresh Cloudflare cookie), then deep link
            llog(f"[1] {slot.date} {slot_time}")
            await page.goto(f"{VATICAN_BASE}/home", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        count = await wait_for(page,
            "document.querySelectorAll(\"[data-cy^='bookTicket_']\").length || 0",
            timeout=25, label="tickets")
        if not count or int(count) == 0:
            llog("❌ no ticket buttons")
            return False
        llog(f"  {count} ticket buttons")

        # [2] Click ticket
        llog("[2] ticket click")
        await page.evaluate(f"""
            (() => {{
                const b = document.querySelector("[data-cy='bookTicket_{tid}']");
                if (b) {{ b.click(); return; }}
                for (const card of document.querySelectorAll('[id^="ticket_"]')) {{
                    const t = card.innerText.toLowerCase();
                    if (t.includes('musei vaticani') && (t.includes('ingresso')||t.includes('biglietti'))) {{
                        const btn = card.querySelector("[data-cy^='bookTicket_']");
                        if (btn) {{ btn.click(); return; }}
                    }}
                }}
            }})()
        """)
        await page.wait_for_timeout(2000)

        # [3] Quantity
        llog("[3] quantity")
        await wait_for(page,
            "!!document.querySelector(\"[data-cy='ticketQuantity']\") || !!document.querySelector('select')",
            timeout=10, label="qty")
        set_qty = await page.evaluate(f"""
            (() => {{
                const sel = document.querySelector('select');
                if (sel) {{ sel.value='{visitors}'; sel.dispatchEvent(new Event('change',{{bubbles:true}})); return 'select'; }}
                return null;
            }})()
        """)
        if not set_qty:
            try:
                await page.click("[data-cy='ticketQuantity']")
                await page.wait_for_timeout(800)
            except Exception:
                pass
            await page.evaluate(f"""
                (() => {{
                    const items = Array.from(document.querySelectorAll("[data-cy='ticketQuantitySection']"));
                    const m = items.find(el => el.innerText.trim()==='{visitors}');
                    if (m) {{ m.click(); return; }}
                    if (items.length>={visitors}) items[{visitors}-1].click();
                    else if (items.length>0) items[items.length-1].click();
                }})()
            """)
        await page.wait_for_timeout(1500)
        await wait_for(page,
            "document.querySelectorAll(\"[data-cy='time']\").length||0",
            timeout=12, label="time cells")

        # [4] Time
        llog(f"[4] time={slot_time}")
        hour = int(slot_time.split(":")[0])
        if hour >= 13:
            await page.evaluate("""
                (() => {
                    const tabs = document.querySelectorAll('div.showGTMobile > div > div');
                    for (const t of tabs) {
                        if (/pomeriggio|afternoon/i.test(t.innerText)) { t.click(); return; }
                    }
                    if (tabs.length >= 2) tabs[1].click();
                })()
            """)
            await page.wait_for_timeout(1000)

        ct = await page.evaluate(f"""
            (() => {{
                for (const cell of document.querySelectorAll("[data-cy='time']")) {{
                    const num = cell.querySelector('.muvaCalendarNumber');
                    const txt = (num ? num.innerText : cell.innerText).trim().split('\\n')[0];
                    if (txt==='{slot_time}' && !cell.innerText.includes('ESAURITI')) {{
                        cell.scrollIntoView({{behavior:'smooth',block:'center'}});
                        cell.click(); return 'exact:'+txt;
                    }}
                }}
                for (const cell of document.querySelectorAll("[data-cy='time']")) {{
                    const txt = cell.innerText.trim();
                    if (!txt.includes('ESAURITI') && !txt.includes('SOLD') && txt.length>0) {{
                        cell.scrollIntoView({{behavior:'smooth',block:'center'}});
                        cell.click(); return 'any:'+txt.split('\\n')[0];
                    }}
                }}
                return null;
            }})()
        """)
        llog(f"  time={ct}")
        if not ct:
            llog("❌ no time available")
            return False
        await page.wait_for_timeout(2000)

        # [5] PROCEDI
        llog("[5] PROCEDI")
        try:
            await page.wait_for_selector("[data-cy='bookVisit']", timeout=10000)
            await page.click("[data-cy='bookVisit']")
        except Exception:
            await page.evaluate("document.querySelector(\"[data-cy='bookVisit']\")?.click()")
        await page.wait_for_timeout(6000)

        cur = page.url
        if "recap" in cur.lower():
            await page.evaluate("document.querySelector(\"[data-cy='bookVisit']\")?.click()")
            await page.wait_for_timeout(6000)
            cur = page.url

        # Cloudflare sometimes bounces back to entry — one retry
        if "fromtag" in cur.lower() or "home" in cur.lower():
            llog("  ↩ bounced — retrying PROCEDI")
            await page.wait_for_timeout(3000)
            try:
                await page.click("[data-cy='bookVisit']")
            except Exception:
                await page.evaluate("document.querySelector(\"[data-cy='bookVisit']\")?.click()")
            await page.wait_for_timeout(6000)
            cur = page.url

        # [6] Checkout
        llog("[6] checkout")
        form = await wait_for(page,
            "!!document.querySelector(\"[data-cy='managerSurname']\")",
            timeout=20, label="checkout form")
        cur = page.url
        if not form or "checkout" not in cur.lower():
            llog(f"❌ checkout not reached — {cur[:60]}")
            return False
        llog("  ✅ checkout!")

        # [7] Fill form
        llog("[7] fill form")
        parts = target.customer_name.split()
        first = parts[0] if parts else "Mario"
        last = " ".join(parts[1:]) if len(parts) > 1 else "Rossi"
        email = target.customer_email or f"booking{target.booking_id}@example.com"

        await pfill(page, "[data-cy='managerSurname']", last)
        await pfill(page, "[data-cy='managerName']", first)
        await pfill(page, "[data-cy='managerCity']", "Roma")
        await pfill(page, "[data-cy='managerEmail']", email)
        await pfill(page, "[data-cy='managerConfirmEmail']", email)
        await pfill(page, "[data-cy='managerPhone']", "3401234567")

        try:
            await page.click("[data-cy='managerSex']"); await page.wait_for_timeout(300)
            await page.click("[data-cy='managerSexSection']"); await page.wait_for_timeout(300)
        except Exception:
            pass
        try:
            await page.click("[data-cy='managerCountry']"); await page.wait_for_timeout(300)
            await page.evaluate("""
                (() => {
                    const items = Array.from(document.querySelectorAll("[data-cy='managerCountrySection']"));
                    const it = items.find(el => /ital/i.test(el.innerText));
                    if (it) it.click(); else if (items[0]) items[0].click();
                })()
            """)
            await page.wait_for_timeout(300)
        except Exception:
            pass
        await page.evaluate("""
            (() => {
                const inp = document.querySelector("[data-cy='dateCalendar']");
                if (!inp) return;
                inp.removeAttribute('readonly');
                inp.focus(); inp.value='15/01/1990';
                inp.dispatchEvent(new Event('input',{bubbles:true}));
                inp.dispatchEvent(new Event('change',{bubbles:true}));
                inp.setAttribute('readonly','true');
            })()
        """)
        await page.wait_for_timeout(300)
        try:
            await page.click("[data-cy='managerLanguage']"); await page.wait_for_timeout(300)
            await page.click("[data-cy='managerLanguageSection']"); await page.wait_for_timeout(300)
        except Exception:
            pass
        for i in range(visitors):
            try:
                if i > 0:
                    await page.evaluate(
                        f"document.querySelector('#participantElement_{i} div.tw-flex-grow > div')?.click()")
                    await page.wait_for_timeout(400)
                await pfill(page, f"#participantSurname_{i}", last)
                await pfill(page, f"#participantName_{i}", first)
            except Exception:
                pass
        llog("  form filled")

        # [8] GDPR keeper
        llog("[8] GDPR keeper")
        await page.evaluate(KEEPER_JS)
        await page.wait_for_timeout(2000)
        cb = await page.evaluate('document.querySelectorAll("input[type=checkbox]:checked").length')
        llog(f"  {cb} checkbox(es) checked")

        # [9] Keepalive
        llog("[9] keepalive")
        await page.evaluate(self.keepalive_js(slot, target))

        llog(f"✅ HOLD ACTIVE — {slot.date} {slot_time} | {target.customer_name}")
        if on_hold is not None:
            try:
                on_hold(label)
            except Exception:
                pass

        # [10] Watch for Turnstile, then hold forever
        for _ in range(600):
            await page.wait_for_timeout(1000)
            try:
                token = await page.evaluate("""
                    (() => {
                        const inp = document.querySelector(
                            '[name="cf-turnstile-response"], input[name*="turnstile"]');
                        return inp && inp.value && inp.value.length > 10
                            ? inp.value.slice(0,15) : null;
                    })()
                """)
                if token:
                    llog(f"🎉 TURNSTILE: {token}...")
                if "epay" in page.url:
                    llog(f"💳 EPAY: {page.url[:80]}")
                    if on_payment is not None:
                        try:
                            on_payment(label, page.url)
                        except Exception:
                            pass
                    break
            except Exception:
                pass

        llog("Entering infinite hold (Playwright keeps the page alive)...")
        while True:
            await page.wait_for_timeout(30000)
            try:
                cb_now = await page.evaluate(
                    'document.querySelectorAll("input[type=checkbox]:checked").length')
                llog(f"⏱ keepalive {cb_now} checked | {page.url[:50]}")
            except Exception:
                llog("⚠️ page check failed")
                break
        return True
