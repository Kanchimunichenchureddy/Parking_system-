import os
import tempfile
os.environ['DATABASE_URL']=os.getenv('TEST_DATABASE_URL','sqlite:///'+tempfile.mktemp(prefix='parkreceipt-test-',suffix='.db'))
os.environ['APP_ORIGIN']='http://testserver'
import uuid
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.models import Base,engine,Session,Location,User,Receipt,PaymentRequest
from app.main import app,hasher,limits

@pytest.fixture(autouse=True)
def setup():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine);limits.clear()
    with Session() as s:
        s.add_all([Location(id=1,slug='parking-a',name='Parking A',rate=3000),Location(id=2,slug='parking-b',name='Parking B',rate=3000)])
        s.flush()
        s.add_all([User(username='owner',role='owner',password_hash=hasher.hash('test-password')),User(username='staff-a',role='staff',location_id=1,password_hash=hasher.hash('test-password')),User(username='staff-b',role='staff',location_id=2,password_hash=hasher.hash('test-password'))]);s.commit()

def client(user=None):
    c=TestClient(app)
    if user: assert c.post('/api/login',json={'username':user,'password':'test-password'}).status_code==200
    return c

def new(c,method='cash',**kw):
    data=dict(location_slug='parking-a',vehicle=' ka 01 ab 1234 ',method=method,idempotency_key=str(uuid.uuid4()));data.update(kw)
    r=c.post('/api/requests',json=data);assert r.status_code==200,r.text
    return r.json()

def report(c,**kw):
    from app.main import IST
    day=datetime.now(IST).date().isoformat()
    return c.get('/api/owner/report',params=dict(start=day,end=day,**kw)).json()

def test_cash_duplicate_and_permissions():
    c=client(); r=new(c,amount=1); token=r['token'];assert r['amount']==3000 and r['vehicle']=='KA01AB1234'
    assert c.get('/api/staff/requests').status_code==401
    assert client('staff-b').post(f'/api/staff/requests/{token}/approve').status_code==403
    a=client('staff-a'); o=client('owner'); assert report(o)['cash_total']==0
    first=a.post(f'/api/staff/requests/{token}/approve').json();second=a.post(f'/api/staff/requests/{token}/approve').json()
    assert first['receipt_number']==second['receipt_number']
    assert c.get(f'/api/receipts/{token}').json()['state']=='confirmed'
    assert report(o)['cash_total']==3000
    assert c.post(f'/api/requests/{token}/cancel').status_code==409
    assert c.get('/api/receipts/1').status_code==404

def test_demo_states():
    c=client(); o=client('owner')
    for state in ['failed','cancelled','confirmed']:
        r=new(c,'demo'); t=r['token'];x=c.post(f'/api/requests/{t}/simulate',json={'outcome':state});assert x.status_code==200
        assert c.get(f'/api/receipts/{t}').status_code==(200 if state=='confirmed' else 409)
    totals=report(o);assert totals['cash_total']==0 and totals['demo_total']==3000

def test_rates_and_idempotency():
    c=client();key=str(uuid.uuid4());r=new(c,idempotency_key=key)
    assert new(c,idempotency_key=key)['token']==r['token']
    o=client('owner');assert o.patch('/api/owner/locations/1',json={'rate':5000}).status_code==200
    assert c.get('/api/requests/'+r['token']).json()['amount']==3000
    assert new(c)['amount']==5000
    assert c.post('/api/requests',json=dict(location_slug='parking-a',vehicle='OTHER',method='cash',idempotency_key=key)).status_code==409

def test_concurrent_approval():
    c=client('staff-a');r=new(c)
    cookies=dict(c.cookies)
    def approve(_):
        with TestClient(app) as x:
            x.cookies.update(cookies)
            return x.post('/api/staff/requests/'+r['token']+'/approve')
    with ThreadPoolExecutor(max_workers=5) as pool: responses=list(pool.map(approve,range(5)))
    assert all(x.status_code==200 for x in responses)
    assert len({x.json()['receipt_number'] for x in responses})==1
    with Session() as s: assert s.scalar(select(func.count()).select_from(Receipt))==1

def test_timezone_export_and_logout():
    c=client('staff-a');r=new(c);c.post('/api/staff/requests/'+r['token']+'/approve')
    with Session() as s:
        row=s.scalar(select(PaymentRequest));row.confirmed_at=datetime(2026,1,1,18,30);s.commit()
    o=client('owner');args={'start':'2026-01-02','end':'2026-01-02'}
    assert o.get('/api/owner/report',params=args).json()['cash_count']==1
    assert o.get('/api/owner/report',params={'start':'2026-01-01','end':'2026-01-01'}).json()['cash_count']==0
    assert 'KA01AB1234' in o.get('/api/owner/export',params=args).text
    o.post('/api/logout');assert o.get('/api/owner/report',params=args).status_code==401

def test_security_and_demo_disabled(monkeypatch):
    c=client('staff-a')
    assert c.patch('/api/owner/locations/1',json={'rate':2}).status_code==403
    assert c.post('/api/requests',headers={'origin':'https://evil.example'},json={}).status_code==403
    r=new(c,'demo')
    monkeypatch.setattr('app.main.DEMO',False)
    assert c.post('/api/requests/'+r['token']+'/simulate',json={'outcome':'confirmed'}).status_code==404

def test_persistence_pending_cancel_and_assignment():
    c=client();r=new(c);engine.dispose()
    assert client().get('/api/requests/'+r['token']).json()['state']=='pending'
    assert c.get('/api/receipts/'+r['token']).status_code==409
    assert c.post('/api/requests/'+r['token']+'/cancel').json()['state']=='cancelled'
    assert client('staff-a').post('/api/staff/requests/'+r['token']+'/approve').status_code==409
    o=client('owner');assert o.patch('/api/owner/users/2',json={'location_id':2}).status_code==200
    r=new(c)
    assert client('staff-a').post('/api/staff/requests/'+r['token']+'/approve').status_code==403

def test_concurrent_creation_recovers_same_request():
    key=str(uuid.uuid4())
    data=dict(location_slug='parking-a',vehicle='TEST01',method='cash',idempotency_key=key)
    def create(_):
        with TestClient(app) as c:return c.post('/api/requests',json=data)
    with ThreadPoolExecutor(max_workers=5) as pool: results=list(pool.map(create,range(5)))
    assert all(r.status_code==200 for r in results),[r.text for r in results]
    assert len({r.json()['token'] for r in results})==1
    with Session() as s:assert s.scalar(select(func.count()).select_from(PaymentRequest))==1

def test_export_matches_report_filters_and_escapes_cells():
    import csv,io
    o=client('owner');r=new(o,vehicle='-FORMULA');o.post('/api/staff/requests/'+r['token']+'/approve')
    demo=new(o,'demo');o.post('/api/requests/'+demo['token']+'/simulate',json={'outcome':'confirmed'})
    from app.main import IST
    day=datetime.now(IST).date().isoformat()
    params=dict(start=day,end=day,method='cash',location_id=1,search='-FORMULA')
    result=o.get('/api/owner/report',params=params).json()
    records=list(csv.DictReader(io.StringIO(o.get('/api/owner/export',params=params).text)))
    assert result['total']==len(records)==1
    assert records[0]['Vehicle']=="'-FORMULA"
    assert result['demo_total']==0

def test_staff_entry_enforces_location_and_method():
    data=dict(location_slug='parking-a',vehicle='WALKIN01',method='cash',idempotency_key=str(uuid.uuid4()))
    assert client().post('/api/staff/requests',json=data).status_code==401
    assert client('staff-b').post('/api/staff/requests',json=data).status_code==403
    c=client('staff-a');r=c.post('/api/staff/requests',json=data)
    assert r.status_code==200 and r.json()['state']=='pending'
    assert c.post('/api/staff/requests',json=data).json()['token']==r.json()['token']
    assert c.post('/api/staff/requests',json={**data,'method':'demo'}).status_code==400

def test_pending_queue_survives_large_confirmed_history():
    c=client('staff-a');pending=new(c)
    with Session() as s:
        for n in range(205):
            s.add(PaymentRequest(token=str(uuid.uuid4()),idempotency_key=str(uuid.uuid4()),reference=f'H{n}',location_id=1,vehicle=f'TEST{n}',amount=3000,method='cash',state='confirmed',confirmed_at=datetime.now()))
        s.commit()
    rows=c.get('/api/staff/requests').json()
    assert rows[0]['token']==pending['token']
    assert len(rows)==51
