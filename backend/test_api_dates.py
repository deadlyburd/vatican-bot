import requests, sys, os
sys.path.insert(0, '.')
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'

session = requests.Session()
headers = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://tickets.museivaticani.va/'
}

dates = ['17/03/2026', '18/03/2026', '19/03/2026', '21/03/2026', '23/03/2026', '25/03/2026', '26/03/2026', '30/03/2026']

print("=== SEARCH API TEST (MV-Biglietti, 2 visitors) ===")
for date in dates:
    try:
        r = session.get(
            'https://tickets.museivaticani.va/api/search/resultPerTag',
            params={'lang':'it','visitorNum':'2','visitDate':date,'area':'1','who':'','page':'0','tag':'MV-Biglietti'},
            headers=headers,
            timeout=15
        )
        data = r.json()
        visits = data.get('visits', [])
        jsession = r.cookies.get('JSESSIONID', 'NONE')
        short_js = jsession[:15] if jsession != 'NONE' else 'NONE'
        print(f"{date} | HTTP {r.status_code} | {len(visits)} tickets | JSESSION={short_js}")
        for v in visits[:3]:
            print(f"  -> id={v.get('id')} | {v.get('name','?')[:50]} | {v.get('availability')}")
    except Exception as e:
        print(f"{date} | EXCEPTION: {e}")

print()
print("=== SEARCH API TEST (MV-Visite-Guidate, 2 visitors) ===")
session2 = requests.Session()
for date in ['23/03/2026', '30/03/2026']:
    try:
        r = session2.get(
            'https://tickets.museivaticani.va/api/search/resultPerTag',
            params={'lang':'it','visitorNum':'2','visitDate':date,'area':'1','who':'','page':'0','tag':'MV-Visite-Guidate'},
            headers=headers,
            timeout=15
        )
        data = r.json()
        visits = data.get('visits', [])
        print(f"{date} | HTTP {r.status_code} | {len(visits)} guided tickets")
        for v in visits[:3]:
            print(f"  -> id={v.get('id')} | {v.get('name','?')[:50]} | {v.get('availability')}")
    except Exception as e:
        print(f"{date} | EXCEPTION: {e}")

# Now test timeavail for one ticket if we got IDs
print()
print("=== TIMEAVAIL TEST ===")
