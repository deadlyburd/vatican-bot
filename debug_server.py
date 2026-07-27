#!/usr/bin/env python3
"""Debug server time click issue."""
import asyncio, json, warnings
warnings.filterwarnings("ignore")

async def test():
    import nodriver as uc
    browser = await uc.start(user_data_dir="/root/vatican_booking_profile", headless=False, lang="it-IT", no_sandbox=True)
    tab = browser.main_tab
    await tab.get("https://tickets.museivaticani.va/home/fromtag/2/1788213600000/MV-Biglietti/1")
    await tab.sleep(5)

    # Click ticket
    tid = await tab.evaluate("""(()=>{var cards=Array.from(document.querySelectorAll('[id^="ticket_"]'));
        for(var c of cards){if(c.innerText.toLowerCase().includes('musei vaticani')){
        var btn=c.querySelector('[data-cy^="bookTicket_"]');if(btn)return btn.getAttribute('data-cy').replace('bookTicket_','');}}
        return null;})()""")
    if isinstance(tid, list): tid = tid[0][1].get('value') if tid else None
    print(f"Ticket ID: {tid}")
    btn = await tab.query_selector('[data-cy="bookTicket_' + str(tid) + '"]')
    if btn: await btn.click()
    await tab.sleep(3)

    # Set quantity
    qty = await tab.query_selector("[data-cy='ticketQuantity']")
    if qty: await qty.click()
    await tab.sleep(1)
    opts = await tab.query_selector_all("[data-cy='ticketQuantitySection']")
    if len(opts) >= 2: await opts[1].click()
    await tab.sleep(2)
    print("Quantity set")

    # Find available time cell index
    time_idx = await tab.evaluate("""(()=>{var cells=document.querySelectorAll("[data-cy='time']");
        for(var i=0;i<cells.length;i++){var t=cells[i].innerText.trim();
        if(!t.includes('ESAURITI')&&!t.includes('SOLD'))return i;}return -1;})()""")
    if isinstance(time_idx, list):
        time_idx = time_idx[0][1].get('value') if time_idx else -1
    print(f"Time index: {time_idx}")

    # Check PROCEDI BEFORE clicking time
    p_before = await tab.evaluate("""(()=>{
        var b=document.querySelector("[data-cy='bookVisit']");
        return b?{disabled:b.disabled,text:b.innerText.trim()}:null;
    })()""")
    print(f"PROCEDI before: {json.dumps(p_before, default=str)}")

    if time_idx >= 0:
        # Click via nodriver Element
        cells = await tab.query_selector_all("[data-cy='time']")
        cell = cells[time_idx]
        await cell.scroll_into_view()
        await tab.sleep(0.3)
        await cell.click()
        print(f"Clicked cell at index {time_idx}")
        await tab.sleep(2)

    # Check PROCEDI AFTER clicking time
    p_after = await tab.evaluate("""(()=>{
        var b=document.querySelector("[data-cy='bookVisit']");
        return b?{disabled:b.disabled,text:b.innerText.trim()}:null;
    })()""")
    print(f"PROCEDI after: {json.dumps(p_after, default=str)}")

    # Try clicking PROCEDI
    if p_after:
        btn = await tab.query_selector("[data-cy='bookVisit']")
        if btn:
            await btn.click()
            print("PROCEDI clicked!")
    await tab.sleep(6)

    url = await tab.evaluate("window.location.href")
    print(f"URL: {url}")

    await browser.stop()

asyncio.run(test())
