import requests, re

BASE = 'https://tickets.museivaticani.va'

# Get the main page to find JS bundle URLs
r = requests.get(f'{BASE}/home', headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
print(f"Home: {r.status_code}")

# Find all script src
scripts = re.findall(r'src="([^"]+\.js[^"]*)"', r.text)
print(f"Scripts: {scripts}")

# Also look in the raw HTML for any 6L keys
keys = re.findall(r'6L[A-Za-z0-9_-]{38}', r.text)
print(f"Keys in home HTML: {keys}")

# Try the main bundle directly
for script in scripts:
    url = script if script.startswith('http') else f'{BASE}{script}'
    try:
        rj = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        keys = re.findall(r'6L[A-Za-z0-9_-]{38}', rj.text)
        if keys:
            print(f"\nFound in {url}:")
            print(f"  Keys: {list(set(keys))}")
    except Exception as e:
        print(f"Error fetching {url}: {e}")
