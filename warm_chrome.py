#!/usr/bin/env python3
"""Pre-warm Chrome with Vatican browsing to build Cloudflare trust."""
import asyncio, json, urllib.request, websockets, time

async def warm():
    resp = urllib.request.urlopen('http://127.0.0.1:9222/json')
    tab = next((t for t in json.loads(resp.read()) if t.get('type')=='page'), None)
    if not tab: return print('No tab')

    ws = await websockets.connect(tab['webSocketDebuggerUrl'])
    async def cdp(m, p={}):
        cid = int(time.time()*1000) % 100000
        await ws.send(json.dumps({'id':cid,'method':m,'params':p}))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get('id')==cid: return msg

    await cdp('Runtime.enable'); await cdp('Page.enable')

    # 1. Vatican home
    print('1. Vatican home...')
    await cdp('Page.navigate', {'url':'https://tickets.museivaticani.va/home'})
    await asyncio.sleep(4)

    # 2. Browse tickets for a date
    print('2. Browsing tickets...')
    await cdp('Page.navigate', {'url':'https://tickets.museivaticani.va/home/fromtag/2/1788213600000/MV-Biglietti/1'})
    await asyncio.sleep(4)

    # 3. Navigate back home
    print('3. Back to home...')
    await cdp('Page.navigate', {'url':'https://tickets.museivaticani.va/home'})
    await asyncio.sleep(3)

    print('✅ Chrome warmed! Cookies saved to persistent profile.')
    await ws.close()

asyncio.run(warm())
