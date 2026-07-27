#!/usr/bin/env python3
"""Check Turnstile state on server over time."""
import asyncio, json, warnings
warnings.filterwarnings("ignore")

async def test():
    import nodriver as uc
    browser = await uc.start(user_data_dir="/root/vatican_booking_profile", headless=False, lang="it-IT", no_sandbox=True)
    tab = browser.main_tab

    await tab.get("https://tickets.museivaticani.va/home/fromtag/2/1788213600000/MV-Biglietti/1")
    await tab.sleep(5)
    await tab.evaluate("""(()=>{var cards=Array.from(document.querySelectorAll('[id^="ticket_"]'));
        for(var c of cards){if(c.innerText.toLowerCase().includes('musei vaticani')){
        var btn=c.querySelector('[data-cy^="bookTicket_"]');if(btn){btn.click();return;}}}})()""")
    await tab.sleep(3)
    await tab.evaluate("document.querySelector(\"[data-cy='ticketQuantity']\")?.click()")
    await tab.sleep(1)
    await tab.evaluate("""(()=>{var items=Array.from(document.querySelectorAll("[data-cy='ticketQuantitySection']"));
        if(items.length>=2)items[1].click();})()""")
    await tab.sleep(2)
    await tab.evaluate("""(()=>{var cells=Array.from(document.querySelectorAll("[data-cy='time']"));
        for(var c of cells){var t=c.innerText.trim();
        if(!t.includes('ESAURITI')&&!t.includes('SOLD')){c.click();break;}}})()""")
    await tab.sleep(2)
    await tab.evaluate("document.querySelector(\"[data-cy='bookVisit']\")?.click()")
    await tab.sleep(6)
    print("On checkout, monitoring Turnstile...")

    for i in range(40):
        state = await tab.evaluate("""(()=>{
            var r = {};
            r.iframe = !!document.querySelector('iframe[src*="challenges.cloudflare"]');
            var f = document.querySelector('iframe[src*="challenges.cloudflare"]');
            r.iframeSrc = f ? f.src.substring(0,120) : null;
            r.iframeVisible = f ? f.offsetParent !== null : false;
            r.token = document.querySelector('[name="cf-turnstile-response"]')?.value?.substring(0,40) || null;
            r.allIframes = document.querySelectorAll('iframe').length;
            var urls = [];
            document.querySelectorAll('iframe').forEach(function(f){urls.push(f.src.substring(0,80))});
            r.frameUrls = urls;
            return r;
        })()""")

        if isinstance(state, list):
            state = {item[0]: item[1].get('value', item[1]) for item in state if isinstance(item, list) and len(item)==2}

        token = state.get('token')
        iframe = state.get('iframe')
        if token:
            print(f"[{i}s] ✅ TOKEN: {token}")
        if iframe:
            print(f"[{i}s] 📦 IFRAME: {state.get('iframeSrc','')[:80]}")
        if i == 0 or i % 10 == 0:
            print(f"[{i}s] iframes={state.get('allIframes',0)} token={token or 'none'} visible={state.get('iframeVisible')}")

        # If iframe exists, try clicking it
        if iframe and state.get('iframeVisible'):
            print(f"[{i}s] Clicking Turnstile iframe...")
            await tab.evaluate("""(()=>{
                var f = document.querySelector('iframe[src*="challenges.cloudflare"]');
                if(!f)return;
                var r = f.getBoundingClientRect();
                var x = r.x + 30, y = r.y + 35;
                var el = document.elementFromPoint(x, y);
                if(el){
                    el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,clientX:x,clientY:y,view:window}));
                    el.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,clientX:x,clientY:y}));
                    el.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,clientX:x,clientY:y}));
                }
            })()""")
            await tab.sleep(3)

        await tab.sleep(1)

    await tab.sleep(2)
    await browser.stop()

asyncio.run(test())
