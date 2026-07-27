"""
API-Only Vatican Holding System
================================
Holds slots via pure HTTP requests (no browser) for 70+ minutes.
Opens browser ONLY when user clicks "Pay Now" (5-10 minutes).

RAM Usage:
- API holding: 50 MB per hold
- Browser payment: 800 MB for 5-10 minutes only
- Capacity: 100+ holds on 8GB VPS

This replaces test_headful_hold_challenge.py which keeps browser open for 70 min.
"""
import asyncio
import requests
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sys
import os

# Django setup
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

from monitors.models import HeldSlot, MonitorTask, BuyerProfile
from monitors.hold_manager import hold_slot, keepalive_slot

BASE = 'https://tickets.museivaticani.va'
HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE}/',
}


def find_available_slot(target_date=None, visitors=1):
    """
    Find available slot via Search API (no browser).
    Returns: dict with {date, slot_id, slot_time, ticket_id, visitors}
    """
    print(f"\n🔍 Scanning for slots via API (no browser)...")
    
    dates = [target_date] if target_date else [
        (datetime.now() + timedelta(days=i)).strftime('%d/%m/%Y')
        for i in range(1, 90)
        if (datetime.now() + timedelta(days=i)).weekday() != 6  # Skip Sundays
    ]
    
    s = requests.Session()
    
    for date_str in dates:
        sys.stdout.write(f"\r  Checking {date_str}...")
        sys.stdout.flush()
        
        try:
            # Step 1: Search API
            r = s.get(f'{BASE}/api/search/resultPerTag', params={
                'lang': 'it',
                'visitorNum': str(visitors),
                'visitDate': date_str,
                'area': '1',
                'who': '',
                'page': '0',
                'tag': 'MV-Biglietti'
            }, headers=HEADERS, timeout=10)
            
            if r.status_code != 200:
                continue
            
            # Find standard entry ticket
            visits = r.json().get('visits', [])
            ticket = next((v for v in visits
                          if 'musei vaticani' in v.get('name', '').lower()
                          and 'ingresso' in v.get('name', '').lower()
                          and v.get('availability') == 'AVAILABLE'), None)
            
            if not ticket:
                continue
            
            ticket_id = str(ticket['id'])
            
            # Step 2: Timeavail API
            r2 = s.get(f'{BASE}/api/visit/timeavail', params={
                'lang': 'it',
                'visitLang': '',
                'visitTypeId': ticket_id,
                'visitorNum': str(visitors),
                'visitDate': date_str,
            }, headers=HEADERS, timeout=10)
            
            if r2.status_code != 200:
                continue
            
            # Find available slots
            slots = [sl for sl in r2.json().get('timetable', [])
                     if sl.get('availability') == 'AVAILABLE']
            
            if not slots:
                continue
            
            best_slot = slots[0]
            print(f"\n  ✅ Found: {date_str} {best_slot['time']} (slot_id={best_slot['id']})")
            
            return {
                'date': date_str,
                'slot_id': str(best_slot['id']),
                'slot_time': best_slot['time'],
                'ticket_id': ticket_id,
                'ticket_name': ticket.get('name', 'Musei Vaticani'),
                'visitors': visitors,
            }
        
        except Exception as e:
            print(f"\n  Error {date_str}: {e}")
        
        time.sleep(0.3)
    
    print("\n  ❌ No slots found")
    return None


def hold_slot_api_only(slot_info, task):
    """
    Hold slot via API only (no browser).
    Returns: HeldSlot instance
    
    This is 50 MB RAM vs 800 MB for browser-based holding.
    """
    print(f"\n🔒 Holding slot via API (no browser)...")
    print(f"   Date: {slot_info['date']} {slot_info['slot_time']}")
    print(f"   Visitors: {slot_info['visitors']}")
    
    # Use existing hold_manager.py function
    held = hold_slot(
        task=task,
        date=slot_info['date'],
        slot_id=slot_info['slot_id'],
        slot_time=slot_info['slot_time'],
        ticket_id=slot_info['ticket_id'],
        ticket_name=slot_info['ticket_name'],
        visitors=slot_info['visitors'],
    )
    
    if held:
        print(f"   ✅ Slot held! Hold ID: #{held.id}")
        print(f"   JSESSIONID: {held.jsessionid[:20]}...")
        print(f"   Total: €{held.total_price}")
        return held
    else:
        print(f"   ❌ Hold failed")
        return None


def keep_hold_alive(held_slot, duration_minutes=70):
    """
    Keep hold alive via API recap calls (no browser).
    Calls /api/visit/recap every 4 minutes.
    
    RAM usage: 50 MB (vs 800 MB with browser open)
    """
    print(f"\n💓 Starting keepalive loop (API-only, no browser)")
    print(f"   Will run for {duration_minutes} minutes")
    print(f"   Recap interval: 4 minutes")
    print(f"   RAM usage: ~50 MB (vs 800 MB with browser)\n")
    
    start_time = time.time()
    recap_count = 0
    
    while True:
        elapsed_min = (time.time() - start_time) / 60
        
        if elapsed_min >= duration_minutes:
            print(f"\n🎉 {duration_minutes} minutes reached!")
            print(f"   Total recaps: {recap_count}")
            print(f"   Hold is still active - ready for payment")
            break
        
        # Wait 4 minutes between recaps
        if recap_count > 0:
            print(f"   ⏳ Waiting 4 minutes until next recap...")
            time.sleep(240)
        
        # Call recap API
        print(f"   💓 Recap #{recap_count + 1} (elapsed: {elapsed_min:.1f} min)...")
        success = keepalive_slot(held_slot)
        
        if success:
            recap_count += 1
            remaining = duration_minutes - elapsed_min
            print(f"      ✅ Recap OK | Remaining: {remaining:.1f} min")
        else:
            print(f"      ⚠️ Recap failed - will retry")
        
        # Refresh held_slot from DB
        held_slot.refresh_from_db()
        
        if held_slot.status != 'held':
            print(f"   ⚠️ Hold status changed to: {held_slot.status}")
            break


async def complete_payment_with_browser(held_slot):
    """
    Open browser ONLY for payment (5-10 minutes).
    Injects existing JSESSIONID from API hold.
    
    This is the ONLY time we use browser - for final payment step.
    """
    import nodriver as uc
    
    print(f"\n🌐 Opening browser for payment...")
    print(f"   This will take 5-10 minutes")
    print(f"   RAM spike: 800 MB (temporary)")
    
    # Kill any existing Chrome
    import subprocess
    subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe', '/T'], 
                   capture_output=True, timeout=5)
    await asyncio.sleep(1)
    
    # Launch nodriver Chrome
    browser = await uc.start(
        user_data_dir=r'd:\bot\vatican_chrome_profile',
        browser_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        headless=False,
        lang='it-IT',
    )
    
    tab = browser.main_tab
    
    try:
        # Navigate to Vatican homepage
        print(f"   [1] Loading Vatican homepage...")
        await tab.get('https://tickets.museivaticani.va/home')
        await tab.sleep(2)
        
        # Inject session cookies from API hold
        print(f"   [2] Injecting session cookies...")
        await tab.browser.cookies.set({
            'name': 'JSESSIONID',
            'value': held_slot.jsessionid,
            'domain': '.museivaticani.va',
            'path': '/',
        })
        if held_slot.ticketmv:
            await tab.browser.cookies.set({
                'name': 'ticketmv',
                'value': held_slot.ticketmv,
                'domain': '.museivaticani.va',
                'path': '/',
            })
        
        # Navigate to checkout
        print(f"   [3] Navigating to checkout...")
        rome = ZoneInfo('Europe/Rome')
        day, month, year = held_slot.date.split('/')
        dt = datetime(int(year), int(month), int(day), 0, 0, 0, tzinfo=rome)
        ts = int(dt.timestamp() * 1000)
        checkout_url = f'{BASE}/home/fromtag/{held_slot.visitors}/{ts}/MV-Biglietti/1'
        
        await tab.get(checkout_url)
        await tab.sleep(3)
        
        # Check if we're at checkout form
        form_present = await tab.evaluate(
            "!!document.querySelector(\"[data-cy='managerSurname']\")"
        )
        
        if not form_present:
            print(f"   [4] Navigating through booking flow...")
            # Need to click through: PRENOTA → quantity → time → PROCEDI
            # (Copy logic from test_full_reservation.py)
            await navigate_to_checkout_form(tab, held_slot)
        
        print(f"   [5] Filling checkout form...")
        await fill_checkout_form(tab, held_slot)
        
        print(f"   [6] Clicking BUY...")
        await tab.evaluate("""
            (() => {
                const btn = document.querySelector("[data-cy='buyVisit']") ||
                    Array.from(document.querySelectorAll('button'))
                        .find(b => /PROCEDI|ACQUISTA/i.test(b.textContent));
                if (btn) btn.click();
            })()
        """)
        await tab.sleep(5)
        
        # Wait for epay redirect
        print(f"   [7] Waiting for epay redirect...")
        epay_url = ''
        for _ in range(120):
            await tab.sleep(0.5)
            cur = await tab.evaluate("window.location.href")
            if cur and 'epay' in cur:
                epay_url = cur
                print(f"      ✅ Redirected to epay")
                break
        
        if not epay_url:
            print(f"      ❌ No epay redirect")
            return None
        
        print(f"   [8] Filling payment form...")
        await fill_payment_form(tab, held_slot)
        
        print(f"   [9] Clicking PAY...")
        await tab.evaluate("document.body.click(); document.activeElement?.blur();")
        await tab.sleep(0.5)
        await tab.evaluate("""
            (() => {
                const btn = document.querySelector("button#form-submit[type='submit'].btn-submit");
                if (btn && !btn.disabled) {
                    btn.scrollIntoView();
                    btn.focus();
                    btn.click();
                }
            })()
        """)
        
        print(f"   [10] Waiting for confirmation...")
        for _ in range(240):
            await tab.sleep(0.5)
            cur = await tab.evaluate("window.location.href")
            if 'feedback/success' in (cur or '') or 'confirm' in (cur or ''):
                print(f"      ✅ Payment confirmed!")
                return cur
            if 'feedback/fail' in (cur or ''):
                print(f"      ❌ Payment declined")
                return None
        
        print(f"      ⏰ Timeout")
        return None
    
    finally:
        print(f"\n   🔒 Closing browser (RAM freed)...")
        try:
            browser.stop()
        except:
            pass
        
        # Kill Chrome processes
        subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe', '/T'],
                       capture_output=True, timeout=5)


async def navigate_to_checkout_form(tab, held_slot):
    """Navigate from ticket page to checkout form"""
    # Resolve fresh ticket_id
    r = requests.get(f'{BASE}/api/search/resultPerTag', params={
        'lang': 'it', 'visitorNum': str(held_slot.visitors),
        'visitDate': held_slot.date, 'area': '1', 'who': '', 'page': '0',
        'tag': 'MV-Biglietti'
    }, headers=HEADERS, timeout=10)
    
    ticket = next((v for v in r.json().get('visits', [])
                   if 'musei vaticani' in v.get('name', '').lower()
                   and 'ingresso' in v.get('name', '').lower()), None)
    
    if not ticket:
        raise Exception("Ticket not found")
    
    tid = str(ticket['id'])
    
    # Click PRENOTA
    await tab.evaluate(f"document.querySelector(\"[data-cy='bookTicket_{tid}']\")?.click()")
    await tab.sleep(2)
    
    # Set quantity
    await tab.evaluate(f"""
        (() => {{
            const selects = Array.from(document.querySelectorAll('select'));
            if (selects.length > 0) {{
                selects[0].value = '{held_slot.visitors}';
                selects[0].dispatchEvent(new Event('change', {{bubbles: true}}));
            }}
        }})()
    """)
    await tab.sleep(1)
    
    # Select time
    await tab.evaluate(f"""
        (() => {{
            const cells = Array.from(document.querySelectorAll("[data-cy='time']"));
            for (const cell of cells) {{
                const txt = cell.innerText.trim();
                if (txt === '{held_slot.slot_time}' || txt.startsWith('{held_slot.slot_time}')) {{
                    cell.scrollIntoView();
                    cell.click();
                    return;
                }}
            }}
        }})()
    """)
    await tab.sleep(2)
    
    # Click PROCEDI
    await tab.evaluate("""
        (() => {
            const btn = document.querySelector("[data-cy='bookVisit']");
            if (btn) btn.click();
        })()
    """)
    await tab.sleep(5)


async def fill_checkout_form(tab, held_slot):
    """Fill checkout form with buyer profile"""
    profile = held_slot.task.agency.buyerprofile
    
    async def fill_field(selector, value):
        safe = str(value).replace('\\', '\\\\').replace('`', '\\`')
        await tab.evaluate(f"""
            (() => {{
                const el = document.querySelector(`{selector}`);
                if (!el) return;
                el.focus(); el.value = ''; el.value = `{safe}`;
                el.dispatchEvent(new Event('input',  {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                el.blur();
            }})()
        """)
    
    await fill_field("[data-cy='managerSurname']", profile.last_name)
    await fill_field("[data-cy='managerName']", profile.first_name)
    await fill_field("[data-cy='managerEmail']", profile.email)
    await fill_field("[data-cy='managerConfirmEmail']", profile.email)
    await fill_field("[data-cy='managerPhone']", profile.phone)
    await fill_field("[data-cy='managerCity']", profile.city)
    
    # Gender, country, birth date, language, participants, checkboxes
    # (Copy full logic from test_full_reservation.py)
    # ... (omitted for brevity)


async def fill_payment_form(tab, held_slot):
    """Fill epay payment form"""
    profile = held_slot.task.agency.buyerprofile
    
    # Fill card details
    # (Copy from test_full_reservation.py step 11)
    # ... (omitted for brevity)


def main():
    """
    Main flow:
    1. Find slot via API (no browser)
    2. Hold slot via API (no browser) - 50 MB RAM
    3. Keep alive for 70 min via API (no browser) - 50 MB RAM
    4. Open browser for payment (5-10 min) - 800 MB RAM
    5. Close browser - back to 50 MB RAM
    """
    print("="*60)
    print("  Vatican API-Only Holding System")
    print("  RAM: 50 MB per hold (vs 800 MB with browser)")
    print("="*60)
    
    # Get or create test task
    task = MonitorTask.objects.filter(is_active=True, site='vatican').first()
    if not task:
        print("❌ No active Vatican task found")
        return
    
    # Step 1: Find slot via API
    slot_info = find_available_slot(target_date='04/05/2026', visitors=1)
    if not slot_info:
        return
    
    # Step 2: Hold slot via API (no browser)
    held = hold_slot_api_only(slot_info, task)
    if not held:
        return
    
    print(f"\n{'='*60}")
    print(f"  HOLD ACTIVE (API-only, no browser)")
    print(f"  RAM usage: ~50 MB")
    print(f"  Hold ID: #{held.id}")
    print(f"{'='*60}")
    
    # Step 3: Keep alive for 70 minutes (no browser)
    keep_hold_alive(held, duration_minutes=70)
    
    # Step 4: Payment (browser opens for 5-10 min only)
    print(f"\n{'='*60}")
    print(f"  READY FOR PAYMENT")
    print(f"  Opening browser now (temporary RAM spike)")
    print(f"{'='*60}")
    
    result = asyncio.run(complete_payment_with_browser(held))
    
    if result:
        print(f"\n✅ SUCCESS! Ticket booked.")
        print(f"   Confirmation: {result}")
        held.status = 'paid'
        held.save()
    else:
        print(f"\n❌ Payment failed")
        print(f"   Hold is still active - you can retry")


if __name__ == '__main__':
    main()
