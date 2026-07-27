import requests
from datetime import datetime, timedelta

# Test dates in June and July 2026
test_dates = []
start_date = datetime(2026, 6, 1)
for i in range(60):  # Check 60 days starting from June 1
    test_dates.append((start_date + timedelta(days=i)).strftime('%d/%m/%Y'))

print('Searching for available Vatican tickets in June/July 2026...\n')

url = 'https://tickets.museivaticani.va/api/search/resultPerTag'
headers = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://tickets.museivaticani.va/'
}

available_dates = []

for date in test_dates[:20]:  # Check first 20 dates
    params = {
        'lang': 'it',
        'visitorNum': '1',
        'visitDate': date,
        'area': '1',
        'who': '',
        'page': '0',
        'tag': 'MV-Biglietti'
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            visits = data.get('visits', [])
            
            # Check if any tickets are available
            has_available = any(v.get('availability') == 'AVAILABLE' for v in visits)
            
            if has_available:
                available_dates.append(date)
                print(f'✓ {date} - AVAILABLE')
                for v in visits:
                    if v.get('availability') == 'AVAILABLE':
                        ticket_name = v.get('name', 'Unknown')
                        availability = v.get('availability')
                        print(f'  - {ticket_name}: {availability}')
            else:
                print(f'✗ {date} - No availability')
    except Exception as e:
        print(f'✗ {date} - Error: {str(e)}')

print(f'\n\nFound {len(available_dates)} dates with availability:')
for date in available_dates[:5]:
    print(f'  - {date}')
