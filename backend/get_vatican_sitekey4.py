import requests, re

BASE = 'https://tickets.museivaticani.va'

# Check all chunk JS files
r_home = requests.get(f'{BASE}/home', headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)

# Get all JS files referenced
all_js = re.findall(r'["\']([A-Za-z0-9_-]+\.js)["\']', r_home.text)
print(f"JS files referenced: {all_js[:10]}")

# Also check the chunk files from the HAR — we know chunk-RSPFXPKX.js has timeavail
chunk_files = ['chunk-RSPFXPKX.js', 'chunk-BEW4AJNQ.js', 'chunk-6AFO56VB.js']

for chunk in chunk_files:
    url = f'{BASE}/{chunk}'
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if r.status_code == 200:
            keys = re.findall(r'6L[A-Za-z0-9_-]{38}', r.text)
            recaptcha = re.findall(r'.{0,30}[Rr]ecaptcha.{0,30}', r.text[:100000])
            if keys or recaptcha:
                print(f"\n{chunk} ({len(r.text)} bytes):")
                print(f"  Keys: {list(set(keys))}")
                for ref in recaptcha[:3]:
                    print(f"  ref: {ref}")
    except Exception as e:
        print(f"  {chunk}: {e}")

# Try fetching the checkout page with a real browser UA and look for grecaptcha
r2 = requests.get(f'{BASE}/home/checkout',
    headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml',
    }, timeout=15)

# Search for site key pattern in all content
all_keys = re.findall(r'6L[A-Za-z0-9_-]{38}', r2.text)
print(f"\nCheckout page keys: {list(set(all_keys))}")

# Look for render= pattern (how v3 is loaded)
render = re.findall(r'render=([^&\s"\']+)', r2.text)
print(f"Render: {render}")

# Search for siteKey or site_key
sitekey = re.findall(r'[sS]ite[Kk]ey["\s:=]+([A-Za-z0-9_-]{20,})', r2.text)
print(f"siteKey: {sitekey}")
