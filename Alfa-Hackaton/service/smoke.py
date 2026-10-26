"""Exercise the public BFF/API without training, collectors or paid LLM calls."""
import argparse
import json
import time
import uuid
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from urllib.error import HTTPError


def check(base):
    base=base.rstrip('/')+'/'
    def request(path,params=None,body=None):
        url=base+path+('?' + urlencode(params) if params else '')
        req=Request(url,data=json.dumps(body).encode() if body is not None else None,
                    headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=30) as f:return json.load(f)
    health=request('health');assert health['ok']
    assert health['analysis_availability']['available']==health['llm_available']
    assert not {'tokens','calls','usage','day'} & health['analysis_availability'].keys()
    c=request('companies',{'limit':1})['items'][0]
    scope={k:c[k] for k in ('company_id','source_record_id')};scope['user_id']='smoke-'+uuid.uuid4().hex
    profile=request('profile',scope);request('profile',body={**scope,'role':'treasurer','topic_ids':profile['topic_ids']})
    assert request('profile',scope)['role']=='treasurer'
    request_id=uuid.uuid4().hex
    feed=request('feed',{**scope,'role':'treasurer','mode':'ranked','scope':'interest','limit':3,'request_id':request_id})
    assert feed==request('feed',{**scope,'role':'treasurer','mode':'ranked','scope':'interest','limit':3,'request_id':request_id})
    article_count=len(feed['items'])
    if feed['items']:
        a=feed['items'][0];body=request('article',{'article_id':a['article_id']});assert body['text']
        request('events',body={**scope,'article_id':a['article_id'],'kind':'save','event_id':uuid.uuid4().hex})
        assert a['article_id'] in [x['article_id'] for x in request('saved',scope)['items']]
        assert not request('saved',{**scope,'user_id':scope['user_id']+'-other'})['items']
    context=request('context',scope);assert context['facts']
    note=request('context',body={**scope,'text':'Техническая проверка сохранения контекста; не подтверждённый факт'})
    assert context['context_version']!=request('context',scope)['context_version']
    request('context',body={**scope,'delete_id':note['id']})
    assert context['context_version']==request('context',scope)['context_version']
    bank=request('bank-sources',{'q':'ключевая ставка'})
    if bank['items']:
        with urlopen(base+'bank-file?'+urlencode({'document_id':bank['items'][0]['id']}),timeout=30) as f:
            assert f.headers['Content-Type']=='application/pdf';assert f.read(5)==b'%PDF-'
    scenario=request('scenario',body={**scope,'parameters':{'kind':'loan','currency':'RUB','principal':'1000000','days':'365','basis':365,'rate_type':'floating','benchmark_base':'14','benchmark_scenario':'12','spread':'2','acknowledge_assumptions':True}})
    assert scenario['delta']=='-20000.00'
    assert request('scenarios',scope)['items'][0]['id']==scenario['id']
    assert not request('scenarios',{**scope,'user_id':scope['user_id']+'-other'})['items']
    assert request('metrics',scope)['evaluation']['status'] in ('not_measured','partially_measured','invalid_report')
    assert request('metrics',scope)['runs']==0
    return {'ok':True,'dataset_kind':health.get('dataset_kind'),'news':health['counts']['news'],
      'company':c['company_id'],'feed_items':article_count,'bank_documents':len(bank['items']),
      'llm_called':False,'verified':['health','analysis_availability','companies','role','feed_idempotency','user_isolation','context_notes','bank_search','metrics','scenario_calculation','scenario_history','scenario_isolation']+(['article','save'] if article_count else [])+(['pdf'] if bank['items'] else []),'skipped':[] if bank['items'] else ['pdf:no_bank_documents']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:3000/api/live');a=p.parse_args()
    print(json.dumps(check(a.base),ensure_ascii=False,indent=2))
