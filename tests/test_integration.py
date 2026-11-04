"""Integration tests intentionally use an isolated database, never application data."""
import os
import uuid
from datetime import timedelta
import pytest

if os.getenv('TEST_DATABASE_URL'):
    os.environ['DATABASE_URL']=os.environ['TEST_DATABASE_URL']

from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import Base, Session, Ticket, Review, engine, utcnow
from app import jobs
from app.config import settings


@pytest.fixture

def db_setup(monkeypatch):
    monkeypatch.setattr(settings(),"auto_routing_enabled",True)
    url=os.environ.get('TEST_DATABASE_URL','')
    if not url:
        pytest.skip('Set TEST_DATABASE_URL to a dedicated PostgreSQL test database')
    if not url.rsplit('/',1)[-1].startswith('router_test'):
        pytest.fail('Refusing to clear a non-test database')
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(Review.__table__.delete())
        connection.execute(Ticket.__table__.delete())
    yield


@pytest.fixture

def client(db_setup):
    return TestClient(app)


@pytest.fixture

def fake_model(monkeypatch):
    class Model:
        metadata={'threshold':.8,'version':'TEST-FIXTURE-NOT-REAL-METRICS'}
        def predict(self,text):
            return 'ORDER', .95 if 'order' in text else .25, .1
    model=Model()
    monkeypatch.setattr(jobs,'predictor',lambda:model)
    return model


def submit(client,text='Please track my order',key=None):
    return client.post('/api/tickets',json={'text':text},headers={'Idempotency-Key':key or str(uuid.uuid4())})


@pytest.mark.integration

def test_idempotency_and_conflict(client):
    first=submit(client,key='same')
    assert first.status_code==202
    assert submit(client,key='same').json()['id']==first.json()['id']
    assert submit(client,'A different support request',key='same').status_code==409
    assert client.get('/api/tickets').json()['total']==1


@pytest.mark.integration

def test_parallel_duplicate_submissions(client):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as executor:
        results=list(executor.map(lambda _:submit(client,key='concurrent'),range(8)))
    assert all(r.status_code==202 for r in results)
    assert len({r.json()['id'] for r in results})==1


@pytest.mark.integration

def test_routing_and_duplicate_delivery(client,fake_model):
    ticket=submit(client).json()
    jobs.process_ticket(ticket['id'],0)
    jobs.process_ticket(ticket['id'],0)
    result=client.get('/api/tickets/'+ticket['id']).json()
    assert result['status']=='routed' and result['assigned_team']=='Order Operations'
    assert result['attempts']==1


@pytest.mark.integration

def test_review_preserves_prediction(client,fake_model):
    ticket=submit(client,'Something strange happened').json()
    jobs.process_ticket(ticket['id'],0)
    result=client.get('/api/tickets/'+ticket['id']).json()
    assert result['status']=='review' and result['assigned_team'] is None
    body={'category':'PAYMENT','reviewer':'test','note':'Synthetic fixture'}
    assert client.post('/api/tickets/'+ticket['id']+'/review',json=body).status_code==200
    result=client.get('/api/tickets/'+ticket['id']).json()
    assert result['predicted_category']=='ORDER'
    assert result['review']['category']=='PAYMENT' and result['assigned_team']=='Billing'
    assert client.post('/api/tickets/'+ticket['id']+'/review',json=body).status_code==409


@pytest.mark.integration

def test_retry_backoff_and_bound(client,fake_model):
    def fail(text):
        raise RuntimeError('fixture failure')
    fake_model.predict=fail
    ticket=submit(client).json()
    for attempt in range(settings().max_attempts):
        before=utcnow()
        with pytest.raises(RuntimeError):
            jobs.process_ticket(ticket['id'],attempt)
        with Session() as db:
            row=db.get(Ticket,ticket['id'])
            assert row.attempts==attempt+1
            assert row.dispatch_after>=before+timedelta(seconds=settings().retry_base_seconds*2**attempt)
        # Delayed duplicate delivery cannot consume another attempt.
        jobs.process_ticket(ticket['id'],attempt)
    assert client.get('/api/tickets/'+ticket['id']).json()['status']=='failed'


@pytest.mark.integration

def test_worker_restart_and_fencing(client,fake_model):
    ticket=submit(client).json()
    with Session.begin() as db:
        row=db.get(Ticket,ticket['id'])
        row.status='processing'
        row.attempts=1
        row.lease_token='abandoned-worker'
        row.lease_until=utcnow()-timedelta(seconds=1)
    jobs.process_ticket(ticket['id'],1)
    result=client.get('/api/tickets/'+ticket['id']).json()
    assert result['status']=='routed' and result['attempts']==2


@pytest.mark.integration

def test_live_lease_blocks_duplicate(client,fake_model):
    ticket=submit(client).json()
    with Session.begin() as db:
        row=db.get(Ticket,ticket['id'])
        row.status='processing'
        row.lease_until=utcnow()+timedelta(seconds=90)
    jobs.process_ticket(ticket['id'],0)
    assert client.get('/api/tickets/'+ticket['id']).json()['attempts']==0


@pytest.mark.integration

def test_redis_delivery_and_recovery(client,fake_model):
    from rq import SimpleWorker
    q=jobs.queue()
    try:
        q.connection.ping()
    except Exception:
        pytest.skip('Redis unavailable')
    q.empty()
    ticket=submit(client).json()
    assert jobs.dispatch_once()==1
    assert jobs.dispatch_once()==0
    # Simulate loss after Redis accepted delivery, before the worker ran.
    q.empty()
    with Session.begin() as db:
        db.get(Ticket,ticket['id']).dispatch_after=utcnow()-timedelta(seconds=1)
    assert jobs.dispatch_once()==1
    SimpleWorker([q],connection=q.connection).work(burst=True)
    assert client.get('/api/tickets/'+ticket['id']).json()['status']=='routed'


@pytest.mark.integration

def test_queue_outage_keeps_durable_ticket(client,monkeypatch):
    def unavailable():
        raise ConnectionError('fixture queue outage')
    monkeypatch.setattr(jobs,'queue',unavailable)
    ticket=submit(client).json()
    with pytest.raises(ConnectionError):
        jobs.dispatch_once()
    assert client.get('/api/tickets/'+ticket['id']).json()['status']=='queued'


@pytest.mark.integration

def test_filters_and_validation(client):
    assert submit(client,'short').status_code==422
    assert submit(client,'x'*5001).status_code==422
    assert submit(client).status_code==202
    assert client.get('/api/tickets?status=review').json()['total']==0
    assert client.get('/api/tickets?limit=0').status_code==422
    assert client.get('/api/tickets/missing').status_code==404

@pytest.mark.integration

def test_retry_not_dispatched_before_backoff(client,fake_model):
    ticket=submit(client).json()
    with Session.begin() as db:
        row=db.get(Ticket,ticket['id'])
        row.dispatch_after=utcnow()+timedelta(seconds=30)
    assert jobs.dispatch_once()==0


@pytest.mark.integration

def test_expired_processing_lease_is_redispatched(client,fake_model):
    q=jobs.queue()
    q.empty()
    ticket=submit(client).json()
    with Session.begin() as db:
        row=db.get(Ticket,ticket['id'])
        row.status='processing'
        row.attempts=1
        row.lease_token='crashed'
        row.lease_until=utcnow()-timedelta(seconds=1)
    assert jobs.dispatch_once()==1
    from rq import SimpleWorker
    SimpleWorker([q],connection=q.connection).work(burst=True)
    result=client.get('/api/tickets/'+ticket['id']).json()
    assert result['status']=='routed' and result['attempts']==2


@pytest.mark.integration

def test_stale_result_cannot_overwrite_new_owner(client,fake_model):
    ticket=submit(client).json()
    def stolen(text):
        with Session.begin() as db:
            row=db.get(Ticket,ticket['id'])
            row.lease_token='new-owner'
            row.status='reviewed'
            row.assigned_team='Protected team'
        return 'ORDER',.99,1.
    fake_model.predict=stolen
    jobs.process_ticket(ticket['id'],0)
    result=client.get('/api/tickets/'+ticket['id']).json()
    assert result['status']=='reviewed' and result['assigned_team']=='Protected team'


@pytest.mark.integration
def test_manual_mode_overrides_high_confidence(client,fake_model,monkeypatch):
    monkeypatch.setattr(settings(),"auto_routing_enabled",False)
    ticket=submit(client).json()
    jobs.process_ticket(ticket['id'],0)
    result=client.get('/api/tickets/'+ticket['id']).json()
    assert result['status']=='review' and result['confidence']==.95
    assert result['routing_evidence']['candidate_auto_route'] is True
    assert 'automatic_routing_disabled' in result['routing_evidence']['review_reasons']

@pytest.mark.integration
@pytest.mark.parametrize('text',[
    'Money left my account two times for one purchase.',
    'Something is wrong. Please help.',
    'I was charged twice for the same order. Can you refund the extra payment?'])
def test_real_development_cases_are_reviewed(client,monkeypatch,text):
    from pathlib import Path
    from app.predictor import Predictor
    if not Path('artifacts/robustness/deployed/model.joblib').exists():
        pytest.skip('Local trained artifact unavailable; do not download in CI')
    actual=Predictor('artifacts/robustness/deployed')
    monkeypatch.setattr(jobs,'predictor',lambda:actual)
    monkeypatch.setattr(settings(),'auto_routing_enabled',False)
    ticket=submit(client,text).json()
    jobs.process_ticket(ticket['id'],0)
    result=client.get('/api/tickets/'+ticket['id']).json()
    assert result['status']=='review' and result['assigned_team'] is None
    assert result['model_version'].startswith('robust-')
    assert 'automatic_routing_disabled' in result['routing_evidence']['review_reasons']

@pytest.mark.integration
def test_public_demo_only_accepts_synthetic_examples(client,monkeypatch):
    from app.main import demo_examples
    monkeypatch.setattr(settings(),'demo_mode',True)
    assert submit(client,'Do not accept arbitrary private visitor content').status_code==422
    assert submit(client,demo_examples()[0]).status_code==202


@pytest.mark.integration
def test_public_demo_bounds_storage_and_preserves_idempotency(client,monkeypatch):
    from app.main import demo_examples
    monkeypatch.setattr(settings(),'demo_mode',True)
    monkeypatch.setattr(settings(),'demo_ticket_limit',1)
    first=submit(client,demo_examples()[0],key='quota').json()
    assert submit(client,demo_examples()[0],key='quota').json()['id']==first['id']
    assert submit(client,demo_examples()[1]).status_code==429


@pytest.mark.integration
def test_public_demo_does_not_store_review_free_text(client,fake_model,monkeypatch):
    from app.main import demo_examples
    monkeypatch.setattr(settings(),'demo_mode',True)
    monkeypatch.setattr(settings(),'auto_routing_enabled',False)
    ticket=submit(client,demo_examples()[1]).json()
    jobs.process_ticket(ticket['id'],0)
    path='/api/tickets/'+ticket['id']+'/review'
    assert client.post(path,json={'category':'PAYMENT','reviewer':'Someone','note':'Private text'}).status_code==422
    assert client.post(path,json={'category':'PAYMENT','reviewer':'Someone','note':''}).status_code==200
    result=client.get('/api/tickets/'+ticket['id']).json()
    assert result['review']['reviewer']=='Demo visitor' and result['review']['note']==''

@pytest.mark.integration
def test_public_demo_concurrent_replays_respect_quota(client,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from app.main import demo_examples
    monkeypatch.setattr(settings(),'demo_mode',True)
    monkeypatch.setattr(settings(),'demo_ticket_limit',1)
    with ThreadPoolExecutor(8) as executor:
        replies=list(executor.map(lambda _:submit(client,demo_examples()[0],key='demo-race'),range(8)))
    assert all(reply.status_code==202 for reply in replies)
    assert len({reply.json()['id'] for reply in replies})==1
