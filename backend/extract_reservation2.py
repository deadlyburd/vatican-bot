"""Extract ALL headers from the working reservation request."""
import json, base64

with open('D:/bot/travelagenntbot/epay.catholica.va.har', 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

for e in data.get('log', {}).get('entries', []):
    url = e.get('request', {}).get('url', '')
    if 'reservation' not in url:
        continue
    req = e['request']
    resp = e['response']
    print(f"URL: {url}")
    print(f"Status: {resp.get('status')}")
    print("\nALL REQUEST HEADERS:")
    for h in req.get('headers', []):
        print(f"  {h['name']}: {h['value']}")
    print("\nALL REQUEST COOKIES:")
    for c in req.get('cookies', []):
        print(f"  {c['name']}={c['value'][:50]}")
    print("\nRESPONSE BODY:")
    rc = resp.get('content', {})
    rt = rc.get('text', '')
    if rc.get('encoding') == 'base64':
        try: rt = base64.b64decode(rt).decode('utf-8', errors='replace')
        except: pass
    try:
        rb = json.loads(rt)
        print(json.dumps(rb, indent=2, ensure_ascii=False)[:2000])
    except:
        print(rt[:500])
    print("\nRESPONSE HEADERS:")
    for h in resp.get('headers', []):
        print(f"  {h['name']}: {h['value']}")
