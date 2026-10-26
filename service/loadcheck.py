"""Bounded local HTTP timing check. No analysis, LLM, training or collectors."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import statistics
import time
from urllib.parse import urlencode,urlparse
from urllib.request import urlopen
import uuid


def check(base,requests=16,workers=4):
    if urlparse(base).hostname not in ('localhost','127.0.0.1','::1'):raise ValueError('Local test only')
    if not 1<=requests<=200 or not 1<=workers<=8:raise ValueError('Bounded requests/workers required')
    base=base.rstrip('/')+'/'
    with urlopen(base+'companies?limit=1',timeout=10) as response:company=json.load(response)['items'][0]
    scope={k:company[k] for k in ('company_id','source_record_id')};scope['user_id']='loadcheck-'+uuid.uuid4().hex
    def request(index):
        route='health' if index%2 else 'feed';start=time.monotonic()
        params='' if route=='health' else '?'+urlencode({**scope,'limit':3,'mode':'ranked','scope':'interest','kind':'news','request_id':uuid.uuid4().hex})
        try:
            with urlopen(base+route+params,timeout=30) as response:json.load(response)
            return {'route':route,'seconds':time.monotonic()-start,'ok':True}
        except Exception as error:return {'route':route,'seconds':time.monotonic()-start,'ok':False,'error_type':type(error).__name__}
    started=time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:rows=list(pool.map(request,range(requests)))
    report={'requests':requests,'workers':workers,'elapsed_seconds':time.monotonic()-started,'llm_called':False,'failures':sum(not r['ok'] for r in rows),'routes':{}}
    for name in ('health','feed'):
        times=sorted(r['seconds'] for r in rows if r['route']==name)
        if times:report['routes'][name]={'count':len(times),'p50_seconds':statistics.median(times),'p95_seconds':times[math.ceil(len(times)*.95)-1],'max_seconds':max(times)}
    report['limitations']=['Small local timing check; not a production capacity estimate.','LLM queues, remote gateway and Selenium throughput are not measured.','All writes belong to an isolated loadcheck user.']
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:9082/api/live');p.add_argument('--requests',type=int,default=16);p.add_argument('--workers',type=int,default=4);args=p.parse_args()
    print(json.dumps(check(**vars(args)),indent=2))
