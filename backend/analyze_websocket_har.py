"""
Deep analysis of websocket.har — extract ALL requests including
fetch, XHR, WebSocket, and the full reservation flow.
"""
import json, base64, sys

import json, base64, sys, re

filepath = 'D:/bot/travelagenntbot/websocket.har'

# Read raw bytes
with open(filepath, 'rb') as f:
    raw = f.read()

# Try multiple parsing strategies
data = None
for strategy in ['direct', 'crlf_strip', 'errors_ignore']:
    try:
        if strategy == 'direct':
            data = json.loads(raw.decode('utf-8'))
        elif strategy == 'crlf_strip':
            content = raw.decode('utf-8', errors='replace')
            content = content.replace('\r\n', '\\n').replace('\r', '\\n')
            data = json.loads(content)
        elif strategy == 'errors_ignore':
            # Use json with strict=False equivalent
            content = raw.decode('utf-8', errors='replace')
            # Remove all control chars except \t \n
            content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', content)
            data = json.loads(content)
        print(f"Parsed with strategy: {strategy}")
        break
    except Exception as e:
        print(f"Strategy {strategy} failed: {str(e)[:100]}")

if not data:
    print("All strategies failed — trying line-by-line extraction")
    # Extract entries manually using regex
    content = raw.decode('utf-8', errors='replace')
    # Find all URL patterns
    urls = re.findall(r'"url"\s*:\s*"(https://[^"]+)"', content)
    methods = re.findall(r'"method"\s*:\s*"([A-Z]+)"', content)
    statuses = re.findall(r'"status"\s*:\s*(\d+)', content)
    print(f"\nFound {len(urls)} URLs via regex:")
    for i, url in enumerate(urls[:50]):
        m = methods[i] if i < len(methods) else '?'
        st = statuses[i] if i < len(statuses) else '?'
        if any(x in url for x in ['recap', 'reservation', 'timeavail', 'resultPerTag',
                                    'services', 'checkout', 'config', 'gdpr']):
            print(f"  [{m}] {st} {url}")
    sys.exit(0)

entries = data.get('log', {}).get('entries', [])
print(f"Total entries: {len(entries)}\n")

# Print ALL URLs to see the full flow
print("=== ALL REQUESTS (chronological) ===")
for i, e in enumerate(entries):
    req = e.get('request', {})
    resp = e.get('response', {})
    url = req.get('url', '')
    method = req.get('method', '?')
    status = resp.get('status', '?')
    # Skip static assets
    if any(x in url for x in ['.js', '.css', '.png', '.jpg', '.svg', '.ico', '.woff', '.ttf']):
        continue
    print(f"{i:3}. [{method}] {status} {url[:100]}")

print("\n\n=== DETAILED API CALLS ===")
INTERESTING = ['recap', 'reservation', 'timeavail', 'resultPerTag', 'services',
               'visit?lang', 'checkout', 'config', 'gdpr', 'country', 'representetive',
               'purchaserules', 'calendar', 'filter', 'startup', 'initValues']

for e in entries:
    req = e.get('request', {})
    resp = e.get('response', {})
    url = req.get('url', '')
    method = req.get('method', '?')
    status = resp.get('status', '?')

    if not any(x in url for x in INTERESTING):
        continue

    print(f"\n{'='*65}")
    print(f"[{method}] {status} {url}")

    # ALL request headers
    hdrs = {h['name']: h['value'] for h in req.get('headers', [])}
    print("Request headers:")
    for k, v in hdrs.items():
        if k.lower() not in [':authority', ':method', ':path', ':scheme',
                               'accept-encoding', 'priority']:
            print(f"  {k}: {v}")

    # Cookies
    cookies = {c['name']: c['value'] for c in req.get('cookies', [])}
    if cookies:
        print(f"Cookies: {cookies}")

    # Request body
    pd = req.get('postData', {})
    if pd.get('text'):
        try:
            body = json.loads(pd['text'])
            print("REQUEST BODY:")
            print(json.dumps(body, indent=2, ensure_ascii=False)[:3000])
        except:
            print(f"REQUEST (raw): {pd['text'][:500]}")

    # Response
    rc = resp.get('content', {})
    rt = rc.get('text', '')
    if rc.get('encoding') == 'base64':
        try: rt = base64.b64decode(rt).decode('utf-8', errors='replace')
        except: pass
    if rt and len(rt) < 5000:
        try:
            rb = json.loads(rt)
            print("RESPONSE BODY:")
            print(json.dumps(rb, indent=2, ensure_ascii=False)[:3000])
        except:
            if len(rt) < 1000:
                print(f"RESPONSE (raw): {rt[:500]}")

    # Response cookies
    rc2 = resp.get('cookies', [])
    if rc2:
        print(f"Set-Cookie: {[c['name']+'='+c['value'][:40] for c in rc2]}")
