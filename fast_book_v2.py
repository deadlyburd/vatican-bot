#!/usr/bin/env python3
"""Fast book v2: use query_selector + click() (no evaluate() type issues)."""
import asyncio, warnings
warnings.filterwarnings("ignore")

async def book():
    import nodriver as uc
    browser = await uc.start(
        user_data_dir="/root/vatican_test_profile",
        headless=False, lang="it-IT", no_sandbox=True
    )
    tab = browser.main_tab
    await tab.get("https://tickets.museivaticani.va/home/fromtag/2/1788213600000/MV-Biglietti/1")
    await tab.sleep(4)

    # Click Vatican ticket - find by card text
    cards = await tab.query_selector_all('[id^="ticket_"]')
    for card in cards:
        text = await card.get_text()
        if 'musei vaticani' in text.lower() and ('ingresso' in text.lower() or 'biglietti' in text.lower()):
            btn = await card.query_selector('[data-cy^="bookTicket_"]')
            if btn:
                await btn.click()
                print(f"Clicked Vatican ticket")
                break
    await tab.sleep(3)

    # Set quantity to 2
    qty = await tab.query_selector("[data-cy='ticketQuantity']")
    if qty:
        await qty.click()
        await tab.sleep(0.8)
        opts = await tab.query_selector_all("[data-cy='ticketQuantitySection']")
        if len(opts) >= 2:
            await opts[1].click()
            print("Quantity: 2")
    await tab.sleep(2)

    # Find first non-sold-out time cell and click it
    cells = await tab.query_selector_all("[data-cy='time']")
    print(f"Time cells: {len(cells)}")

    clicked = False
    for cell in cells:
        text = await cell.get_text()
        text = text.strip()
        sold = 'ESAURITI' in text or 'SOLD' in text
        if not sold:
            print(f"Clicking: {text.split(chr(10))[0]}")
            await cell.scroll_into_view()
            await tab.sleep(0.3)
            await cell.click()
            await tab.sleep(1)
            clicked = True
            break

    if not clicked:
        print("No available slots!")
        await browser.stop()
        return

    await tab.sleep(2)

    # Check mat-button-toggle-checked
    checked = await tab.query_selector('mat-button-toggle.mat-button-toggle-checked')
    if checked:
        ct = await checked.get_text()
        print(f"Selected toggle: {ct.strip()}")
    else:
        print("No toggle checked!")

    # Click PROCEDI
    procedi = await tab.query_selector("[data-cy='bookVisit']")
    if procedi:
        await procedi.scroll_into_view()
        await tab.sleep(0.3)
        await procedi.click()
        print("PROCEDI clicked")

    # Wait for navigation
    for i in range(15):
        await tab.sleep(1)
        url = await tab.evaluate('window.location.href')
        # Handle nodriver type-wrapped strings
        if isinstance(url, list):
            url = url[0][1]['value'] if url else ''
        elif isinstance(url, dict):
            url = url.get('value', '')
        if 'checkout' in str(url) or 'recap' in str(url):
            print(f"NAVIGATED: {url}")
            break

    await tab.sleep(2)
    await browser.stop()

asyncio.run(book())
