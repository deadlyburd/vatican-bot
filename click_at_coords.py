#!/usr/bin/env python3
"""Click time slot using real mouse events at element coordinates."""
import asyncio, warnings
warnings.filterwarnings("ignore")

async def test():
    import nodriver as uc
    browser = await uc.start(
        user_data_dir="/root/vatican_test_profile",
        headless=False, lang="it-IT", no_sandbox=True
    )
    tab = browser.main_tab
    await tab.get("https://tickets.museivaticani.va/home/fromtag/2/1788213600000/MV-Biglietti/1")
    await tab.sleep(5)

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
    await tab.sleep(3)

    # Set quantity first
    qty_el = await tab.query_selector("[data-cy='ticketQuantity']")
    if qty_el:
        await qty_el.click()
        await tab.sleep(1)
        options = await tab.query_selector_all("[data-cy='ticketQuantitySection']")
        if len(options) >= 2:
            await options[1].click()
            await tab.sleep(1)
    print("Quantity set")

    # Find 11:30 time cell and get its bounding rect
    rect = await tab.evaluate("""(()=>{
        const cells = Array.from(document.querySelectorAll("[data-cy='time']"));
        for (const cell of cells) {
            const txt = cell.innerText.trim();
            if (txt.includes("11:30")) {
                const r = cell.getBoundingClientRect();
                return {x: r.x + r.width/2, y: r.y + r.height/2, text: txt};
            }
        }
        return null;
    })()""")
    print(f"Rect: {rect}")

    # Click at those coordinates using CDP mouse events
    if rect:
        # Extract actual values from nodriver's type-wrapped returns
        x = rect['x']['value'] if isinstance(rect.get('x'), dict) else rect['x']
        y = rect['y']['value'] if isinstance(rect.get('y'), dict) else rect['y']
        print(f"Clicking at x={x}, y={y}")

        # Use CDP to dispatch real mouse click
        await tab.send(cdp.send('Input.dispatchMouseEvent', {
            'type': 'mousePressed',
            'x': x, 'y': y,
            'button': 'left',
            'clickCount': 1,
        }))
        await tab.send(cdp.send('Input.dispatchMouseEvent', {
            'type': 'mouseReleased',
            'x': x, 'y': y,
            'button': 'left',
            'clickCount': 1,
        }))
        print("Mouse click dispatched")
        await tab.sleep(2)

    # Check selection
    sel = await tab.evaluate("""(()=>{
        const cells = Array.from(document.querySelectorAll("[data-cy='time']"));
        for (const c of cells) {
            const parent = c.closest('mat-button-toggle');
            if (parent && parent.classList.contains('mat-button-toggle-checked')) {
                return 'checked:' + c.innerText.trim().substring(0, 30);
            }
        }
        return 'none';
    })()""")
    print(f"Selection: {sel}")

    # Click PROCEDI
    btn = await tab.query_selector("[data-cy='bookVisit']")
    if btn:
        await btn.click()
        print("PROCEDI clicked")

    await tab.sleep(6)
    url = await tab.evaluate('window.location.href')
    print(f"URL: {url}")
    await tab.sleep(2)
    browser.stop()

asyncio.run(test())
