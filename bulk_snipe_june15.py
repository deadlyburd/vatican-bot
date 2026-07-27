
"""
Bulk Vatican Snipe — June 15, 2026
====================================
Books 100 tickets for the participant list across time slots 08:00–10:00.
Groups participants into bookings of 2, classifies adult vs child/student.

Vatican ticket types (June 15, 2026 cutoff = 18 years old):
  Biglietto Intero  (id:60, €20) — born before 15/06/2008
  Biglietto Ridotto (id:61, €10) — born on/after 15/06/2008 (under 18)

Run:
    python bulk_snipe_june15.py
    python bulk_snipe_june15.py --dry-run   # just show groups, no browser
"""
import asyncio
import sys
import os
import time
import json
import requests
import argparse
import warnings
import subprocess
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

warnings.filterwarnings('ignore', category=ResourceWarning)

# ── CONFIG ────────────────────────────────────────────────────────────────────
TARGET_DATE   = '15/06/2026'
VISIT_DATE_ISO = date(2026, 6, 15)
TIME_SLOTS    = ['08:00', '08:30', '09:00', '09:30', '10:00']  # rotate through these

# Booking strategy: try 6 first, then fall back to smaller groups
MAX_GROUP_SIZES = [6, 4, 3, 2, 1]
MAX_GUIDED_TICKETS = 20   # up to 20 tickets via guided tours (tag: MV-Visite-Guidate)

VATICAN_BASE  = 'https://tickets.museivaticani.va'
CHROME_PATH   = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
CHROME_PROFILE = os.path.join(os.path.expanduser('~'), 'vatican_bulk_profile')
USER_AGENT    = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

# Representative (manager) — use first adult in each group
REP_EMAIL    = 'mario.rossi@example.com'
REP_PHONE    = '3401234567'
REP_CITY     = 'Roma'
REP_COUNTRY  = 'Italia'
REP_GENDER   = 'M'

# Card details
CARD = {
    'holder': 'MARIO ROSSI',
    'number': '',    # ← fill your real card
    'expiry': '12/28',
    'cvv':    '',    # ← fill your real CVV
}
AUTO_PAY = True

H = {'Accept': 'application/json, text/plain, */*',
     'X-Requested-With': 'XMLHttpRequest',
     'Referer': f'{VATICAN_BASE}/', 'User-Agent': USER_AGENT}

# ── PARTICIPANT LIST (from PDF) ───────────────────────────────────────────────
# Format: (last_name, first_name, birthdate DD/MM/YYYY)
PARTICIPANTS_RAW = [
    ('M Willits',          'Lashae',      '09/07/1980'),
    ('Hoops',              'Sandra',      '21/01/1957'),
    ('Kaliszak',           'Scott',       '15/09/1993'),
    ('Kriel',              'Krista',      '09/12/1969'),
    ('Allen',              'Mary',        '16/09/2010'),
    ('Basom',              'Blake',       '28/03/1975'),
    ('Basom',              'Emmett',      '06/08/2015'),
    ('Basom',              'Jennifer',    '15/10/1978'),
    ('Basom',              'Landon',      '21/08/2011'),
    ('Brewster',           'Nolan',       '16/03/2011'),
    ('Budney',             'Julie',       '22/08/2009'),
    ('Camalier',           'Cohen',       '11/06/2009'),
    ('Camalier',           'Juniper',     '11/06/2009'),
    ('Cameron Jr',         'John',        '01/07/1974'),
    ('Cameron',            'Jennifer',    '18/08/1977'),
    ('Cameron',            'Lindsay',     '20/10/2008'),
    ('Cameron',            'Zachary',     '11/01/2007'),
    ('Capewell',           'Christopher', '28/04/1977'),
    ('Capewell',           'Eric',        '30/06/2010'),
    ('Capewell',           'Savannah',    '23/10/2012'),
    ('Chuckalovcak',       'Amelia',      '19/05/2010'),
    ('Clites',             'Adalynn',     '01/04/2011'),
    ('Coeyman',            'Chase',       '05/09/2009'),
    ('Cowan',              'Andrew',      '10/08/2013'),
    ('Cowan',              'Caleigh',     '21/06/2010'),
    ('Cowan',              'Christopher', '12/07/1979'),
    ('Cowan',              'Molly',       '17/02/1979'),
    ('Cromartie',          'Caelyn',      '23/08/2010'),
    ('Deguchi',            'Ryan',        '17/08/2009'),
    ('Devulapalli',        'Vaishnavi',   '04/08/2010'),
    ('Dietrich',           'Levi',        '24/12/2010'),
    ('Fitzkee',            'Gabriella',   '01/10/2010'),
    ('Fox',                'Melanie',     '07/11/1979'),
    ('Glantz',             'Carlee',      '28/09/2010'),
    ('Glantz',             'Mandi',       '12/01/1981'),
    ('Goldman-Smith',      'Ian',         '24/10/2009'),
    ('Gonzales',           'Allura',      '07/02/2011'),
    ('Gonzales',           'Kerri',       '22/12/1981'),
    ('Gray',               'Lydia',       '06/06/2007'),
    ('Gutekunst',          'Julianna',    '16/11/2007'),
    ('Hernandez-Hinojosa', 'Lizbeth',     '26/02/2008'),
    ('Jones',              'Linda',       '29/06/1951'),
    ('Kriel',              'Daniel',      '08/06/1972'),
    ('Lake III',           'Larry',       '23/06/1984'),
    ('Lake',               'Sarah',       '28/06/1988'),
    ('Landers',            'Maile',       '10/05/1980'),
    ('Lasher',             'Caroline',    '04/04/2008'),
    ('Pacifico',           'Andrea',      '19/10/1978'),
    ('Pacifico',           'Scott',       '25/07/1980'),
    ('Querry',             'Eric',        '04/06/1970'),
    ('Querry',             'Katharine',   '04/08/1970'),
    ('Ratchford',          'Kathleen',    '07/11/2007'),
    ('Ruth',               'Jennifer',    '01/04/1972'),
    ('Salla',              'Jennifer',    '09/04/1979'),
    ('Shoulders',          'Vivian',      '18/10/2007'),
    ('Thach',              'Ivana',       '03/01/2008'),
    ('Tillman-Cromartie',  'Danielle',    '12/05/1979'),
    ('Willits',            'Cynthia',     '17/08/1955'),
    ('Willits',            'Joshua',      '12/02/1980'),
    ('Sartorius',          'Joseph',      None),  # no birthdate in PDF
]


def parse_dob(dob_str):
    """Parse DD/MM/YYYY → date object. Returns None if missing."""
    if not dob_str:
        return None
    try:
        d, m, y = dob_str.split('/')
        return date(int(y), int(m), int(d))
    except Exception:
        return None

def is_adult(dob):
    """Adult = 18+ on June 15, 2026."""
    if dob is None:
        return True  # assume adult if unknown
    cutoff = date(2008, 6, 15)
    return dob < cutoff

def ticket_type(dob):
    """Returns (ticket_id, ticket_name, price)."""
    if is_adult(dob):
        return (60, 'Biglietto Intero', 20)
    else:
        return (61, 'Biglietto Ridotto', 10)

def dob_to_iso(dob):
    """Convert date to Vatican ISO format (day before at 23:00 UTC)."""
    if dob is None:
        return '1980-01-01T23:00:00.000Z'
    prev = dob - timedelta(days=1)
    return prev.strftime('%Y-%m-%dT23:00:00.000Z')

def dob_to_display(dob):
    """DD/MM/YYYY for the calendar picker."""
    if dob is None:
        return '01/01/1980'
    return dob.strftime('%d/%m/%Y')

# ── Build participant objects ──────────────────────────────────────────────────
PARTICIPANTS = []
for last, first, dob_raw in PARTICIPANTS_RAW:
    dob = parse_dob(dob_raw)
    tid, tname, price = ticket_type(dob)
    PARTICIPANTS.append({
        'last_name':  last,
        'first_name': first,
        'dob':        dob,
        'dob_raw':    dob_raw or 'unknown',
        'ticket_id':  tid,
        'ticket_name': tname,
        'price':      price,
        'is_adult':   is_adult(dob),
    })

# ── Group into bookings of GROUP_SIZE ─────────────────────────────────────────
def make_groups(participants):
    """
    Group participants greedily: try 6 first, then 4, 3, 2, 1.
    Each group must have at least 1 adult as representative.
    """
    remaining = list(participants)
    groups = []
    while remaining:
        # Try largest group size first
        placed = False
        for size in MAX_GROUP_SIZES:
            if len(remaining) >= size:
                chunk = remaining[:size]
                # Ensure at least 1 adult
                adults = [p for p in chunk if p['is_adult']]
                if not adults and size > 1:
                    # Swap in an adult from later in the list
                    for j in range(size, len(remaining)):
                        if remaining[j]['is_adult']:
                            remaining[0], remaining[j] = remaining[j], remaining[0]
                            chunk = remaining[:size]
                            break
                groups.append(chunk)
                remaining = remaining[size:]
                placed = True
                break
        if not placed:
            # Take whatever is left
            groups.append(remaining)
            remaining = []
    return groups

GROUPS = make_groups(PARTICIPANTS)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def print_summary():
    adults   = sum(1 for p in PARTICIPANTS if p['is_adult'])
    children = sum(1 for p in PARTICIPANTS if not p['is_adult'])
    total_cost = sum(p['price'] for p in PARTICIPANTS) + len(PARTICIPANTS) * 5
    group_sizes = [len(g) for g in GROUPS]
    print(f"\n{'='*60}")
    print(f"  PARTICIPANT SUMMARY — June 15, 2026")
    print(f"{'='*60}")
    print(f"  Total participants : {len(PARTICIPANTS)}")
    print(f"  Adults (Intero €20): {adults}")
    print(f"  Children (Ridotto €10): {children}")
    print(f"  Bookings           : {len(GROUPS)} groups {group_sizes}")
    print(f"  Max guided tickets : {MAX_GUIDED_TICKETS}")
    print(f"  Time slots         : {TIME_SLOTS}")
    print(f"  Est. total cost    : €{total_cost} (incl. €5 service fee each)")
    print(f"\n  Groups:")
    for i, g in enumerate(GROUPS):
        slot = TIME_SLOTS[i % len(TIME_SLOTS)]
        names = ', '.join(f"{p['first_name']} {p['last_name']} ({'A' if p['is_adult'] else 'C'})" for p in g)
        print(f"  [{i+1:2d}] {slot} | {len(g)}pax | {names}")
    print(f"{'='*60}\n")


# ── Find available slot for a given time ──────────────────────────────────────
def find_slot_for_time(target_time, visitors, guided=False):
    """Try to find a slot. Returns (slot_dict, actual_visitors) or (None, 0)."""
    tag = 'MV-Visite-Guidate' if guided else 'MV-Biglietti'
    s = requests.Session()
    # Try requested visitors first, then fall back
    for v in [visitors] + [x for x in MAX_GROUP_SIZES if x != visitors and x <= visitors]:
        try:
            r = s.get(f'{VATICAN_BASE}/api/search/resultPerTag', params={
                'lang': 'it', 'visitorNum': str(v), 'visitDate': TARGET_DATE,
                'area': '1', 'who': '', 'page': '0', 'tag': tag
            }, headers=H, timeout=10)
            if r.status_code != 200:
                continue
            visits = r.json().get('visits', [])
            if guided:
                ticket = next((x for x in visits
                               if 'musei vaticani' in x.get('name','').lower()
                               and x.get('availability') != 'SOLD_OUT'), None)
            else:
                ticket = next((x for x in visits
                               if 'musei vaticani' in x.get('name','').lower()
                               and 'ingresso' in x.get('name','').lower()
                               and x.get('availability') != 'SOLD_OUT'), None)
            if not ticket:
                continue
            tid = str(ticket['id'])
            r2 = s.get(f'{VATICAN_BASE}/api/visit/timeavail', params={
                'lang': 'it', 'visitLang': '', 'visitTypeId': tid,
                'visitorNum': str(v), 'visitDate': TARGET_DATE,
            }, headers=H, timeout=10)
            if r2.status_code != 200:
                continue
            timetable = r2.json().get('timetable', [])
            # Try exact time first
            slots = [sl for sl in timetable
                     if sl.get('availability') == 'AVAILABLE' and sl.get('time') == target_time]
            if not slots:
                # Any available 08:00-10:00
                slots = [sl for sl in timetable
                         if sl.get('availability') == 'AVAILABLE'
                         and '08:00' <= sl.get('time','') <= '10:00']
            if slots:
                best = slots[0]
                return ({'date': TARGET_DATE, 'slot_id': str(best['id']),
                         'slot_time': best['time'], 'ticket_id': tid, 'visitors': v}, v)
        except Exception as e:
            log(f"  Slot lookup error (v={v}): {e}")
    return None, 0


# ── Browser booking for one group ─────────────────────────────────────────────
async def book_group(group_idx, group, slot, dry_run=False):
    import nodriver as uc

    visitors  = len(group)
    rep       = group[0]  # first person = representative
    date_str  = slot['date']
    slot_time = slot['slot_time']
    tid       = slot['ticket_id']

    log(f"\n[Group {group_idx+1}] {slot_time} | {visitors} people | rep: {rep['first_name']} {rep['last_name']}")
    for p in group:
        log(f"  {'Adult' if p['is_adult'] else 'Child'}: {p['first_name']} {p['last_name']} ({p['dob_raw']})")

    if dry_run:
        log("  [DRY RUN] Skipping browser")
        return True

    rome = ZoneInfo('Europe/Rome')
    d, m, y = date_str.split('/')
    ts = int(datetime(int(y), int(m), int(d), 0, 0, 0, tzinfo=rome).timestamp() * 1000)
    entry_url = f'{VATICAN_BASE}/home/fromtag/{visitors}/{ts}/MV-Biglietti/1'

    # Kill stale Chrome
    subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe', '/T'], capture_output=True)
    await asyncio.sleep(0.5)
    for lf in ['lockfile', 'SingletonLock', 'SingletonCookie']:
        p_path = os.path.join(CHROME_PROFILE, lf)
        try:
            if os.path.exists(p_path): os.remove(p_path)
        except Exception:
            pass

    browser = await uc.start(
        user_data_dir=CHROME_PROFILE,
        browser_executable_path=CHROME_PATH,
        headless=False, lang='it-IT', no_sandbox=True,
    )
    tab = browser.main_tab

    async def js(code): return await tab.evaluate(code)
    async def wait(s): await tab.sleep(s)

    async def fill(sel, val):
        safe = str(val).replace('\\', '\\\\').replace('`', '\\`')
        await js(f"""
            (() => {{
                const el = document.querySelector(`{sel}`);
                if (!el) return;
                el.focus(); el.value = ''; el.value = `{safe}`;
                el.dispatchEvent(new Event('input',  {{bubbles:true}}));
                el.dispatchEvent(new Event('change', {{bubbles:true}}));
                el.blur();
            }})()
        """)

    try:
        # [1] Navigate
        log(f"  [1] {entry_url}")
        await tab.get(entry_url)
        for _ in range(30):
            c = await js("document.querySelectorAll(\"[data-cy^='bookTicket_']\").length")
            if c and int(c) > 0: break
            no_v = await js("(document.body?.innerText||'').includes('Nessuna visita')")
            if no_v:
                await wait(1); await tab.get(entry_url); await wait(2); break
            await wait(0.5)
        await wait(0.5)

        # [2] Fresh ticket ID
        r = requests.get(f'{VATICAN_BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(visitors), 'visitDate': date_str,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=H, timeout=10)
        visits = r.json().get('visits', []) if r.status_code == 200 else []
        t = next((v for v in visits if 'musei vaticani' in v.get('name','').lower()
                  and 'ingresso' in v.get('name','').lower()), None)
        if t: tid = str(t['id'])

        # [3] PRENOTA
        dom_tid = None
        for _ in range(10):
            dom_tid = await js("""
                (() => {
                    for (const card of document.querySelectorAll('[id^="ticket_"]')) {
                        const txt = card.innerText.toLowerCase();
                        if (txt.includes('musei vaticani') && txt.includes('ingresso')) {
                            const btn = card.querySelector("[data-cy^='bookTicket_']");
                            if (btn) return btn.getAttribute('data-cy').replace('bookTicket_','');
                        }
                    }
                    for (const btn of document.querySelectorAll("[data-cy^='bookTicket_']"))
                        if (btn.innerText.trim()==='PRENOTA') return btn.getAttribute('data-cy').replace('bookTicket_','');
                    return null;
                })()
            """)
            if dom_tid: break
            await wait(0.5)
        if dom_tid: tid = dom_tid
        await js(f"document.querySelector(\"[data-cy='bookTicket_{tid}']\")?.click()")
        await wait(2)

        # [4] Quantity
        for _ in range(10):
            has = await js("!!(document.querySelector('select')||document.querySelector(\"[data-cy='ticketQuantity']\"))")
            if has: break
            await wait(0.4)
        qty = await js(f"""
            (() => {{
                const sel = document.querySelector('select');
                if (sel) {{ sel.value='{visitors}'; sel.dispatchEvent(new Event('change',{{bubbles:true}})); return 'select'; }}
                const el = document.querySelector("[data-cy='ticketQuantity']");
                if (el) {{ el.click(); return 'dropdown'; }}
                return null;
            }})()
        """)
        if qty == 'dropdown':
            await wait(0.8)
            await js(f"""
                (() => {{
                    const items = Array.from(document.querySelectorAll("[data-cy='ticketQuantitySection']"));
                    for (const it of items) {{
                        if (it.innerText.trim()==='{visitors}'||it.innerText.trim().startsWith('{visitors} ')) {{ it.click(); return; }}
                    }}
                    if (items.length>={visitors}) items[{visitors}-1].click();
                    else if (items.length) items[items.length-1].click();
                }})()
            """)
        await wait(1.5)

        # [5] Time slot
        target_mins = int(slot_time.split(':')[0])*60 + int(slot_time.split(':')[1])
        for _ in range(20):
            c = await js("document.querySelectorAll(\"[data-cy='time']\").length")
            if c and int(c) > 0: break
            await wait(0.5)
        await js(f"""
            (() => {{
                const cells = Array.from(document.querySelectorAll("[data-cy='time']"));
                for (const cell of cells) {{
                    const txt = cell.innerText.trim();
                    if (txt==='{slot_time}'||txt.startsWith('{slot_time}')) {{ cell.scrollIntoView(); cell.click(); return; }}
                }}
                const target={target_mins};
                let best=null,bestDiff=9999;
                for (const cell of cells) {{
                    const parts=cell.innerText.trim().split('\\n')[0].split(':');
                    if (parts.length!==2) continue;
                    const mins=parseInt(parts[0])*60+parseInt(parts[1]);
                    const diff=Math.abs(mins-target);
                    if (diff<bestDiff) {{ bestDiff=diff; best=cell; }}
                }}
                if (best) {{ best.scrollIntoView(); best.click(); }}
            }})()
        """)
        await wait(2)

        # [6] PROCEDI
        for _ in range(10):
            has = await js("!!(document.querySelector(\"[data-cy='bookVisit']\"))")
            if has: break
            await wait(0.5)
        await js("(() => { const b=document.querySelector(\"[data-cy='bookVisit']\")||Array.from(document.querySelectorAll('button')).find(b=>/PROCEDI/i.test(b.textContent)); if(b) b.click(); })()")
        await wait(5)

        # [7] Wait for form
        for _ in range(60):
            el = await js("document.querySelector(\"[data-cy='managerSurname']\")?.tagName")
            if el: break
            await wait(0.5)

        # [8] Fill form with representative (first person in group)
        rep_dob = rep['dob']
        rep_dob_display = dob_to_display(rep_dob)
        rep_dob_iso = dob_to_iso(rep_dob)
        rep_bm_num = rep_dob.strftime('%m') if rep_dob else '01'
        rep_by = rep_dob.strftime('%Y') if rep_dob else '1980'
        rep_bd = rep_dob.strftime('%d') if rep_dob else '01'
        month_names = {'01':'GEN','02':'FEB','03':'MAR','04':'APR','05':'MAG','06':'GIU',
                       '07':'LUG','08':'AGO','09':'SET','10':'OTT','11':'NOV','12':'DIC'}
        rep_bm = month_names.get(rep_bm_num, 'GEN')

        await fill("[data-cy='managerSurname']",     rep['last_name'])
        await fill("[data-cy='managerName']",         rep['first_name'])
        await fill("[data-cy='managerCity']",         REP_CITY)
        await fill("[data-cy='managerEmail']",        REP_EMAIL)
        await fill("[data-cy='managerConfirmEmail']", REP_EMAIL)

        # Phone — type digit by digit
        phone_el = await tab.query_selector("[data-cy='managerPhone']")
        if phone_el:
            await phone_el.click(); await wait(0.2)
            await js("(() => { const el=document.querySelector(\"[data-cy='managerPhone']\"); if(el){el.value='';el.dispatchEvent(new Event('input',{bubbles:true}));} })()")
            for ch in REP_PHONE:
                await phone_el.send_keys(ch); await wait(0.03)
            await js("(() => { const el=document.querySelector(\"[data-cy='managerPhone']\"); if(el){el.dispatchEvent(new Event('change',{bubbles:true}));el.blur();} })()")
        await wait(0.3)

        # Gender
        await js("document.querySelector(\"[data-cy='managerSex']\")?.click()")
        await wait(0.3)
        await js("document.querySelector(\"[data-cy='managerSexSection']\")?.click()")
        await wait(0.3)

        # Country
        await js("document.querySelector(\"[data-cy='managerCountry']\")?.click()")
        await wait(0.3)
        await js("(() => { const s=document.querySelector('#searchInput_country'); if(s){s.value='Ital';s.dispatchEvent(new Event('input',{bubbles:true}));} })()")
        await wait(0.4)
        await js("(() => { const items=Array.from(document.querySelectorAll(\"[data-cy='managerCountrySection']\")); const it=items.find(e=>/^ital/i.test(e.innerText.trim())); if(it) it.click(); else if(items[0]) items[0].click(); })()")
        await wait(0.3)

        # Birth date — direct injection
        set_ok = await js(f"""
            (() => {{
                const inp = document.querySelector("[data-cy='dateCalendar']");
                if (!inp) return false;
                inp.removeAttribute('readonly');
                inp.focus(); inp.value = '{rep_dob_display}';
                inp.dispatchEvent(new Event('input',  {{bubbles:true}}));
                inp.dispatchEvent(new Event('change', {{bubbles:true}}));
                inp.dispatchEvent(new KeyboardEvent('keydown', {{key:'Enter',bubbles:true}}));
                inp.setAttribute('readonly','true');
                return inp.value;
            }})()
        """)
        await wait(0.4)
        if not set_ok or set_ok == '':
            # Calendar fallback
            await js("document.querySelector(\"mat-datepicker-toggle button[aria-label='Open calendar']\")?.click()")
            await wait(0.8)
            for _ in range(2):
                multi = await js("document.querySelectorAll('.mat-calendar-body-cell').length > 12")
                if multi: break
                await js("document.querySelector('button.mat-calendar-period-button')?.click()")
                await wait(0.4)
            for _ in range(30):
                found = await js(f"""
                    (() => {{
                        const cells=Array.from(document.querySelectorAll('.mat-calendar-body-cell'));
                        const yr=cells.find(c=>c.textContent.trim()==='{rep_by}');
                        if(yr){{yr.click();return true;}}
                        document.querySelector('.mat-calendar-previous-button')?.click();
                        return false;
                    }})()
                """)
                await wait(0.3)
                if found: break
            await wait(0.4)
            await js(f"(() => {{ const cells=Array.from(document.querySelectorAll('.mat-calendar-body-cell')); const mo=cells.find(c=>c.textContent.trim().toUpperCase()==='{rep_bm}'); if(mo) mo.click(); }})()")
            await wait(0.4)
            bd_s = rep_bd.lstrip('0') or '1'
            await js(f"(() => {{ const cells=Array.from(document.querySelectorAll('span.mat-calendar-body-cell-content')); const day=cells.find(c=>c.textContent.trim()==='{bd_s}'); if(day) day.click(); }})()")
            await wait(0.3)

        # Language
        await js("document.querySelector(\"[data-cy='managerLanguage']\")?.click()")
        await wait(0.3)
        await js("document.querySelector(\"[data-cy='managerLanguageSection']\")?.click()")
        await wait(0.3)

        # Participants
        for i, p in enumerate(group):
            if i > 0:
                await js(f"(() => {{ const el=document.querySelector('#participantElement_{i} div.tw-flex-grow > div'); if(el) el.click(); }})()")
                await wait(0.5)
            await fill(f"#participantSurname_{i}", p['last_name'])
            await fill(f"#participantName_{i}",    p['first_name'])

        # GDPR checkboxes
        cb0 = await js("document.querySelectorAll('input[type=\"checkbox\"]')[0]?.checked")
        if cb0 is False:
            await js("document.querySelectorAll('input[type=\"checkbox\"]')[0]?.click()")
            await wait(1.5)
            await js("(() => { const c=document.querySelector(\"[data-cy='purchase-rules-close-btn']\")||Array.from(document.querySelectorAll('button')).find(b=>/chiudi|close/i.test(b.textContent)); if(c) c.click(); })()")
            await wait(1)
        cb1 = await js("document.querySelectorAll('input[type=\"checkbox\"]')[1]?.checked")
        if cb1 is False:
            await js("document.querySelectorAll('input[type=\"checkbox\"]')[1]?.click()")
        await wait(0.5)

        # Turnstile check
        for _ in range(30):
            token = await js("(() => { const inp=document.querySelector('[name=\"cf-turnstile-response\"]'); return (inp&&inp.value&&inp.value.length>10)?'ok':null; })()")
            if token: break
            await wait(0.5)

        # [9] BUY
        await js("""
            (() => {
                const byId=document.querySelector("button#form-submit[type='submit'].btn-submit");
                if(byId&&!byId.disabled){byId.scrollIntoView();byId.click();return;}
                const submits=Array.from(document.querySelectorAll("button[type='submit']")).filter(b=>!b.disabled);
                if(submits.length) submits[submits.length-1].click();
            })()
        """)

        # [10] Wait for epay
        epay_url = ''
        for _ in range(120):
            await wait(0.5)
            try:
                cur = await js("window.location.href")
                if cur and 'epay' in cur:
                    epay_url = cur
                    log(f"  ✅ epay: {epay_url[:80]}")
                    break
            except Exception:
                pass

        if not epay_url:
            log(f"  ❌ No epay redirect for group {group_idx+1}")
            return False

        # [11] Fill epay
        await wait(3)

        async def epay_fill(fid, val):
            safe = str(val).replace('`','\\`')
            await js(f"""
                (() => {{
                    const el=document.querySelector('#{fid}');
                    if(!el) return;
                    el.focus(); el.value=`{safe}`;
                    el.dispatchEvent(new Event('input',{{bubbles:true}}));
                    el.dispatchEvent(new Event('change',{{bubbles:true}}));
                    el.blur();
                }})()
            """)

        card_first, *rest = CARD['holder'].split(' ', 1)
        card_last = rest[0] if rest else card_first
        await epay_fill('name',        card_first)
        await epay_fill('surname',     card_last)
        await epay_fill('email',       REP_EMAIL)
        await epay_fill('repeatEmail', REP_EMAIL)
        await wait(0.3)

        if CARD['number']:
            iframe_el = await tab.query_selector('iframe[name*="cardNumber"],iframe[id*="cardNumber"]')
            if iframe_el:
                await iframe_el.click(); await wait(0.5)
                for ch in CARD['number']:
                    await iframe_el.send_keys(ch); await wait(0.05)
                await wait(0.3)

        if CARD['cvv']:
            cvv_el = await tab.query_selector('iframe[name*="cvv"],iframe[id*="cvv"]')
            if cvv_el:
                await cvv_el.click(); await wait(0.5)
                for ch in CARD['cvv']:
                    await cvv_el.send_keys(ch); await wait(0.05)
                await cvv_el.send_keys('\t')
                await wait(0.3)

        if CARD['expiry']:
            exp_m, exp_y = CARD['expiry'].split('/')
            exp_m = exp_m.strip().zfill(2)
            exp_y = ('20'+exp_y.strip()) if len(exp_y.strip())==2 else exp_y.strip()
            await js("document.querySelectorAll('app-dropdown')[0]?.querySelector('.select__box--selectedValue')?.click()")
            await wait(0.4)
            await js(f"(() => {{ const items=Array.from(document.querySelectorAll('.select__list--item span')); const mo=items.find(e=>e.textContent.trim()==='{exp_m}'); if(mo) mo.click(); }})()")
            await wait(0.3)
            await js("document.querySelectorAll('app-dropdown')[1]?.querySelector('.select__box--selectedValue')?.click()")
            await wait(0.4)
            await js(f"(() => {{ const items=Array.from(document.querySelectorAll('.select__list--item span')); const yr=items.find(e=>e.textContent.trim()==='{exp_y}'); if(yr) yr.click(); }})()")
            await wait(0.3)

        await js("(() => { const cb=document.querySelector('#mat-checkbox-1-input'); if(cb&&!cb.checked) cb.click(); })()")
        await wait(0.3)

        if AUTO_PAY:
            await js("(() => { document.body.click(); document.activeElement?.blur(); })()")
            await wait(0.5)
            await js("""
                (() => {
                    const byId=document.querySelector("button#form-submit[type='submit'].btn-submit");
                    if(byId&&!byId.disabled){byId.scrollIntoView();byId.focus();byId.click();return;}
                    const byText=Array.from(document.querySelectorAll("button[type='submit']")).find(b=>b.textContent.includes('Paga')&&!b.disabled);
                    if(byText){byText.scrollIntoView();byText.focus();byText.click();}
                })()
            """)
            log(f"  💳 PAY clicked for group {group_idx+1}")

            # Wait for confirmation
            for _ in range(120):
                await wait(0.5)
                try:
                    cur = await js("window.location.href")
                    if not cur or cur == epay_url: continue
                    if 'feedback/fail' in cur or 'error' in cur:
                        log(f"  ❌ Payment failed: {cur}")
                        return False
                    if any(x in cur for x in ('feedback/success','confirm','success','thank','grazie')):
                        log(f"  ✅ BOOKED! Group {group_idx+1}: {', '.join(p['first_name']+' '+p['last_name'] for p in group)}")
                        return True
                    if cur != epay_url:
                        log(f"  📱 3DS — approve on phone...")
                        for _ in range(240):
                            await wait(0.5)
                            try:
                                cur2 = await js("window.location.href")
                                if 'feedback/success' in (cur2 or '') or 'confirm' in (cur2 or ''):
                                    log(f"  ✅ BOOKED (3DS)! Group {group_idx+1}")
                                    return True
                                if 'feedback/fail' in (cur2 or ''):
                                    log(f"  ❌ 3DS failed")
                                    return False
                            except Exception:
                                pass
                        return False
                except Exception:
                    pass
        else:
            log(f"  AUTO_PAY=False — review browser then click Paga manually")
            await wait(60)

        return True

    except Exception as e:
        log(f"  ❌ Group {group_idx+1} error: {e}")
        import traceback; traceback.print_exc()
        return False
    finally:
        try: await wait(3); browser.stop()
        except: pass


# ── MAIN ─────────────────────────────────────────────────────────────────────
async def main(dry_run=False, start_from=0):
    print_summary()

    if not CARD['number'] and not dry_run:
        print("❌ CARD['number'] is empty — fill in your card details at the top of this file!")
        return

    results = {'success': 0, 'failed': 0, 'skipped': 0}

    for i, group in enumerate(GROUPS):
        if i < start_from:
            log(f"[Group {i+1}] Skipping (start_from={start_from})")
            results['skipped'] += 1
            continue

        slot_time = TIME_SLOTS[i % len(TIME_SLOTS)]
        log(f"\n{'='*50}")
        log(f"Group {i+1}/{len(GROUPS)} | Time: {slot_time} | {len(group)} people")

        if not dry_run:
            slot, actual_v = find_slot_for_time(slot_time, len(group))
            if not slot:
                log(f"  ❌ No slot available for {slot_time} — trying smaller group")
                results['failed'] += 1
                continue
            if actual_v < len(group):
                log(f"  ⚠️  Only {actual_v} spots available, splitting group")
                # Book what we can, push remainder back
                booked_group = group[:actual_v]
                leftover = group[actual_v:]
                GROUPS.insert(i+1, leftover)  # re-queue remainder
                group = booked_group
                slot['visitors'] = actual_v
            log(f"  Slot: {slot['slot_id']} @ {slot['slot_time']} | {actual_v} visitors")
        else:
            slot = {'date': TARGET_DATE, 'slot_id': 'DRY', 'slot_time': slot_time, 'ticket_id': '0', 'visitors': len(group)}

        ok = await book_group(i, group, slot, dry_run=dry_run)
        if ok:
            results['success'] += 1
        else:
            results['failed'] += 1

        if not dry_run and i < len(GROUPS) - 1:
            log(f"  Waiting 10s before next booking...")
            await asyncio.sleep(10)

    print(f"\n{'='*60}")
    print(f"  BULK BOOKING COMPLETE")
    print(f"  ✅ Success : {results['success']}")
    print(f"  ❌ Failed  : {results['failed']}")
    print(f"  ⏭️  Skipped : {results['skipped']}")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run',    action='store_true', help='Show groups without booking')
    parser.add_argument('--start-from', type=int, default=0, help='Resume from group N (0-indexed)')
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, start_from=args.start_from))
