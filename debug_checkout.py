#!/usr/bin/env python3
"""Debug Vatican checkout form DOM."""
import asyncio, json, warnings
warnings.filterwarnings("ignore")

async def debug():
    import nodriver as uc
    browser = await uc.start(
        user_data_dir="/root/vatican_test_profile",
        headless=False, lang="it-IT", no_sandbox=True
    )
    tab = browser.main_tab

    # Navigate and click through to checkout
    await tab.get("https://tickets.museivaticani.va/home/fromtag/2/1788213600000/MV-Biglietti/1")
    await tab.sleep(5)

    # Click Vatican ticket
    dom_tid = await tab.evaluate('''(()=>{
        const cards=Array.from(document.querySelectorAll("[id^=\\"ticket_\\"]"));
        for(const c of cards){
            if(c.innerText.toLowerCase().includes("musei vaticani")){
                const btn=c.querySelector("[data-cy^=\\"bookTicket_\\"]");
                if(btn)return btn.getAttribute("data-cy").replace("bookTicket_","");
            }
        }
        return null;
    })()''')
    print(f"DOM ticket_id: {dom_tid}")
    await tab.evaluate(f'document.querySelector("[data-cy=\'bookTicket_{dom_tid}\']")?.click()')
    await tab.sleep(3)

    # Set quantity
    await tab.evaluate('document.querySelector("[data-cy=\'ticketQuantity\']")?.click()')
    await tab.sleep(1)
    await tab.evaluate('''(()=>{
        const items=Array.from(document.querySelectorAll("[data-cy='ticketQuantitySection']"));
        if(items.length>=2)items[1].click();
    })()''')
    await tab.sleep(2)

    # Click time
    await tab.evaluate('''(()=>{
        const cells=Array.from(document.querySelectorAll("[data-cy='time']"));
        for(const c of cells){if(c.innerText.trim().includes("11:30")){c.click();break;}}
    })()''')
    await tab.sleep(2)

    # PROCEDI
    await tab.evaluate('document.querySelector("[data-cy=\'bookVisit\']")?.click()')
    await tab.sleep(6)

    print(f"Current URL: {await tab.evaluate('window.location.href')}")
    print()

    # Inspect form
    info = await tab.evaluate('''(()=>{
        const r = {};
        r.url = window.location.href;

        // Check each expected field
        const fields = [
            "[data-cy='managerSurname']",
            "[data-cy='managerName']",
            "[data-cy='managerEmail']",
            "[data-cy='managerCity']",
            "[data-cy='managerPhone']",
            "[data-cy='managerSex']",
            "[data-cy='managerCountry']",
            "[data-cy='buyButton']",
            "[data-cy='dateCalendar']",
        ];
        r.fields = {};
        for (const sel of fields) {
            const el = document.querySelector(sel);
            if (el) {
                r.fields[sel] = {
                    tag: el.tagName,
                    type: el.type || el.getAttribute("type") || "N/A",
                    value: el.value || "(no value)",
                    disabled: el.disabled || false,
                    visible: el.offsetParent !== null,
                    classes: el.className?.substring(0, 60),
                };
            } else {
                r.fields[sel] = null;
            }
        }

        // All inputs
        r.allInputs = Array.from(document.querySelectorAll("input, select, textarea")).map(el => ({
            sel: el.getAttribute("data-cy") || el.id || el.name || el.tagName,
            value: el.value,
            type: el.type,
        }));

        return r;
    })()''')

    print(json.dumps(info, indent=2))
    await tab.sleep(2)
    browser.stop()

asyncio.run(debug())
