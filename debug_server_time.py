import asyncio, warnings
warnings.filterwarnings("ignore")

async def test():
    import nodriver as uc
    browser = await uc.start(user_data_dir="/root/vatican_booking_profile", headless=False, lang="it-IT", no_sandbox=True)
    tab = browser.main_tab
    await tab.get("https://tickets.museivaticani.va/home/fromtag/2/1788213600000/MV-Biglietti/1")
    await tab.sleep(5)

    # Click ticket
    tid = await tab.evaluate("""(()=>{var cards=Array.from(document.querySelectorAll("[id^=\\"ticket_\\"]"));
        for(var c of cards){if(c.innerText.toLowerCase().includes("musei vaticani")){
        var btn=c.querySelector("[data-cy^=\\"bookTicket_\\"]");if(btn)return btn.getAttribute("data-cy").replace("bookTicket_","");}}
        return null;})()""")
    if isinstance(tid, list): tid = tid[0][1].get("value") if tid else None
    btn = await tab.query_selector("[data-cy=\\"bookTicket_" + str(tid) + "\\"]")
    if btn: await btn.click()
    await tab.sleep(3)

    # Set quantity
    qty = await tab.query_selector("[data-cy=\\"ticketQuantity\\"]")
    if qty: await qty.click()
    await tab.sleep(1)
    opts = await tab.query_selector_all("[data-cy=\\"ticketQuantitySection\\"]")
    if len(opts) >= 2: await opts[1].click()
    await tab.sleep(2)

    # Find available time cell
    time_idx = await tab.evaluate("""(()=>{var cells=document.querySelectorAll("[data-cy=\\"time\\"]");
        for(var i=0;i<cells.length;i++){var t=cells[i].innerText.trim();
        if(!t.includes("ESAURITI")&&!t.includes("SOLD"))return i;}return -1;})()""")
    if isinstance(time_idx, list): time_idx = time_idx[0][1].get("value") if time_idx else -1
    print(f"Time index: {time_idx}")

    if time_idx >= 0:
        cells = await tab.query_selector_all("[data-cy=\\"time\\"]")
        cell = cells[time_idx]
        # Click with mouse event sequence
        await tab.evaluate(f"""(function(){{
            var cells=document.querySelectorAll("[data-cy=\\"time\\"]");
            var c=cells[{time_idx}];
            if(!c)return;
            c.scrollIntoView({{behavior:"smooth",block:"center"}});
            var r=c.getBoundingClientRect();
            var x=r.x+r.width/2, y=r.y+r.height/2;
            ["mousemove","mouseover","mousedown","mouseup","click"].forEach(function(t){{
                c.dispatchEvent(new MouseEvent(t,{{bubbles:true,cancelable:true,clientX:x,clientY:y,view:window}}));
            }});
        }})()""")
        print(f"Clicked cell at index {time_idx}")
        await tab.sleep(2)

    # Check PROCEDI state
    import json
    p = await tab.evaluate("""(()=>{
        var b=document.querySelector("[data-cy=\\"bookVisit\\"]");
        if(!b)return {{found:false}};
        return {{found:true, disabled:b.disabled, text:b.innerText.trim(), visible:b.offsetParent!==null}};
    })()""")
    print(f"PROCEDI: {json.dumps(p, default=str)}")

    await tab.sleep(3)
    await browser.stop()

asyncio.run(test())
