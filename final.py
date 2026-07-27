Vatican Multi-Hold Launcher
Spawns N independent Chrome sessions, each holding a different May slot.
Each session uses its own debug port + Chrome profile.
Run: python hold_multi.py
"""
import asyncio
import os
import sys
import time
import requests
import subprocess
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from zoneinfo import ZoneInfo

# ── GLOBAL CONFIG ─────────────────────────────────────────────────────────────
VATICAN_BASE      = 'https://tickets.museivaticani.va'
VISITORS          = 2
ADULTS            = 2
CHILDREN          = 0
HEARTBEAT_MS      = 240000   # 4 minutes
SEARCH_FROM       = "01/05/2026"
SEARCH_UNTIL      = "31/05/2026"   # only May
NUM_SESSIONS      = 6
BASE_DEBUG_PORT   = 9230     # increment by 5 each batch: 9230, 9236, 9241...
BASE_PROFILE      = r"C:\Users\gotic\AppData\Local\Temp\vatican_multi_"
CHROME_PATH       = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_AGENT        = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/146.0.7680.178 Safari/537.36")

PROFILE_DATA = {
    'first_name': 'Mario',
    'last_name':  'Rossi',
    'email':      'mario.rossi@example.com',
    'phone':      '+393401234567',
    'city':       'Roma',
}
# ─────────────────────────────────────────────────────────────────────────────


def scan_all_may_slots():
    """
    Scan all of May and return a list of available slots.
    Returns up to NUM_SESSIONS unique (date, time) slots.
    """
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': USER_AGENT,
        'Referer': f'{VATICAN_BASE}/',
    }
    session = requests.Session()
    try:
        session.get(f'{VATICAN_BASE}/home', headers={'User-Agent': USER_AGENT}, timeout=10)
    except Exception:
        pass

    start_dt = datetime.strptime(SEARCH_FROM, '%d/%m/%Y')
    end_dt   = datetime.strptime(SEARCH_UNTIL, '%d/%m/%Y')
    days     = (end_dt - start_dt).days + 1
    dates    = [(start_dt + timedelta(days=i)).strftime('%d/%m/%Y') for i in range(days)]

    found = []
    seen_dates = set()

    print(f"Scanning May for available slots (need {NUM_SESSIONS})...")
    for date_str in dates:
        dt = datetime.strptime(date_str, '%d/%m/%Y')
        if dt.weekday() == 6:
            continue
        sys.stdout.write(f"\r  Checking {date_str}... found {len(found)}/{NUM_SESSIONS}")
        sys.stdout.flush()
        try:
            r = session.get(f'{VATICAN_BASE}/api/search/resultPerTag', params={
                'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': date_str,
                'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
            }, headers=headers, timeout=10)
            if r.status_code != 200:
                continue
            ticket = next((v for v in r.json().get('visits', [])
                           if 'musei vaticani' in v.get('name', '').lower()
                           and 'ingresso' in v.get('name', '').lower()), None)
            if not ticket:
                continue
            tid = ticket['id']

            r2 = session.get(f'{VATICAN_BASE}/api/visit/timeavail', params={
                'lang': 'it', 'visitLang': '', 'visitTypeId': str(tid),
                'visitorNum': str(VISITORS), 'visitDate': date_str,
            }, headers=headers, timeout=10)
            if r2.status_code != 200:
                continue

            available = [s for s in r2.json().get('timetable', [])
                         if s.get('availability') in ('AVAILABLE', 'LOW_AVAILABILITY')]

            # Take up to 2 slots per date (morning + afternoon) to spread sessions
            slots_taken = 0
            for slot in available:
                key = f"{date_str}_{slot['time']}"
                if key not in seen_dates and slots_taken < 2:
                    seen_dates.add(key)
                    found.append({
                        'date':     date_str,
                        'slot_id':  str(slot['id']),
                        'slot_time': slot['time'],
                        'ticket_id': str(tid),
                        'visitors': VISITORS,
                    })
                    slots_taken += 1
                    if len(found) >= NUM_SESSIONS:
                        break

            if len(found) >= NUM_SESSIONS:
                break

        except Exception as e:
            pass
        time.sleep(0.3)

    print(f"\nFound {len(found)} slots:")
    for s in found:
        print(f"  {s['date']} {s['slot_time']}")
    return found


async def run_session(session_idx: int, slot_info: dict):
    """Run one hold session for the given slot."""
    port    = BASE_DEBUG_PORT + session_idx
    profile = f"{BASE_PROFILE}{session_idx}"
    label   = f"[S{session_idx+1} {slot_info['date']} {slot_info['slot_time']}]"

    def log(msg):
        print(f"{label} {msg}")

    async with async_playwright() as p:
        log(f"Launching Chrome on port {port}...")
        chrome_cmd = [
            CHROME_PATH,
            f'--remote-debugging-port={port}',
            f'--user-data-dir={profile}',
            '--profile-directory=Default',
            '--no-first-run',
            '--no-default-browser-check',
            '--start-maximized',
            '--disable-blink-features=AutomationControlled',
            '--ignore-gpu-blocklist',
            '--enable-webgl',
            '--enable-accelerated-2d-canvas',
            '--disable-features=IsolateOrigins,site-per-process',
            f'--user-agent={USER_AGENT}',
            'about:blank',
        ]
        subprocess.Popen(
            chrome_cmd,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        # Stagger startup so Chrome instances don't all fight at once
        await asyncio.sleep(3 + session_idx * 2)

        try:
            browser = await p.chromium.connect_over_cdp(f'http://localhost:{port}')
        except Exception as e:
            log(f"CDP connect failed: {e}")
            return

        ctx = (browser.contexts[0] if browser.contexts
               else await browser.new_context(
                   locale='it-IT', timezone_id='Europe/Rome',
                   user_agent=USER_AGENT, ignore_https_errors=True))
        page = await ctx.new_page()
        await Stealth().apply_stealth_async(page)

        def console_filter(msg):
            txt = msg.text
            junk = ["Private Access Token", "xr-spatial-tracking", "NaN",
                    "font-size:0", "native code", "cmg/1", "Violation"]
            if any(x in txt for x in junk) or len(txt) < 5:
                return
            log(f"[BROWSER] {txt}")
        page.on("console", console_filter)
        log("Connected")

        # Entry URL
        rome = ZoneInfo('Europe/Rome')
        d, m, y = slot_info['date'].split('/')
        ts = int(datetime(int(y), int(m), int(d), 0, 0, 0, tzinfo=rome).timestamp() * 1000)
        entry_url = f"{VATICAN_BASE}/home/fromtag/{slot_info['visitors']}/{ts}/MV-Biglietti/1"

        # [1] Navigate
        log(f"[1] {entry_url}")
        await page.goto(entry_url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(4000)

        # [2] Fresh ticket_id
        log("[2] ticket_id...")
        r = await page.request.get(f'{VATICAN_BASE}/api/search/resultPerTag',
            params={'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': slot_info['date'],
                    'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'},
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'})
        visits = (await r.json()).get('visits', [])
        ticket = next((v for v in visits if 'musei vaticani' in v.get('name', '').lower()
                       and 'ingresso' in v.get('name', '').lower()), None)
        if not ticket:
            log("No ticket found"); return
        tid = str(ticket['id'])
        log(f"ticket_id={tid}")

        # [3] bookTicket
        log(f"[3] bookTicket_{tid}")
        try:
            await page.wait_for_selector(f"[data-cy='bookTicket_{tid}']", timeout=10000)
            await page.click(f"[data-cy='bookTicket_{tid}']")
            await page.wait_for_timeout(2000)
        except Exception as e:
            log(f"bookTicket failed: {e}")

        # [4] Quantity
        log(f"[4] quantity={VISITORS}")
        try:
            await page.wait_for_selector("[data-cy='ticketQuantity']", timeout=8000)
            await page.click("[data-cy='ticketQuantity']")
            await page.wait_for_timeout(600)
            await page.evaluate(f"""
                () => {{
                    const items = Array.from(document.querySelectorAll("[data-cy='ticketQuantitySection']"));
                    const match = items.find(el => el.innerText.trim() === '{VISITORS}');
                    if (match) match.click();
                    else if (items[0]) items[0].click();
                }}
            """)
            await page.wait_for_timeout(600)
        except Exception as e:
            log(f"quantity failed: {e}")

        # [5] Time
        slot_time = slot_info['slot_time']
        log(f"[5] time={slot_time}")
        try:
            await page.wait_for_timeout(1500)

            async def try_click_time():
                return await page.evaluate(f"""
                    () => {{
                        for (const cell of document.querySelectorAll("[data-cy='time']")) {{
                            const num = cell.querySelector('div.muvaCalendarNumber');
                            const txt = num ? num.innerText.trim() : cell.innerText.trim();
                            if (txt === '{slot_time}') {{ cell.scrollIntoView(); cell.click(); return txt; }}
                        }}
                        return null;
                    }}
                """)

            clicked = await try_click_time()
            if not clicked:
                await page.evaluate("""() => {
                    const tabs = document.querySelectorAll('div.showGTMobile > div > div');
                    if (tabs.length >= 2) tabs[1].click();
                }""")
                await page.wait_for_timeout(800)
                clicked = await try_click_time()
            log(f"time clicked: {clicked}")
            await page.wait_for_timeout(1500)
        except Exception as e:
            log(f"time failed: {e}")

        # [6] PROCEED
        log("[6] PROCEED")
        try:
            await page.wait_for_selector("[data-cy='bookVisit']", timeout=15000)
            await page.click("[data-cy='bookVisit']")
            await page.wait_for_timeout(5000)
        except Exception as e:
            log(f"PROCEED failed: {e}")
            try:
                await page.evaluate("() => { const b = document.querySelector(\"[data-cy='bookVisit']\"); if(b) b.click(); }")
                await page.wait_for_timeout(5000)
            except Exception:
                pass

        # [7] Checkout form
        log("[7] checkout form")
        try:
            await page.wait_for_selector("[data-cy='managerSurname']", timeout=15000)

            async def fill(sel, val):
                try:
                    el = await page.wait_for_selector(sel, timeout=4000)
                    if el:
                        await el.click()
                        await el.fill(str(val))
                except Exception:
                    pass

            await fill("[data-cy='managerSurname']",      PROFILE_DATA['last_name'])
            await fill("[data-cy='managerName']",          PROFILE_DATA['first_name'])
            await fill("[data-cy='managerCity']",          PROFILE_DATA['city'])
            await fill("[data-cy='managerEmail']",         PROFILE_DATA['email'])
            await fill("[data-cy='managerConfirmEmail']",  PROFILE_DATA['email'])
            await fill("[data-cy='managerPhone']",         PROFILE_DATA['phone'])

            try:
                await page.click("[data-cy='managerSex']"); await page.wait_for_timeout(400)
                await page.click("[data-cy='managerSexSection']"); await page.wait_for_timeout(400)
            except Exception: pass

            try:
                await page.click("[data-cy='managerCountry']"); await page.wait_for_timeout(400)
                await page.evaluate("""() => {
                    const items = Array.from(document.querySelectorAll("[data-cy='managerCountrySection']"));
                    const italy = items.find(el => /ital/i.test(el.innerText));
                    if (italy) italy.click(); else if (items[0]) items[0].click();
                }""")
                await page.wait_for_timeout(400)
            except Exception: pass

            try:
                await page.click("mat-sidenav-container span.mat-focus-indicator")
                await page.wait_for_timeout(600)
                yr = await page.query_selector("text/1990")
                if yr: await yr.click(); await page.wait_for_timeout(400)
                for _ in range(4):
                    try: await page.click("button.mat-calendar-next-button"); await page.wait_for_timeout(200)
                    except Exception: pass
                try: await page.click("text/JUN"); await page.wait_for_timeout(400)
                except Exception: pass
                await page.evaluate("""() => {
                    const d = Array.from(document.querySelectorAll('span.mat-calendar-body-cell-content'))
                                   .find(el => el.innerText.trim() === '15');
                    if (d) d.click();
                }""")
                await page.wait_for_timeout(400)
            except Exception: pass

            try:
                await page.click("[data-cy='managerLanguage']"); await page.wait_for_timeout(400)
                await page.click("[data-cy='managerLanguageSection']"); await page.wait_for_timeout(400)
            except Exception: pass

            for i in range(VISITORS):
                try:
                    acc = await page.query_selector(f"#participantElement_{i} div.tw-flex-grow > div")
                    if acc: await acc.click(); await page.wait_for_timeout(500)
                    await fill(f"#participantSurname_{i}", PROFILE_DATA['last_name'])
                    await fill(f"#participantName_{i}",    PROFILE_DATA['first_name'])
                except Exception: pass

            try:
                cb1 = await page.query_selector("#mat-mdc-checkbox-1-input")
                if cb1 and not await cb1.is_checked():
                    await cb1.click(); await page.wait_for_timeout(800)
                    close = (await page.query_selector("[data-cy='purchase-rules-close-btn'] mat-icon")
                             or await page.query_selector("div.cdk-overlay-container mat-icon"))
                    if close: await close.click(); await page.wait_for_timeout(400)
                cb4 = await page.query_selector("#mat-mdc-checkbox-4-input")
                if cb4 and not await cb4.is_checked():
                    await cb4.click(); await page.wait_for_timeout(300)
            except Exception: pass

            log(f"HOLD STABILIZED — heartbeat every {HEARTBEAT_MS//1000}s")

            await page.evaluate("""
                (args) => {
                    const { slot_id, ticket_id, visitors, adult_count, child_count, heartbeat_ms } = args;
                    window._vatican_heartbeat = setInterval(() => {
                        fetch('/api/visit/recap', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            credentials: 'include',
                            body: JSON.stringify({
                                visitId: slot_id,
                                visitTypeId: parseInt(ticket_id),
                                visitorNum: parseInt(visitors),
                                lang: 'it',
                                tickets: [
                                    { id: 60, name: 'Biglietto Intero', price: 20, quantity: adult_count },
                                    { id: 61, name: 'Biglietto Ridotto', price: 10, quantity: child_count }
                                ],
                                additionalCosts: {
                                    'service-0': { id: 58, name: 'Diritti di Prevendita', price: 5, quantity: parseInt(visitors) }
                                },
                                services: [{ id: 58, name: 'Diritti di Prevendita', price: 5, quantity: parseInt(visitors) }]
                            })
                        }).then(r => console.log('HB', r.status, new Date().toLocaleTimeString()))
                          .catch(e => console.log('HB error', e));
                    }, heartbeat_ms);

                    window._box_maintainer = setInterval(() => {
                        const cb1 = document.querySelector("#mat-mdc-checkbox-1-input");
                        const cb4 = document.querySelector("#mat-mdc-checkbox-4-input");
                        if (cb1 && !cb1.checked) {
                            cb1.click();
                            setTimeout(() => {
                                const c = document.querySelector("[data-cy='purchase-rules-close-btn'] mat-icon");
                                if (c) c.click();
                            }, 1000);
                        }
                        if (cb4 && !cb4.checked) cb4.click();
                    }, 30000);
                }
            """, {
                'slot_id':     str(slot_info['slot_id']),
                'ticket_id':   str(tid),
                'visitors':    str(VISITORS),
                'adult_count': str(ADULTS),
                'child_count': str(CHILDREN),
                'heartbeat_ms': HEARTBEAT_MS,
            })

            # Keep Python alive (Chrome is detached, will survive terminal close)
            start = time.time()
            while True:
                elapsed = (time.time() - start) / 60
                log(f"ACTIVE {elapsed:.1f} min")
                await asyncio.sleep(60)

        except Exception as e:
            log(f"Checkout failed: {e} — browser stays open")
            while True:
                await asyncio.sleep(60)


async def main():
    # Step 1: scan May synchronously (one session, fast)
    slots = scan_all_may_slots()
    if not slots:
        print("No May slots found.")
        return

    print(f"\nLaunching {len(slots)} sessions in parallel...\n")

    # Step 2: run all sessions concurrently
    await asyncio.gather(*[
        run_session(i, slot)
        for i, slot in enumerate(slots)
    ])


if __name__ == "__main__":
    asyncio.run(main())