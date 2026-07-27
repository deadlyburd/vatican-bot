#!/usr/bin/env python3
"""Take screenshot of Vatican checkout page + get Turnstile positioning."""
import asyncio, json, warnings
warnings.filterwarnings("ignore")

async def take_screenshot():
    import nodriver as uc
    browser = await uc.start(
        user_data_dir="/root/vatican_booking_profile",
        headless=False, lang="it-IT", no_sandbox=True,
        window_size=(701, 572)
    )
    tab = browser.main_tab

    await tab.get("https://tickets.museivaticani.va/home/fromtag/2/1788213600000/MV-Biglietti/1")
    await tab.sleep(5)

    # Click through to checkout
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

    # SCROLL to captcha first
    await tab.evaluate("""(()=>{
        var el = document.querySelector('.captchaElement');
        if (el) el.scrollIntoView({behavior:'instant',block:'center'});
    })()""")
    await asyncio.sleep(1)

    # Get positioning info AFTER scroll
    info = await tab.evaluate("""(()=>{
        var r = {};
        r.viewport = {w: window.innerWidth, h: window.innerHeight};
        r.scrollY = window.scrollY;

        var ce = document.querySelector('.captchaElement');
        if (ce) {
            var rect = ce.getBoundingClientRect();
            r.captchaElement = {
                x: Math.round(rect.x), y: Math.round(rect.y),
                w: Math.round(rect.width), h: Math.round(rect.height),
                centerX: Math.round(rect.x + rect.width/2),
                centerY: Math.round(rect.y + rect.height/2),
                estimatedCheckboxX: Math.round(rect.x + 20),
                estimatedCheckboxY: Math.round(rect.y + 33),
            };
        }

        var cc = document.querySelector('.captchaContainer');
        if (cc) {
            var rect = cc.getBoundingClientRect();
            r.captchaContainer = {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)};
        }

        var frames = document.querySelectorAll('iframe');
        r.iframes = Array.from(frames).map(function(f){
            var fr = f.getBoundingClientRect();
            return {x:Math.round(fr.x), y:Math.round(fr.y), w:Math.round(fr.width), h:Math.round(fr.height), src:f.src?f.src.substring(0,100):'no src'};
        });

        var hs = document.querySelectorAll('h4');
        for (var i=0;i<hs.length;i++) {
            if (hs[i].innerText.indexOf('Spunta')>-1 || hs[i].innerText.indexOf('rettangolo')>-1) {
                var hr = hs[i].getBoundingClientRect();
                r.spuntaHeading = {x:Math.round(hr.x), y:Math.round(hr.y), w:Math.round(hr.width), h:Math.round(hr.height)};
            }
        }

        var ti = document.querySelector('input[name="cf-turnstile-response"]');
        r.tokenPresent = ti ? (ti.value ? ti.value.substring(0,40) : 'EMPTY') : 'NOT FOUND';

        return r;
    })()""")
    print("=== PAGE INFO (after scroll) ===")
    print(json.dumps(info, indent=2, default=str))

    # Screenshot
    await tab.save_screenshot('/root/page_screenshot.png')
    print("\n✅ Screenshot saved")

    await tab.sleep(2)
    await browser.stop()

asyncio.run(take_screenshot())
