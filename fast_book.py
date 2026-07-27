#!/usr/bin/env python3
"""Fast book: find first available slot, click through to checkout."""
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

    # Click Vatican ticket
    dom_tid = await tab.evaluate("""(()=>{
        const cards=Array.from(document.querySelectorAll('[id^="ticket_"]'));
        for(const c of cards){
            if(c.innerText.toLowerCase().includes("musei vaticani")){
                const btn=c.querySelector('[data-cy^="bookTicket_"]');
                if(btn)return btn.getAttribute('data-cy').replace('bookTicket_','');
            }
        }
        return null;
    })()""")
    await tab.evaluate(f"""document.querySelector('[data-cy="bookTicket_{dom_tid}"]')?.click()""")
    await tab.sleep(2)

    # Set quantity
    qty_el = await tab.query_selector("[data-cy='ticketQuantity']")
    if qty_el:
        await qty_el.click()
        await tab.sleep(0.8)
        options = await tab.query_selector_all("[data-cy='ticketQuantitySection']")
        if len(options) >= 2:
            await options[1].click()
    await tab.sleep(1)

    # Find FIRST available time slot (not SOLD OUT or ESAURITI)
    available = await tab.evaluate("""(()=>{
        const cells = Array.from(document.querySelectorAll("[data-cy='time']"));
        for (const cell of cells) {
            const txt = cell.innerText.trim();
            const soldOut = txt.includes('ESAURITI') || txt.includes('SOLD');
            if (!soldOut) {
                const r = cell.getBoundingClientRect();
                // Check if it has an afternoon parent tab that needs switching
                const parentSection = cell.closest('[class*="tab"], [role="tabpanel"]');
                return {
                    text: txt.split('\\n')[0],
                    x: r.x + r.width/2,
                    y: r.y + r.height/2,
                    hidden: parentSection ? parentSection.offsetParent === null : false,
                };
            }
        }
        return null;
    })()""")
    print(f"First available: {available}")

    if not available:
        print("No available slots!")
        await browser.stop()
        return

    # Click at the exact coordinates of the available time slot
    x = available['x']['value'] if isinstance(available.get('x'), dict) else (available[1][1]['value'] if isinstance(available, list) else 0)
    y = available['y']['value'] if isinstance(available.get('y'), dict) else (available[3][1]['value'] if isinstance(available, list) else 0)

    if isinstance(available, list):
        # Parse nodriver's weird format
        d = {}
        for item in available:
            d[item[0]] = item[1]['value']
        x, y = d['x'], d['y']
        print(f"Parsed coords: x={x}, y={y}")
    else:
        x = available['x']['value']
        y = available['y']['value']

    # Use CDP to dispatch a real mouse click
    cdp = await browser.cdp()
    await cdp.send('Input.dispatchMouseEvent', {
        'type': 'mousePressed', 'x': x, 'y': y,
        'button': 'left', 'clickCount': 1,
    })
    await cdp.send('Input.dispatchMouseEvent', {
        'type': 'mouseReleased', 'x': x, 'y': y,
        'button': 'left', 'clickCount': 1,
    })
    print(f"Clicked at ({x}, {y})")
    await tab.sleep(2)

    # Check if selected
    sel = await tab.evaluate("""(()=>{
        const toggles = Array.from(document.querySelectorAll('mat-button-toggle.mat-button-toggle-checked'));
        if (toggles.length > 0) return toggles[0].innerText.trim().substring(0, 30);
        return 'none';
    })()""")
    print(f"Selected: {sel}")

    # Click PROCEDI
    procedi = await tab.query_selector("[data-cy='bookVisit']")
    if procedi:
        await procedi.click()
        print("PROCEDI clicked")

    # Wait for navigation
    for i in range(15):
        await tab.sleep(1)
        url = await tab.evaluate('window.location.href')
        if 'checkout' in url or 'recap' in url:
            print(f"NAVIGATED to: {url}")
            break
    else:
        url = await tab.evaluate('window.location.href')
        print(f"Final URL: {url}")

    await tab.sleep(3)
    await browser.stop()

asyncio.run(book())
