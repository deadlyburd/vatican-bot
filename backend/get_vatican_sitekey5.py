import requests, re

BASE = 'https://tickets.museivaticani.va'

# Check all referenced chunks
chunks = ['chunk-S2KQPZGL.js', 'chunk-BEW4AJNQ.js', 'polyfills-5FDKUQTZ.js', 'main-WMSSQ66J.js']

for chunk in chunks:
    url = f'{BASE}/{chunk}'
    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
    print(f"{chunk}: {r.status_code} | {len(r.text)} bytes")
    if r.status_code == 200:
        # Search for 6L keys
        keys = re.findall(r'6L[A-Za-z0-9_-]{38}', r.text)
        if keys:
            print(f"  KEYS: {list(set(keys))}")
        # Search for recaptcha
        hits = re.findall(r'.{0,40}[Rr]ecaptcha.{0,40}', r.text)
        for h in hits[:3]:
            print(f"  {h}")
        # Search for sitekey pattern
        sk = re.findall(r'["\']([A-Za-z0-9_-]{40})["\']', r.text)
        if sk:
            print(f"  40-char strings (possible keys): {list(set(sk))[:3]}")
