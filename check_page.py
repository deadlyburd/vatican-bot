#!/usr/bin/env python3
"""Check the current state of the Chrome page via CDP."""
import asyncio, json, websockets, urllib.request, sys

CDP_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9222

async def check():
    resp = urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json", timeout=5)
    tabs = json.loads(resp.read())
    tab = next((t for t in tabs if t.get("type") == "page"), None)
    if not tab:
        print("No page tab found")
        return

    print(f"URL: {tab.get('url', '')[:200]}")
    print(f"Title: {tab.get('title', '')}")

    ws_url = tab["webSocketDebuggerUrl"]
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
        await ws.recv()

        # Get page state
        js = """
        JSON.stringify({
            url: window.location.href,
            title: document.title,
            bodyPreview: document.body ? document.body.innerText.substring(0, 500) : 'no body',
            hasTicketButtons: document.querySelectorAll("[data-cy^='bookTicket']").length,
            hasTimeSlots: document.querySelectorAll("[data-cy='time']").length,
            hasProcedi: !!document.querySelector("[data-cy='bookVisit']"),
            hasAcquista: !!document.querySelector("[data-cy='buyButton']"),
            vabLog: window.__vabLog || [],
        })
        """
        await ws.send(json.dumps({
            "id": 2, "method": "Runtime.evaluate",
            "params": {"expression": js, "returnByValue": True}
        }))
        r = await asyncio.wait_for(ws.recv(), timeout=10)
        data = json.loads(r)
        val = data.get("result", {}).get("result", {}).get("value", "{}")
        try:
            state = json.loads(val)
            for k, v in state.items():
                if k == 'bodyPreview':
                    print(f"{k}: {str(v)[:300]}")
                elif k == 'vabLog':
                    print(f"vabLog ({len(v)} entries):")
                    for entry in v[-10:]:
                        print(f"  {entry}")
                else:
                    print(f"{k}: {v}")
        except Exception:
            print(f"Raw: {val[:500]}")

asyncio.run(check())
