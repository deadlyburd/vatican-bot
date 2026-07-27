#!/usr/bin/env python3
"""Test clicking time slot inner elements to trigger Angular selection."""
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

    await tab.evaluate(f"""document.querySelector('[data-cy="bookTicket_{dom_tid}"]')?.click()""")
    await tab.sleep(3)

    # Find 11:30 time cell
    cell = await tab.query_selector("[data-cy='time']")
    if not cell:
        print("No time cells found")
        return

    # Find the specific time cell for 11:30
    cells = await tab.query_selector_all("[data-cy='time']")
    print(f"Found {len(cells)} time cells")

    target_idx = None
    for idx, c in enumerate(cells):
        text = await c.get_text()
        if "11:30" in text:
            target_idx = idx
            print(f"Found 11:30 at index {idx}: text='{text.strip()}'")
            break

    if target_idx is None:
        print("11:30 not found")
        return

    target = cells[target_idx]

    # Try clicking innermost elements
    # First scroll to it
    await target.scroll_into_view()
    await tab.sleep(0.5)

    # Get inner HTML structure
    inner_html = await target.get_html()
    print(f"Inner HTML: {inner_html[:300]}")

    # Try clicking children: span (time number), then div
    children = await target.query_selector_all('*')
    print(f"Children: {len(children)}")
    for i, child in enumerate(children[:5]):
        tag = await child.get_tag_name()
        text = await child.get_text()
        print(f"  Child {i}: <{tag}> '{text.strip()}'")

    # Click the span (time number)
    span = await target.query_selector('span')
    if span:
        print("\nClicking span child...")
        await span.click()
        await tab.sleep(2)
    else:
        # Click div child
        divs = await target.query_selector_all('div')
        if divs:
            print(f"\nClicking last div child...")
            await divs[-1].click()
            await tab.sleep(2)

    # Check if time is selected
    selected = await tab.evaluate("""(()=>{
        const cells = Array.from(document.querySelectorAll("[data-cy='time']"));
        for (const c of cells) {
            if (c.classList.contains('selected') || c.classList.contains('active') ||
                c.getAttribute('aria-selected') === 'true' || c.getAttribute('aria-checked') === 'true') {
                return c.innerText.trim().substring(0, 30);
            }
        }
        return null;
    })()""")
    print(f"Selected cell: {selected}")

    # Now click PROCEDI
    print("\nClicking PROCEDI...")
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
