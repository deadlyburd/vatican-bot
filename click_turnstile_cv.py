#!/usr/bin/env python3
"""Click Turnstile checkbox using OpenCV template matching."""
import asyncio, warnings, json, urllib.request, base64, io
warnings.filterwarnings("ignore")

async def find_and_click_checkbox():
    import nodriver as uc
    import numpy as np
    import cv2

    browser = await uc.start(
        user_data_dir="/root/vatican_booking_profile",
        headless=False, lang="it-IT", no_sandbox=True,
        window_size=(1005, 572)
    )
    tab = browser.main_tab

    # Navigate to checkout (already filled form)
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

    # Fill form to trigger Turnstile
    # (abbreviated fill - just enough to get Turnstile to appear)
    await tab.evaluate("""(()=>{
        var fields = [
            ['[data-cy="managerSurname"]', 'Rossi'],
            ['[data-cy="managerName"]', 'Mario'],
            ['[data-cy="managerEmail"]', 'mario@test.it'],
            ['[data-cy="managerConfirmEmail"]', 'mario@test.it'],
            ['[data-cy="managerPhone"]', '3401234567'],
            ['[data-cy="managerCity"]', 'Roma'],
        ];
        for (var i=0;i<fields.length;i++) {
            var el = document.querySelector(fields[i][0]);
            if (el) { el.focus(); el.select();
                document.execCommand('selectAll',false,null);
                document.execCommand('insertText',false,fields[i][1]);
                el.dispatchEvent(new Event('input',{bubbles:true}));
                el.dispatchEvent(new Event('change',{bubbles:true}));
            }
        }
        // Click gender, country, language
        document.querySelector('[data-cy="managerSex"]')?.click();
        setTimeout(function(){document.querySelector('[data-cy="managerSexSection"]')?.click()},300);
        document.querySelector('[data-cy="managerCountry"]')?.click();
        setTimeout(function(){document.querySelector('[data-cy="managerCountrySection"]')?.click()},300);
        document.querySelector('[data-cy="managerLanguage"]')?.click();
        setTimeout(function(){document.querySelector('[data-cy="managerLanguageSection"]')?.click()},300);
    })()""")
    await tab.sleep(4)

    # Scroll to captcha
    await tab.evaluate("document.querySelector('.captchaElement')?.scrollIntoView({behavior:'instant',block:'center'})")
    await tab.sleep(3)  # Wait for iframe to load

    # CDP: take screenshot
    ws_url = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json").read())[0]['webSocketDebuggerUrl']
    import websockets
    ws = await websockets.connect(ws_url)

    await ws.send(json.dumps({"id":1,"method":"Page.enable"}))
    await ws.recv()
    await ws.send(json.dumps({"id":2,"method":"Page.captureScreenshot","params":{"format":"png"}}))
    result = json.loads(await ws.recv())
    img_data = base64.b64decode(result['result']['data'])
    img = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    print(f"Screenshot: {w}x{h}")

    # Get captchaElement position for search region
    pos = await tab.evaluate("""(()=>{var el=document.querySelector('.captchaElement');
        if(!el)return null;var r=el.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};})()""")
    if isinstance(pos, list):
        pos = {item[0]: item[1].get('value', item[1]) for item in pos if isinstance(item, list) and len(item)==2}

    if pos:
        # Search in the captcha area
        cx, cy, cw, ch = int(pos['x']), int(pos['y']), int(pos['w']), int(pos['h'])
        roi = img[cy:cy+ch, cx:cx+cw]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        # Threshold to find dark checkbox square
        _, thresh = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        print(f"ROI: {cw}x{ch} at ({cx},{cy}), found {len(contours)} contours")

        for cnt in contours:
            xc, yc, wc, hc = cv2.boundingRect(cnt)
            # Filter: checkbox should be square-ish, 15-40px
            if 15 < wc < 50 and 15 < hc < 50 and abs(wc-hc) < 15:
                # Found a checkbox-like shape!
                click_x = cx + xc + wc//2
                click_y = cy + yc + hc//2
                print(f"  Checkbox at {click_x},{click_y} ({wc}x{hc})")

                # Click it via CDP
                await ws.send(json.dumps({"id":3,"method":"Input.dispatchMouseEvent",
                    "params":{"type":"mousePressed","x":click_x,"y":click_y,"button":"left","clickCount":1}}))
                await asyncio.sleep(0.03)
                await ws.send(json.dumps({"id":4,"method":"Input.dispatchMouseEvent",
                    "params":{"type":"mouseReleased","x":click_x,"y":click_y,"button":"left","clickCount":1}}))
                await asyncio.sleep(0.5)

                # Check if solved
                solved = await tab.evaluate("""(()=>{var i=document.querySelector('input[name="cf-turnstile-response"]');return !!(i&&i.value&&i.value.length>10);})()""")
                if solved:
                    print("  ✅ SOLVED by OpenCV!")
                    break

        # Save debug images
        cv2.imwrite('/root/captcha_roi.png', roi)
        cv2.imwrite('/root/captcha_thresh.png', thresh)
        print("Debug images saved to /root/captcha_*.png")

    await ws.close()
    await asyncio.sleep(2)
    await browser.stop()

asyncio.run(find_and_click_checkbox())
