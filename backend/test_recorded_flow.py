import time
import requests
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
# Set to a specific date in "DD/MM/YYYY" format, or None to pick the first available.
DATE_TO_BOOK = None 
VISITORS = 1
# ---------------------

BASE_URL = "https://tickets.museivaticani.va"

def get_date_info(preferred_date=None):
    """
    Probes the Vatican API to find an available date.
    Returns (date_string, timestamp).
    """
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': f'{BASE_URL}/'
    }

    dates_to_check = []
    if preferred_date:
        dates_to_check.append(preferred_date)
    else:
        # Check the next 60 days
        now = datetime.now()
        for i in range(1, 60):
            dates_to_check.append((now + timedelta(days=i)).strftime('%d/%m/%Y'))

    print(f"Checking availability for dates: {dates_to_check[:5]}...")

    for d_str in dates_to_check:
        try:
            params = {
                'lang': 'it',
                'visitorNum': str(VISITORS),
                'visitDate': d_str,
                'area': '1',
                'who': '',
                'page': '0',
                'tag': 'MV-Biglietti'
            }
            resp = requests.get(f"{BASE_URL}/api/search/resultPerTag", params=params, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue
            
            data = resp.json()
            # Look for "Musei Vaticani - Biglietti d'ingresso" that is AVAILABLE
            ticket = next((v for v in data.get('visits', []) 
                          if "musei vaticani" in v.get('name', '').lower() 
                          and "ingresso" in v.get('name', '').lower()
                          and v.get('availability') in ('AVAILABLE', 'LOW_AVAILABILITY')), None)
            
            if ticket:
                print(f"Found availability on {d_str}!")
                # Convert DD/MM/YYYY to timestamp (milliseconds)
                day, month, year = map(int, d_str.split('/'))
                dt = datetime(year, month, day)
                timestamp = int(dt.timestamp() * 1000)
                return d_str, timestamp
        except Exception as e:
            print(f"Error checking {d_str}: {e}")
            continue

    return None, None

def run():
    print("Finding available date...")
    date_str, timestamp = get_date_info(DATE_TO_BOOK)
    
    if not date_str:
        print("No available dates found. Exiting.")
        return

    target_url = f"{BASE_URL}/home/visit/{VISITORS}/{timestamp}/1"
    
    with sync_playwright() as p:
        # Launch headful browser
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()

        print(f"Navigating to Vatican Museums tickets page for {date_str}...")
        page.goto(target_url)

        # 1. Click the specific ticket card (using more robust text-based locator)
        print("Selecting ticket...")
        # Finding the container for "Musei Vaticani - Biglietti d'ingresso"
        ticket_container = page.locator('div.muvaTicketMainDiv:has-text("Musei Vaticani - Biglietti d\'ingresso")')
        ticket_container.scroll_into_view_if_needed()
        ticket_container.locator("img").first.click()

        # 2. Click PRENOTA (Book) button
        print("Clicking Book button...")
        book_button = ticket_container.locator('button:has-text("PRENOTA")')
        book_button.wait_for(state="visible")
        book_button.click()

        # 3. Select Quantity
        print("Ensuring quantity is selected...")
        page.wait_for_selector("[data-cy='ticketQuantity']")

        # 4. Select Time Slot
        print("Selecting time slot...")
        time_slot_selector = "[data-cy='time']"
        page.wait_for_selector(time_slot_selector)
        # Click the first one that isn't sold out (if possible)
        # Simply clicking first as per recording
        page.locator(time_slot_selector).first.click()

        # 5. Click PROCEDI
        print("Clicking Procedi...")
        proceed_button = "[data-cy='bookVisit']"
        page.wait_for_selector(proceed_button)
        page.click(proceed_button)
        
        # Adding a wait for the checkout page to load and handle potential delays
        print("Waiting for checkout page...")
        page.wait_for_load_state("networkidle")
        time.sleep(2) # Extra buffer for Angular hydration

        # 6. Accept Terms and handle instructions modal
        print("Handling terms and instructions...")
        # Using text-based locator for the mandatory checkbox
        # Clicking the label/text usually toggles the Material checkbox
        terms_label_selector = 'span:has-text("Norme Generali d’Acquisto")'
        page.wait_for_selector(terms_label_selector, timeout=20000)
        page.click(terms_label_selector)

        close_rules_btn = "[data-cy='purchase-rules-close-btn']"
        if page.is_visible(close_rules_btn):
            page.click(close_rules_btn)
        
        marketing_label_selector = 'span:has-text("ricevere informazioni sulle offerte")'
        if page.is_visible(marketing_label_selector):
            page.click(marketing_label_selector)

        # 7. Fill Manager Form
        print("Filling out manager form...")
        page.fill("[data-cy='managerSurname']", "cdc")
        page.fill("[data-cy='managerName']", "xzcxz")
        
        # Sex
        page.click("[data-cy='managerSex']")
        page.wait_for_selector("mat-option")
        page.locator("mat-option").filter(has_text="MASCHIO").click()
        
        # Country
        page.click("[data-cy='managerCountry']")
        page.wait_for_selector("mat-option")
        page.locator("mat-option").filter(has_text="Afghanistan").click()
        
        page.fill("[data-cy='managerCity']", "zxcxz")
        
        # Birthdate
        print("Setting birthdate...")
        page.click("[data-cy='dateCalendar']")
        page.click("button.mat-calendar-period-button")
        page.locator("button.mat-calendar-body-cell").filter(has_text="2002").click()
        page.locator("button.mat-calendar-body-cell").filter(has_text="MAR").click()
        page.locator("button.mat-calendar-body-cell").filter(has_text="21").click()

        # Email
        page.fill("[data-cy='managerEmail']", "test-user@example.com")

        print("Flow completed. Keeping browser open for a few seconds...")
        time.sleep(15)
        
        # browser.close()

if __name__ == "__main__":
    run()
