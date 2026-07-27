"""Quick scan to find first open Vatican date — no proxy, direct from this PC."""
import requests, sys
from datetime import datetime, timedelta

BASE = 'https://tickets.museivaticani.va'
H = {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest', 'Referer': f'{BASE}/'}
VISITORS = 2

s = requests.Session()
found = []

for i in range(1, 120):
    d = (datetime.now() + timedelta(days=i)).strftime('%d/%m/%Y')
    try:
        r = s.get(f'{BASE}/api/search/resultPerTag', params={
            'lang': 'it', 'visitorNum': str(VISITORS), 'visitDate': d,
            'area': '1', 'who': '', 'page': '0', 'tag': 'MV-Biglietti'
        }, headers=H, timeout=8)
        if r.status_code != 200:
            continue
        ticket = next((v for v in r.json().get('visits', [])
                       if 'musei vaticani' in v.get('name', '').lower()
                       and 'ingresso' in v.get('name', '').lower()), None)
        if not ticket:
            continue
        avail = ticket.get('availability', '?')
        tid = ticket.get('id')
        if avail in ('AVAILABLE', 'LOW_AVAILABILITY'):
            print(f'\nOPEN: {d}  id={tid}  avail={avail}')
            found.append({'date': d, 'id': tid, 'avail': avail})
            if len(found) >= 3:
                break
        else:
            sys.stdout.write(f'\r  Checking {d}: {avail}   ')
            sys.stdout.flush()
    except Exception as e:
        print(f'\nERR {d}: {e}')
        break

print()
if not found:
    print('No open dates in next 120 days')
else:
    print(f'\nFirst open date: {found[0]["date"]}')
