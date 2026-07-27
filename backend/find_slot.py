import os,sys,django,time
sys.path.insert(0,os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','core.settings')
django.setup()
from monitors.epay_ssl import make_vatican_session
from datetime import datetime,timedelta
BASE='https://tickets.museivaticani.va'
H={'Accept':'application/json','X-Requested-With':'XMLHttpRequest','Referer':BASE+'/'}
s=make_vatican_session(use_proxy=True)
for days in range(1,120):
    d=(datetime.now()+timedelta(days=days)).strftime('%d/%m/%Y')
    r=s.get(f'{BASE}/api/search/resultPerTag',params={'lang':'it','visitorNum':'1','visitDate':d,'area':'1','who':'','page':'0','tag':'MV-Biglietti'},headers=H,timeout=12)
    if r.status_code!=200: continue
    t=next((v for v in r.json().get('visits',[]) if 'musei vaticani' in v.get('name','').lower() and 'ingresso' in v.get('name','').lower() and v.get('availability') in ('AVAILABLE','LOW_AVAILABILITY')),None)
    if not t: continue
    r2=s.get(f'{BASE}/api/visit/timeavail',params={'lang':'it','visitLang':'','visitTypeId':str(t['id']),'visitorNum':'1','visitDate':d},headers=H,timeout=12)
    if r2.status_code!=200: continue
    slots=[sl for sl in r2.json().get('timetable',[]) if sl.get('availability') not in ('SOLD_OUT','NOT_ALLOWED')]
    if slots:
        st=slots[0]
        print(f"FOUND: date={d} time={st['time']} avail={st['availability']} id={st['id']}")
        break
    time.sleep(0.1)
