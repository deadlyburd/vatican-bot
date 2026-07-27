#!/usr/bin/env python3
"""Quick test: navigate → ticket → time → PROCEDI → checkout."""
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

    # Click 11:30 time - try clicking the mat-button-toggle
    await tab.evaluate("""(()=>{
        const cells = Array.from(document.querySelectorAll("[data-cy='time']"));
        for (const cell of cells) {
            const txt = cell.innerText.trim();
            if (txt.includes("11:30")) {
                // Find parent mat-button-toggle
                const toggle = cell.closest('mat-button-toggle');
                if (toggle) {
                    toggle.click();
                    return;
                }
                // Click the cell
                cell.click();
                cell.dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true,view:window}));
                return;
            }
        }
    })()""")
    await tab.sleep(2)

    # Check selection state
    sel = await tab.evaluate("""(()=>{
        const cells = Array.from(document.querySelectorAll("[data-cy='time']"));
        for (const c of cells) {
            const cls = Array.from(c.classList).join(' ');
            const parent = c.closest('mat-button-toggle');
            const parentCls = parent ? Array.from(parent.classList).join(' ') : '';
            if (cls.includes('selected') || cls.includes('checked') ||
                parentCls.includes('checked') || parentCls.includes('selected') ||
                parentCls.includes('mat-button-toggle-checked')) {
                return c.innerText.trim().substring(0, 30);
            }
        }
        return 'none';
    })()""")
    print(f"Selection state: {sel}")

    # Click PROCEDI
    btn = await tab.query_selector("[data-cy='bookVisit']")
    if btn:
        await btn.scroll_into_view()
        await tab.sleep(0.3)
        await btn.click()
        print("PROCEDI clicked")

    await tab.sleep(6)
    url = await tab.evaluate('window.location.href')
    print(f"URL: {url}")
    await tab.sleep(2)
    browser.stop()

asyncio.run(test())
