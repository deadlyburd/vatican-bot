import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        c = await b.new_context()
        page = await c.new_page()
        print("Goto...")
        await page.goto("https://tickets.museivaticani.va/home/fromtag/3/1782165600000/MV-Biglietti/1")
        await page.wait_for_timeout(3000)
        print("Clicking bookTicket...")
        await page.click("[data-cy^='bookTicket_']", timeout=10000)
        await page.wait_for_timeout(2000)
        print("Clicking dropdown...")
        await page.click("[data-cy='ticketQuantity']", timeout=10000)
        await page.wait_for_timeout(2000)
        html = await page.content()
        with open("vatican_dropdown_dom.html", "w", encoding="utf-8") as f:
            f.write(html)
        await b.close()
        print("Done!")

asyncio.run(test())
