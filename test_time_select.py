#!/usr/bin/env python3
"""Debug time slot selection and PROCEDI navigation."""
import asyncio, json, warnings
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

    # Click ticket
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
    print(f"Ticket: {dom_tid}")

    # Click ticket button
    await tab.evaluate(f"""document.querySelector('[data-cy="bookTicket_{dom_tid}"]')?.click()""")
    await tab.sleep(3)

    # Check time slot structure
    time_info = await tab.evaluate("""(()=>{
        const containers = document.querySelectorAll("[data-cy='time']");
        const info = [];
        for (const c of Array.from(containers).slice(0, 3)) {
            info.push({
                tag: c.tagName,
                text: c.innerText.trim().substring(0, 40),
                classList: Array.from(c.classList).join(' '),
                role: c.getAttribute('role'),
                disabled: c.classList.contains('disabled'),
                childTags: Array.from(c.querySelectorAll('*')).map(e=>e.tagName).join(','),
            });
        }
        return {total: containers.length, samples: info};
    })()""")
    print(json.dumps(time_info, indent=2))

    # Try clicking 11:30 via its container div
    result = await tab.evaluate("""(()=>{
        const cells = Array.from(document.querySelectorAll("[data-cy='time']"));
        for (const cell of cells) {
            const txt = cell.innerText.trim();
            if (txt.includes("11:30")) {
                cell.scrollIntoView({behavior:"smooth",block:"center"});
                // Click the cell itself
                cell.click();
                // Also try clicking any child div/button
                const child = cell.querySelector('div, button, span');
                if (child) child.click();
                return "clicked:" + txt.split('\\n')[0];
            }
        }
        return "not found";
    })()""")
    print(f"Time click result: {result}")
    await tab.sleep(3)

    # Check PROCEDI state
    procedi_state = await tab.evaluate("""(()=>{
        const btn = document.querySelector("[data-cy='bookVisit']");
        if (!btn) return {found: false};
        return {
            found: true,
            disabled: btn.disabled,
            visible: btn.offsetParent !== null,
            text: btn.innerText.trim().substring(0, 30),
        };
    })()""")
    print(f"PROCEDI state: {json.dumps(procedi_state)}")

    # Click PROCEDI directly (time slot IS selected)
    print("Clicking PROCEDI...")
    btn = await tab.query_selector("[data-cy='bookVisit']")
    if btn:
        await btn.scroll_into_view()
        await tab.sleep(0.5)
        await btn.click()
        print("PROCEDI clicked!")
    # Also try JS click as backup
    await tab.evaluate("""document.querySelector("[data-cy='bookVisit']")?.click()""")
    print("PROCEDI JS click also fired")

    # Wait for navigation
    for i in range(20):
        await tab.sleep(1)
        url = await tab.evaluate('window.location.href')
        if 'checkout' in url or 'recap' in url:
            print(f"NAVIGATED: {url}")
            break
        if i == 5:
            print(f"  Still at: {url}")

    final_url = await tab.evaluate('window.location.href')
    print(f"Final URL: {final_url}")

    # If we reached checkout, inspect form
    if 'checkout' in final_url or 'recap' in final_url:
        print("\n=== CHECKOUT PAGE REACHED! ===")
        has_form = await tab.evaluate("""!!document.querySelector("[data-cy='managerSurname']")""")
        print(f"Form present: {has_form}")
        if has_form:
            # Test filling one field with send_keys
            el = await tab.query_selector("[data-cy='managerSurname']")
            if el:
                print("Found managerSurname, testing send_keys...")
                await el.click()
                await tab.sleep(0.2)
                await el.send_keys("Rossi")
                await tab.sleep(0.5)
                val = await tab.evaluate("""document.querySelector("[data-cy='managerSurname']")?.value""")
                print(f"Value after send_keys: {val}")
                is_valid = await tab.evaluate("""!document.querySelector("[data-cy='managerSurname']")?.classList?.contains('ng-invalid')""")
                print(f"Valid after send_keys: {is_valid}")

    await tab.sleep(2)
    browser.stop()

asyncio.run(test())
