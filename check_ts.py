import asyncio, warnings
warnings.filterwarnings("ignore")

async def test():
    import nodriver as uc
    browser = await uc.start(user_data_dir="/root/vatican_booking_profile", headless=False, lang="it-IT", no_sandbox=True)
    tab = browser.main_tab
    
    await tab.get("https://tickets.museivaticani.va/home/fromtag/2/1788213600000/MV-Biglietti/1")
    await tab.sleep(5)
    
    # Click through to checkout
    await tab.evaluate("""(()=>{var cards=Array.from(document.querySelectorAll("[id^=\\"ticket_\\"]"));
        for(var c of cards){if(c.innerText.toLowerCase().includes("musei vaticani")){
        var btn=c.querySelector("[data-cy^=\\"bookTicket_\\"]");if(btn){btn.click();return;}}}})()""")
    await tab.sleep(3)
    await tab.evaluate("document.querySelector(\"[data-cy=\\"ticketQuantity\\"]\")?.click()")
    await tab.sleep(1)
    await tab.evaluate("""(()=>{var items=Array.from(document.querySelectorAll("[data-cy=\\"ticketQuantitySection\\"]"));
        if(items.length>=2)items[1].click();})()""")
    await tab.sleep(2)
    await tab.evaluate("""(()=>{var cells=Array.from(document.querySelectorAll("[data-cy=\\"time\\"]"));
        for(var c of cells){var t=c.innerText.trim();
        if(!t.includes("ESAURITI")&&!t.includes("SOLD")){c.click();break;}}})()""")
    await tab.sleep(2)
    await tab.evaluate("document.querySelector(\"[data-cy=\\"bookVisit\\"]\")?.click()")
    await tab.sleep(6)
    
    # On checkout - find ALL Turnstile/captcha elements
    ts_elements = await tab.evaluate("""(()=>{
        var r = {};
        
        // Check for Turnstile iframes
        var iframes = document.querySelectorAll("iframe");
        r.iframes = Array.from(iframes).map(function(f){return f.src.substring(0,80)});
        
        // Check for cf-turnstile div
        var cf = document.querySelector(".cf-turnstile");
        r.cfDiv = cf ? {visible: cf.offsetParent!==null, innerHTML: cf.innerHTML.substring(0,200)} : null;
        
        // Check for turnstile input
        var inp = document.querySelector("[name=\\"cf-turnstile-response\\"]");
        r.turnstileInput = inp ? {value: inp.value.substring(0,30), visible: inp.offsetParent!==null} : null;
        
        // Check for any captcha elements
        var captcha = document.querySelectorAll("[src*=\\"captcha\\"], [src*=\\"turnstile\\"], [class*=\\"captcha\\"], [class*=\\"turnstile\\"], [id*=\\"captcha\\"], [id*=\\"turnstile\\"]");
        r.captchaElements = Array.from(captcha).map(function(el){return {tag:el.tagName, id:el.id, class:el.className.substring(0,60), src:(el.src||"").substring(0,80)}});
        
        // Check body for "verify" text
        r.bodySnippet = document.body?document.body.innerText.substring(0,500):"";
        
        return r;
    })()""")
    import json
    print(json.dumps(ts_elements, indent=2, default=str))
    
    await tab.sleep(3)
    await browser.stop()

asyncio.run(test())
