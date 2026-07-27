import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from monitors.epay_ssl import make_vatican_session

BASE = 'https://tickets.museivaticani.va'
H = {'Accept':'application/json','X-Requested-With':'XMLHttpRequest','Referer':f'{BASE}/'}

s = make_vatican_session(use_proxy=True)

for date, visitors in [('19/06/2026', 1), ('09/05/2026', 1)]:
    r = s.get(f'{BASE}/api/search/resultPerTag', params={
        'lang':'it','visitorNum':str(visitors),'visitDate':date,
        'area':'1','who':'','page':'0','tag':'MV-Biglietti'
    }, headers=H, timeout=10)
    if r.status_code != 200:
        print(f"{date}: API error {r.status_code}")
        continue
    ticket = next((v for v in r.json().get('visits',[])
                   if 'musei vaticani' in v.get('name','').lower()
                   and 'ingresso' in v.get('name','').lower()), None)
    if not ticket:
        print(f"{date}: No standard entry ticket found")
        continue
    avail = ticket.get('availability')
    tid = ticket['id']
    print(f"{date}: ticket availability={avail}")

    if avail in ('AVAILABLE','LOW_AVAILABILITY'):
        r2 = s.get(f'{BASE}/api/visit/timeavail', params={
            'lang':'it','visitLang':'','visitTypeId':str(tid),
            'visitorNum':str(visitors),'visitDate':date,
        }, headers=H, timeout=10)
        if r2.status_code == 200:
            slots = [(sl['time'], sl['availability']) for sl in r2.json().get('timetable',[])
                     if sl.get('availability') not in ('SOLD_OUT','NOT_ALLOWED')]
            print(f"  Available slots: {slots}")
    else:
        print(f"  → SOLD_OUT — bot will grab it when it opens")
