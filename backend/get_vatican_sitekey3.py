import requests, re

BASE = 'https://tickets.museivaticani.va'

# Fetch main JS bundle
url = f'{BASE}/main-WMSSQ66J.js'
print(f"Fetching {url}...")
r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
print(f"Status: {r.status_code} | Size: {len(r.text)}")

keys = re.findall(r'6L[A-Za-z0-9_-]{38}', r.text)
print(f"reCAPTCHA keys: {list(set(keys))}")

# Also search for recaptcha/grecaptcha references
recaptcha_refs = re.findall(r'.{20}recaptcha.{20}', r.text[:50000])
for ref in recaptcha_refs[:5]:
    print(f"  ref: {ref}")
