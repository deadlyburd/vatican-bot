"""
Headful Hold Forever — Playwright
==================================
Opens Vatican in a real browser, recaps a slot, then re-recaps every 4 minutes
using the full browser flow to keep the session warm.

Run:
    python headful_hold_forever.py --date 15/06/2026 --visitors 2 --lang ENG
    python headful_hold_forever.py --date 26/05/2026 --visitors 2 --lang ITA
"""
import sys, os, time, asyncio, argparse, requests
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()

BOT_TOKEN  = os.getenv('TELEGRAM_BOT_TOKEN', '')
ADMIN_CHAT = os.getenv('ADMIN_TELEGRAM_IDS', '').split(',')[0].strip()

BASE = 'https://tickets.museivaticani.va'
RE_RECAP_INTERVAL = 4 * 60   # 4 minutes

TAG_MAP = {
    'standard': 'MV-Biglietti',
    'guided':   'MV-Visite-Guidate',
}


def tg(text):
    if not BOT_TOKEN or not ADMIN_CHAT:
        return
    try:
        requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json={'chat_id': ADMIN_CHAT, 'text': text, 'parse_mode': 'HTML'},
            timeout=8
        )
    except Exception:
        pass


def log(msg):
    ts = datetime.now(ZoneInfo('Europe/Rome')).strftime('%H:%M:%S')
    print(f'[{ts}] {msg}')


async def find_and_recap_browser(page, date, visitors, lang, tag='MV-Visite-Guidate'):
    """
    Full browser flow:
    1. Navigate to deep link
    2. Wait for Angular to load
    3. Call recap API using browser's session cookies
    Returns slot info dict or None.
    """
    from playwright.async_api import TimeoutError as PWTimeout

    # Build timestamp for deep link (Rome midnight)
    day, month, year = date.split('/')
    from datetime import datetime as dt
    rome = ZoneInfo('Europe/Rome')
    midnight = dt(int(year), int(month), int(day), 0, 0, 0, tzinfo=rome)
    ts = int(midnight.timestamp() * 1000)

    deep_url = f'{BASE}/home/fromtag/{visitors}/{ts}/{tag}/1'
    log(f'  Navigating to: {deep_url}')

    try:
        await page.goto(deep_url, wait_until='networkidle', timeout=30000)
    except PWTimeout:
        await page.goto(deep_url, wait_until='domcontentloaded', timeout=20000)

    await page.wait_for_timeout(3000)  # let Angular settle

    # Use browser's fetch to call search API (uses browser cookies)
    result = await page.evaluate(f"""
    async () => {{
        const r = await fetch('{BASE}/api/search/resultPerTag?lang=it&visitorNum={visitors}&visitDate={date}&area=1&who=&page=0&tag={tag}', {{
            headers: {{'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}}
        }});
        return await r.json();
    }}
    """)

    visits = result.get('visits', [])
    log(f'  Search returned {len(visits)} tickets')

    # Find first available ticket
    slot_info = None
    for v in visits:
        if v.get('availability') in ('SOLD_OUT', 'NOT_ALLOWED'):
            continue
        tid = str(v['id'])
        tname = v.get('name', '')

        # Check timeavail
        ta = await page.evaluate(f"""
        async () => {{
            const r = await fetch('{BASE}/api/visit/timeavail?lang=it&visitLang={lang}&visitTypeId={tid}&visitorNum={visitors}&visitDate={date}', {{
                headers: {{'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}}
            }});
            return await r.json();
        }}
        """)

        for sl in ta.get('timetable', []):
            if sl.get('availability') == 'AVAILABLE':
                slot_info = {
                    'slot_id': sl['id'], 'time': sl['time'],
                    'ticket_id': tid, 'ticket_name': tname, 'lang': lang
                }
                log(f'  Found slot: {sl["time"]} | {tname[:50]}')
                break
        if slot_info:
            break

    if not slot_info:
        log('  No available slot via API — checking suggestion cards on page...')
        # Try clicking PRENOTA on suggestion cards
        try:
            prenota_btn = page.locator('text=PRENOTA').first
            if await prenota_btn.is_visible(timeout=3000):
                await prenota_btn.click()
                await page.wait_for_timeout(2000)
                log('  Clicked PRENOTA on suggestion card')
                # Now try the API again with updated page state
                result2 = await page.evaluate(f"""
                async () => {{
                    const r = await fetch('{BASE}/api/search/resultPerTag?lang=it&visitorNum={visitors}&visitDate={date}&area=1&who=&page=0&tag={tag}', {{
                        headers: {{'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}}
                    }});
                    return await r.json();
                }}
                """)
                for v in result2.get('visits', []):
                    if v.get('availability') in ('SOLD_OUT', 'NOT_ALLOWED'):
                        continue
                    tid = str(v['id'])
                    tname = v.get('name', '')
                    ta2 = await page.evaluate(f"""
                    async () => {{
                        const r = await fetch('{BASE}/api/visit/timeavail?lang=it&visitLang={lang}&visitTypeId={tid}&visitorNum={visitors}&visitDate={date}', {{
                            headers: {{'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}}
                        }});
                        return await r.json();
                    }}
                    """)
                    for sl in ta2.get('timetable', []):
                        if sl.get('availability') == 'AVAILABLE':
                            slot_info = {'slot_id': sl['id'], 'time': sl['time'],
                                         'ticket_id': tid, 'ticket_name': tname, 'lang': lang}
                            log(f'  Found via suggestion: {sl["time"]} | {tname[:50]}')
                            break
                    if slot_info:
                        break
        except Exception as e:
            log(f'  Suggestion click failed: {e}')

    if not slot_info:
        log('  No available slot found')
        return None

    # Get services
    services_result = await page.evaluate(f"""
    async () => {{
        const r = await fetch('{BASE}/api/visit/services?lang=it&visitId={slot_info["slot_id"]}&visitTypeId={slot_info["ticket_id"]}&visitorNum={visitors}', {{
            headers: {{'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}}
        }});
        return await r.json();
    }}
    """)
    services = services_result.get('services', []) or []

    # Build recap body
    svc_list = []
    add_costs = {}
    if services:
        svc = services[0]
        svc_list = [{'id': svc.get('id', 58), 'name': svc.get('name', 'Diritti di Prevendita'),
                     'price': svc.get('price', 5), 'quantity': visitors}]
        add_costs = {'service-0': {'id': svc.get('id', 58), 'name': svc.get('name', 'Diritti di Prevendita'),
                                    'price': svc.get('price', 5), 'quantity': visitors}}

    recap_body = {
        'visitId': str(slot_info['slot_id']),
        'visitTypeId': int(slot_info['ticket_id']),
        'visitorNum': visitors,
        'lang': 'it',
        'tickets': [
            {'id': 60, 'name': 'Biglietto Intero',  'price': 20, 'quantity': str(visitors)},
            {'id': 61, 'name': 'Biglietto Ridotto',  'price': 10, 'quantity': '0'},
        ],
        'additionalCosts': add_costs,
        'services': svc_list,
    }

    import json as _json
    recap_result = await page.evaluate(f"""
    async () => {{
        const r = await fetch('{BASE}/api/visit/recap', {{
            method: 'POST',
            headers: {{'Accept': 'application/json', 'Content-Type': 'application/json',
                       'X-Requested-With': 'XMLHttpRequest', 'Origin': '{BASE}', 'Referer': '{BASE}/'}},
            body: JSON.stringify({_json.dumps(recap_body)})
        }});
        const data = await r.json();
        return {{status: r.status, data}};
    }}
    """)

    if recap_result.get('status') != 200:
        log(f'  Recap failed: {recap_result}')
        return None

    recap_id = recap_result['data'].get('recapId') or recap_result['data'].get('id', '')
    total    = recap_result['data'].get('total', 0)
    slot_info['recap_id'] = recap_id
    slot_info['total']    = total
    log(f'  🔒 Recapped! recapId={recap_id} €{total}')
    return slot_info


async def main(date, visitors, lang, ticket_type):
    from playwright.async_api import async_playwright

    tag = TAG_MAP.get(ticket_type, 'MV-Visite-Guidate')

    log(f'Hold Forever Test (HEADFUL) | {date} | {visitors}v | lang={lang}')
    log(f'Re-recap interval: {RE_RECAP_INTERVAL//60} minutes')

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,   # headful — Vatican needs real browser
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled'],
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            locale='it-IT',
            timezone_id='Europe/Rome',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        )
        page = await context.new_page()

        # ── Initial recap ─────────────────────────────────────────────────
        log('Finding and recapping slot...')
        slot = await find_and_recap_browser(page, date, visitors, lang, tag)

        if not slot:
            log('❌ Could not find or recap a slot. Exiting.')
            await browser.close()
            return

        hold_start  = time.time()
        recap_count = 1

        tg(
            f'🔒 <b>Headful Hold Forever Started</b>\n'
            f'📅 {date}  🕐 {slot["time"]}  👥 {visitors}v  [{lang}]\n'
            f'🎟 {slot["ticket_name"][:50]}\n'
            f'💶 €{slot["total"]}  recapId={slot["recap_id"]}\n\n'
            f'Re-recapping every {RE_RECAP_INTERVAL//60} min via browser.'
        )

        log('─' * 60)
        log(f'Held! Re-recapping every {RE_RECAP_INTERVAL//60} min. Close window or Ctrl+C to stop.')
        log('─' * 60)

        # ── Re-recap loop ─────────────────────────────────────────────────
        try:
            while True:
                await asyncio.sleep(RE_RECAP_INTERVAL)

                elapsed_min = int((time.time() - hold_start) / 60)
                log(f'⏰ {elapsed_min} min elapsed — re-recapping #{recap_count + 1}...')

                new_slot = await find_and_recap_browser(page, date, visitors, lang, tag)

                if new_slot:
                    recap_count += 1
                    log(f'✅ Re-recap #{recap_count} OK | recapId={new_slot["recap_id"]} | {elapsed_min} min total')
                    tg(
                        f'✅ <b>Re-recap #{recap_count}</b> — still holding!\n'
                        f'📅 {date}  🕐 {slot["time"]}  👥 {visitors}v\n'
                        f'⏱ Held for <b>{elapsed_min} minutes</b>\n'
                        f'🔑 recapId={new_slot["recap_id"]}'
                    )
                else:
                    elapsed_min = int((time.time() - hold_start) / 60)
                    log(f'❌ Re-recap FAILED after {elapsed_min} min | {recap_count} successful re-recaps')
                    tg(
                        f'❌ <b>Hold LOST after {elapsed_min} minutes</b>\n'
                        f'📅 {date}  🕐 {slot["time"]}  👥 {visitors}v\n'
                        f'📊 Successful re-recaps: {recap_count}\n'
                        f'Browser session died at {elapsed_min} min.'
                    )
                    break

        except (KeyboardInterrupt, asyncio.CancelledError):
            elapsed_min = int((time.time() - hold_start) / 60)
            log(f'\n⏹ Stopped after {elapsed_min} min | {recap_count} re-recaps')
            tg(
                f'⏹ <b>Hold test stopped</b>\n'
                f'📅 {date}  🕐 {slot["time"]}  👥 {visitors}v\n'
                f'⏱ Held for <b>{elapsed_min} minutes</b>\n'
                f'📊 Re-recaps: {recap_count}'
            )

        await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--date',     default='15/06/2026')
    parser.add_argument('--visitors', type=int, default=2)
    parser.add_argument('--lang',     default='ENG')
    parser.add_argument('--type',     default='guided', choices=['guided', 'standard'])
    args = parser.parse_args()

    asyncio.run(main(args.date, args.visitors, args.lang, args.type))
