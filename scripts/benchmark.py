"""Bounded-concurrency HTTP→queue→worker→database benchmark. No fixture metrics."""
import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path
import httpx
import numpy as np
from ml.common import save, environment

TEXTS=['I would like to cancel my order.','Please send me a copy of my invoice.','How can I change my account password?',
       'I need a refund for the item I returned.','Where can I track my delivery?',
       'I was charged twice for the same purchase.','Something unusual happened and I need some help.',
       'Please update the shipping address for my order.']


async def run(base,count,concurrency):
    semaphore=asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(base_url=base,timeout=15) as client:
        assert (await client.get('/api/health/ready')).status_code==200
        async def one(i):
            async with semaphore:
                start=time.perf_counter()
                response=await client.post('/api/tickets',json={'text':TEXTS[i%len(TEXTS)]},headers={'Idempotency-Key':str(uuid.uuid4())})
                response.raise_for_status()
                ticket=response.json()
                while ticket['status'] in ('queued','processing'):
                    if time.perf_counter()-start>180:
                        raise TimeoutError(ticket['id'])
                    await asyncio.sleep(.05)
                    result=await client.get('/api/tickets/'+ticket['id'])
                    result.raise_for_status()
                    ticket=result.json()
                return {'id':ticket['id'],'status':ticket['status'],'end_to_end_ms':(time.perf_counter()-start)*1000,
                        'queue_wait_ms':ticket['queue_wait_ms'],'inference_ms':ticket['inference_ms']}
        start=time.perf_counter()
        rows=await asyncio.gather(*(one(i) for i in range(count)))
        elapsed=time.perf_counter()-start
    summary={}
    for field in ('end_to_end_ms','queue_wait_ms','inference_ms'):
        values=[r[field] for r in rows if r[field] is not None]
        summary[field]={'median':float(np.median(values)),'p95':float(np.percentile(values,95))}
    result={'command':f'python -m scripts.benchmark --count {count} --concurrency {concurrency}',
            'count':count,'concurrency':concurrency,'poll_interval_seconds':.05,'workers':1,
            'worker_mode':'persistent supervised Windows SimpleWorker; model preloaded once',
            'workload':'8 synthetic demo texts repeated; not held-out evaluation data',
            'elapsed_seconds':elapsed,'throughput_per_second':count/elapsed,
            'failed':sum(r['status']=='failed' for r in rows),'summary':summary,'rows':rows,'environment':environment()}
    save('artifacts/benchmark.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','environment')},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',default='http://127.0.0.1:8000')
    parser.add_argument('--count',type=int,default=40)
    parser.add_argument('--concurrency',type=int,default=4)
    args=parser.parse_args()
    asyncio.run(run(args.base,args.count,args.concurrency))
