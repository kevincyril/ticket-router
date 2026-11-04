"""Smoke-test the real hosted demo. No training or fixture model involved."""
import argparse
import json
from pathlib import Path
import time
import uuid
import httpx


def main(base):
    with httpx.Client(base_url=base,timeout=10) as client:
        for attempt in range(90):
            try:
                if client.get('/api/health/ready').status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(1)
        else:raise SystemExit('Hosted readiness did not become healthy')
        metadata=client.get('/api/model').json()
        assert metadata['demo_mode'] is True
        assert metadata['automatic_routing_enabled'] is False
        headers={'Idempotency-Key':str(uuid.uuid4())}
        invalid=client.post('/api/tickets',json={'text':'tiny'},headers=headers)
        assert invalid.status_code==422
        response=client.post('/api/tickets',json={'text':'One notebook purchase appears twice on my statement. Demo '+uuid.uuid4().hex[:8]},headers=headers)
        response.raise_for_status();ticket=response.json()
        for attempt in range(90):
            response=client.get('/api/tickets/'+ticket['id']);response.raise_for_status();ticket=response.json()
            if ticket['status'] not in ('queued','processing'):break
            time.sleep(1)
        assert ticket['status']=='review',ticket['status']
        assert ticket['model_version']==metadata['metadata']['version']
        assert 'automatic_routing_disabled' in ticket['routing_evidence']['review_reasons']
        path='/api/tickets/'+ticket['id']+'/review'
        response=client.post(path,json={'category':'PAYMENT','reviewer':'Demo visitor','note':'Private notes should be rejected'})
        assert response.status_code==422
        response=client.post(path,json={'category':'PAYMENT','reviewer':'Demo visitor','note':''})
        response.raise_for_status();assert response.json()['status']=='reviewed'
        result=client.get('/api/tickets/'+ticket['id']).json()
        assert result['review']['reviewer']=='Demo visitor' and result['assigned_team']=='Billing'
        client.get('/api/robustness').raise_for_status()
        print(json.dumps({'status':'passed','model_version':ticket['model_version'],'flow':'HTTP -> Postgres -> Redis -> RQ process worker -> review -> persisted team','custom_request_and_size_limits':'verified'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:8000')
    main(parser.parse_args().base)
