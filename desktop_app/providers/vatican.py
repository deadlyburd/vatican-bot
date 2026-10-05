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

    def find_slots(
        self,
        date_dmy: str,
        visitors: int,
        poll_proxy: str = "",
        ticket_type: str = "standard",
        language: str = "ENG",
    ) -> List[Slot]:
        """
        Find available Vatican slots.

        Args:
            date_dmy:    Date in DD/MM/YYYY format.
            visitors:    Number of visitors.
            poll_proxy:  Optional proxy URL for the API call.
            ticket_type: ``"standard"`` (MV-Biglietti, default) or
                         ``"guided"`` (MV-Visite-Guidate).
            language:    Language code for guided tours — e.g. ``"ENG"``, ``"ITA"``.
                         Ignored for standard tickets.
        """
        from slot_finder import AvailableSlot
        finder = self._slot_finder(proxy=poll_proxy)

        if ticket_type.lower().strip() == "guided":
            raw: List[AvailableSlot] = finder.find_slots_guided(
                date_dmy, visitors, language=language, use_cache=False
            )
        else:
            raw = finder.find_slots(date_dmy, visitors, use_cache=False)

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
        # Both standard and guided tours use the same /home/visit/ URL structure.
        # Area is always 1 (Musei Vaticani).
        return f"{VATICAN_BASE}/home/visit/{target.visitors}/{ts}/1"

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
        is_guided = getattr(target, "is_guided", False)
        language  = getattr(target, "language", "ENG") or "ENG"

        def llog(msg):
            log.info(f"[{label}] {msg}")

        llog(f"→ {slot.date} {slot_time} | {target.customer_name} ({visitors}v)"
             + (f" guided/{language}" if is_guided else ""))

        # ── [1] Navigate ───────────────────────────────────────────────────
        if navigate:
            llog(f"[1] navigate → {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2500)

        # Wait for ticket buttons to appear
        count = await wait_for(page,
            "document.querySelectorAll(\"[data-cy^='bookTicket_']\").length || 0",
            timeout=25, label="tickets")
        if not count or int(count) == 0:
            llog("❌ no ticket buttons")
            return False
        llog(f"  {count} ticket buttons visible")

        # ── [2] Click the correct ticket ───────────────────────────────────
        llog(f"[2] click ticket — is_guided={is_guided} tid={tid}")
        clicked = await page.evaluate(f"""
            (() => {{
                const isGuided = {'true' if is_guided else 'false'};
                const tid = '{tid}';

                function cardName(card) {{
                    const t = card.querySelector('.muvaTicketTitle, [data-cy="ticketName"], h2.visitName');
                    return (t ? t.innerText : card.innerText).toLowerCase().trim();
                }}

                // 1. Exact data-cy match
                const exact = document.querySelector("[data-cy='bookTicket_" + tid + "']");
                if (exact) {{ exact.scrollIntoView({{block:'center'}}); exact.click(); return 'exact:' + tid; }}

                // 2. Name-based match — guided vs standard
                for (const card of document.querySelectorAll("[id^='ticket_']")) {{
                    const btn = card.querySelector("[data-cy^='bookTicket_']");
                    if (!btn) continue;
                    const name = cardName(card);
                    const isGuidedCard = name.includes('visita') || name.includes('guidat') ||
                                         name.includes('guided') || name.includes('singoli');
                    const isStandardCard = (name.includes('biglietti') || name.includes('ingresso'))
                                           && !name.includes('visita');
                    if (isGuided && isGuidedCard) {{
                        btn.scrollIntoView({{block:'center'}}); btn.click();
                        return 'name-guided:' + name.slice(0, 50);
                    }}
                    if (!isGuided && isStandardCard) {{
                        btn.scrollIntoView({{block:'center'}}); btn.click();
                        return 'name-standard:' + name.slice(0, 50);
                    }}
                }}

                // 3. Last resort: first button
                const first = document.querySelector("[data-cy^='bookTicket_']");
                if (first) {{ first.scrollIntoView({{block:'center'}}); first.click(); return 'fallback-first'; }}
                return 'not-found';
            }})()
        """)
        llog(f"  ticket click: {clicked}")
        await page.wait_for_timeout(1500)

        # ── [3] Language selection (guided tours only) ─────────────────────
        if is_guided:
            llog(f"[3] select language={language}")
            # Map our language codes to the position in the Vatican dropdown
            # Recording shows Italian is item 4 (1-indexed) in the dropdown list.
            LANG_POSITIONS = {
                "ITA": 4, "ENG": 1, "ESP": 2, "FRA": 3, "DEU": 5, "POR": 6
            }
            lang_pos = LANG_POSITIONS.get(language.upper(), 1)

            lang_opened = await wait_for(page,
                "!!document.querySelector(\"[data-cy='visitLang']\")",
                timeout=8, label="visitLang dropdown")
            if lang_opened:
                try:
                    await page.click("[data-cy='visitLang']")
                    await page.wait_for_timeout(600)
                    # Click nth item in the language dropdown
                    await page.evaluate(f"""
                        (() => {{
                            const items = document.querySelectorAll(
                                'app-ticket-visit-language [data-cy=\"visitLangSection\"], '
                                + 'app-ticket-visit-language app-dropdown article section > div'
                            );
                            const idx = Math.min({lang_pos} - 1, items.length - 1);
                            if (items[idx]) {{ items[idx].click(); return idx; }}
                            // fallback: first item
                            if (items[0]) items[0].click();
                        }})()
                    """)
                    await page.wait_for_timeout(800)
                    llog(f"  language selected (pos {lang_pos})")
                except Exception as e:
                    llog(f"  ⚠️ language select failed: {e}")
        else:
            llog("[3] standard ticket — no language selection")

        # ── [4] Quantity ───────────────────────────────────────────────────
        llog(f"[4] set quantity={visitors}")
        await wait_for(page,
            "!!document.querySelector(\"[data-cy='ticketQuantity']\")",
            timeout=10, label="qty dropdown")

        # Recording shows two quantity dropdowns (adult + child row).
        # We click the first one (adults) and set it to `visitors`, leave child at 0.
        qty_set = await page.evaluate(f"""
            (() => {{
                // Try Angular dropdown (data-cy='ticketQuantity')
                const qtys = document.querySelectorAll("[data-cy='ticketQuantity']");
                if (qtys.length === 0) return 'none';
                // Open the first dropdown (adults)
                qtys[0].click();
                return 'opened:' + qtys.length;
            }})()
        """)
        llog(f"  qty open: {qty_set}")
        await page.wait_for_timeout(500)

        # Select the right quantity from the dropdown sections
        qty_clicked = await page.evaluate(f"""
            (() => {{
                const sections = document.querySelectorAll("[data-cy='ticketQuantitySection']");
                // sections are labelled 1,2,3… find the one matching visitors count
                for (const s of sections) {{
                    const t = s.innerText.trim();
                    if (t === '{visitors}' || t.startsWith('{visitors}')) {{
                        s.click(); return 'exact:' + t;
                    }}
                }}
                // fallback: index-based (visitors-1 because list is 1-indexed)
                const idx = Math.min({visitors} - 1, sections.length - 1);
                if (sections[idx]) {{ sections[idx].click(); return 'idx:' + idx; }}
                return 'none';
            }})()
        """)
        llog(f"  qty selected: {qty_clicked}")
        await page.wait_for_timeout(1000)

        # Wait for time slots to appear
        slot_count = await wait_for(page,
            "document.querySelectorAll(\"[data-cy='time']\").length || 0",
            timeout=15, label="time cells")
        llog(f"  time cells loaded: {slot_count}")

        # ── [5] Select time slot ───────────────────────────────────────────
        llog(f"[5] select time={slot_time}")
        hour = int(slot_time.split(":")[0])
        if hour >= 13:
            # Switch to afternoon tab if needed
            await page.evaluate("""
                (() => {
                    const tabs = document.querySelectorAll('div.showGTMobile > div > div');
                    for (const t of tabs) {
                        if (/pomeriggio|afternoon/i.test(t.innerText||'')) { t.click(); return; }
                    }
                    if (tabs.length >= 2) tabs[1].click();
                })()
            """)
            await page.wait_for_timeout(800)

        ct = await page.evaluate(f"""
            (() => {{
                // Try exact time match first
                for (const cell of document.querySelectorAll("[data-cy='time']")) {{
                    const inner = cell.innerText || '';
                    if (inner.includes('ESAURITI') || inner.includes('SOLD')) continue;
                    const num = cell.querySelector('.muvaCalendarNumber');
                    const txt = (num ? num.innerText : inner).trim().split('\\n')[0].trim();
                    if (txt === '{slot_time}') {{
                        cell.scrollIntoView({{behavior:'smooth',block:'center'}});
                        cell.click(); return 'exact:' + txt;
                    }}
                }}
                // Fallback: first available cell
                for (const cell of document.querySelectorAll("[data-cy='time']")) {{
                    const inner = cell.innerText || '';
                    if (!inner.includes('ESAURITI') && !inner.includes('SOLD') && inner.trim()) {{
                        cell.scrollIntoView({{behavior:'smooth',block:'center'}});
                        cell.click(); return 'any:' + inner.trim().split('\\n')[0];
                    }}
                }}
                return null;
            }})()
        """)
        llog(f"  time clicked: {ct}")
        if not ct:
            llog("❌ no available time slot found")
            return False
        await page.wait_for_timeout(2000)

        # ── [6] PROCEDI ────────────────────────────────────────────────────
        llog("[6] PROCEDI")
        try:
            await page.wait_for_selector("[data-cy='bookVisit']", timeout=10000)
            await page.click("[data-cy='bookVisit']")
        except Exception:
            await page.evaluate("document.querySelector(\"[data-cy='bookVisit']\")?.click()")
        await page.wait_for_timeout(5000)

        # Bounce detection: /home/visit/ means we're still on the entry page
        cur = page.url
        for _retry in range(2):
            if "visit" in cur.lower() and "checkout" not in cur.lower() and "recap" not in cur.lower():
                llog(f"  ↩ still on entry page ({cur[:60]}) — retrying PROCEDI")
                await page.wait_for_timeout(2000)
                try:
                    await page.click("[data-cy='bookVisit']")
                except Exception:
                    await page.evaluate("document.querySelector(\"[data-cy='bookVisit']\")?.click()")
                await page.wait_for_timeout(5000)
                cur = page.url
            else:
                break

        # ── [7] Checkout form ──────────────────────────────────────────────
        llog("[7] checkout")
        form = await wait_for(page,
            "!!document.querySelector(\"[data-cy='managerSurname']\")",
            timeout=20, label="checkout form")
        cur = page.url
        if not form or "checkout" not in cur.lower():
            llog(f"❌ checkout not reached — {cur[:60]}")
            return False
        llog("  ✅ checkout reached")

        parts = target.customer_name.split()
        first = parts[0] if parts else "Mario"
        last  = " ".join(parts[1:]) if len(parts) > 1 else "Rossi"
        email = target.customer_email or f"booking{target.booking_id}@example.com"

        await pfill(page, "[data-cy='managerSurname']", last)
        await pfill(page, "[data-cy='managerName']", first)
        await pfill(page, "[data-cy='managerCity']", "Roma")
        await pfill(page, "[data-cy='managerEmail']", email)
        await pfill(page, "[data-cy='managerConfirmEmail']", email)
        await pfill(page, "[data-cy='managerPhone']", "3401234567")

        try:
            await page.click("[data-cy='managerSex']")
            await page.wait_for_timeout(300)
            await page.click("[data-cy='managerSexSection']")
            await page.wait_for_timeout(300)
        except Exception:
            pass
        try:
            await page.click("[data-cy='managerCountry']")
            await page.wait_for_timeout(300)
            await page.evaluate("""
                (() => {
                    const items = Array.from(document.querySelectorAll("[data-cy='managerCountrySection']"));
                    const it = items.find(el => /ital/i.test(el.innerText||''));
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
                inp.focus(); inp.value = '15/01/1990';
                inp.dispatchEvent(new Event('input',  {bubbles:true}));
                inp.dispatchEvent(new Event('change', {bubbles:true}));
                inp.setAttribute('readonly', 'true');
            })()
        """)
        await page.wait_for_timeout(300)
        try:
            await page.click("[data-cy='managerLanguage']")
            await page.wait_for_timeout(300)
            await page.click("[data-cy='managerLanguageSection']")
            await page.wait_for_timeout(300)
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

        # ── [8] GDPR checkboxes — follow exact recording order ─────────────
        # Order from recording:
        #   a) Tick Terms (norme generali)    → mat-mdc-checkbox-1
        #   b) Close the modal that appears   → [data-cy='purchase-rules-close-btn']
        #   c) Tick reduced-price disclaimer  → mat-mdc-checkbox-6 (aria label with "ridotto")
        #   d) Tick offers checkbox           → mat-mdc-checkbox-7 (aria label with "offerte")
        llog("[8] GDPR checkboxes (recording order)")

        # a) Terms
        await page.evaluate("""
            (() => {
                const boxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
                for (const b of boxes) {
                    if (b.disabled) continue;
                    let el = b.parentElement, text = '';
                    for (let i = 0; i < 8 && el; i++) {
                        const t = (el.innerText||el.textContent||'').replace(/\\s+/g,' ').trim();
                        if (t.length > 4) { text = t.toLowerCase(); break; }
                        el = el.parentElement;
                    }
                    if ((text.includes('norme generali') || text.includes('accetto le')) && !b.checked) {
                        b.click(); break;
                    }
                }
            })()
        """)
        await page.wait_for_timeout(800)

        # b) Close the terms modal
        try:
            await page.click("[data-cy='purchase-rules-close-btn']")
            await page.wait_for_timeout(600)
        except Exception:
            try:
                await page.evaluate("""
                    (() => {
                        const btn = [...document.querySelectorAll('button')]
                            .find(b => /chiudi|close/i.test(b.textContent||''));
                        if (btn) btn.click();
                    })()
                """)
                await page.wait_for_timeout(600)
            except Exception:
                pass

        # c) Reduced-price disclaimer
        await page.evaluate("""
            (() => {
                const boxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
                for (const b of boxes) {
                    if (b.disabled || b.checked) continue;
                    const aria = (b.getAttribute('aria-label')||'').toLowerCase();
                    const id   = (b.id||'').toLowerCase();
                    if (aria.includes('ridotto') || aria.includes('reduced') ||
                        id.includes('checkbox-6')) {
                        b.click(); break;
                    }
                }
            })()
        """)
        await page.wait_for_timeout(400)

        # d) Offers / marketing checkbox
        await page.evaluate("""
            (() => {
                const boxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
                for (const b of boxes) {
                    if (b.disabled || b.checked) continue;
                    const aria = (b.getAttribute('aria-label')||'').toLowerCase();
                    const id   = (b.id||'').toLowerCase();
                    if (aria.includes('offerte') || aria.includes('offers') ||
                        id.includes('checkbox-7')) {
                        b.click(); break;
                    }
                }
            })()
        """)
        await page.wait_for_timeout(400)

        # e) Fallback keeper for any remaining unchecked non-disabled boxes
        await page.evaluate(KEEPER_JS)
        await page.wait_for_timeout(1500)

        cb = await page.evaluate('document.querySelectorAll("input[type=checkbox]:checked").length')
        llog(f"  {cb} checkbox(es) checked")

        # ── [9] Keepalive ──────────────────────────────────────────────────
        llog("[9] keepalive")
        await page.evaluate(self.keepalive_js(slot, target))

        llog(f"✅ HOLD ACTIVE — {slot.date} {slot_time} | {target.customer_name}")
        if on_hold is not None:
            try:
                on_hold(label)
            except Exception:
                pass

        # ── [10] Watch for Turnstile / ePay, hold forever ─────────────────
        for _ in range(600):
            await page.wait_for_timeout(1000)
            try:
                token = await page.evaluate("""
                    (() => {
                        const inp = document.querySelector(
                            '[name="cf-turnstile-response"], input[name*="turnstile"]');
                        return inp && inp.value && inp.value.length > 10
                            ? inp.value.slice(0, 15) : null;
                    })()
                """)
                if token:
                    llog(f"🎉 TURNSTILE token: {token}...")
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

        llog("Entering infinite hold (Playwright keeps page alive)...")
        while True:
            await page.wait_for_timeout(30000)
            try:
                cb_now = await page.evaluate(
                    'document.querySelectorAll("input[type=checkbox]:checked").length')
                llog(f"⏱ keepalive {cb_now} checked | {page.url[:50]}")
            except Exception:
                llog("⚠️ page check failed — exiting hold")
                break
        return True
