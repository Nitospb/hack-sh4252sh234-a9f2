"""Threaded local API. Only the Next BFF is published in Docker."""
import argparse
import hmac
import json
import os
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from recommendations.engine import Feed
from recommendations import catalog
from recommendations.snapshots import Snapshots
from service.runtime import Runtime, VERSION
from service import bank
from service.context import DATA


def load_env(path=ROOT/'.env'):
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key,value=line.split('=',1)
                if key.strip().startswith('ALFA_'):os.environ.setdefault(key.strip(),value.strip().strip('"').strip("'"))


def handler(engine, runtime=None, snapshots=None):
    runtime=runtime or Runtime(engine)
    snapshots=snapshots or Snapshots(engine, os.getenv("ALFA_CATALOG_RELEASES"), embeddings=engine.embeddings_enabled)
    class Handler(BaseHTTPRequestHandler):
        def authorized(self):
            token=os.getenv('ALFA_INTERNAL_TOKEN','')
            return not token or hmac.compare_digest(self.headers.get('X-Alfa-Internal',''),token)

        def reply(self,status,value):
            body=json.dumps(value,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

        def identity(self,q):
            uid=q['company_id'];user=q.get('user_id','local')
            if not all(isinstance(v,str) and 0<len(v)<=200 for v in (uid,user)):raise ValueError('company_id/user_id must be 1..200 characters')
            c=catalog.company(self.engine,uid,q.get('source_record_id'))
            return c,user

        def do_GET(self):
            if not self.authorized():return self.reply(403,{'error':'Forbidden'})
            try:
                engine=self.engine=snapshots.current()
                url=urlparse(self.path);q={k:v[0] for k,v in parse_qs(url.query).items()}
                if url.path=='/feed':result=engine.recommend(q['company_id'],q.get('user_id','local'),int(q.get('limit',20)),q.get('source_record_id'),q.get('request_id'),scope=q.get('scope','interest'),include_review=q.get('include_review')=='true',kind=q.get('kind','all'),mode=q.get('mode','ranked'),role=q.get('role'))
                elif url.path=='/health':
                    result=catalog.health(engine);result['catalog_publication']=snapshots.status();result['agent_version']=VERSION;result['bank_documents']=len(bank.documents(runtime.assets));result['bank_retrieval']=bank.retrieval_status(runtime.semantic_index,engine.encoder_sha)
                elif url.path=='/companies':result=catalog.companies(engine,q.get('q',''),q.get('limit',25))
                elif url.path=='/company':result=catalog.company(engine,q['company_id'],q.get('source_record_id'))
                elif url.path=='/profile':result=catalog.profile_state(engine,q['company_id'],q.get('user_id','local'))
                elif url.path=='/saved':result=catalog.saved(engine,q['company_id'],q.get('user_id','local'))
                elif url.path=='/article':result=catalog.article(engine,q['article_id'])
                elif url.path=='/news':result=catalog.news(engine,q.get('q',''),q.get('kind','all'),q.get('offset',0),q.get('limit',30))
                elif url.path=='/insight':result=catalog.insight(engine,q['company_id'],q['article_id'],q.get('source_record_id'),role=q.get('role','general'))
                elif url.path in ('/context','/runs','/run','/metrics','/scenarios'):
                    c,user=self.identity(q)
                    if url.path=='/context':result={**c,**runtime.context(c,user)}
                    elif url.path=='/runs':result=runtime.list_runs(c['company_id'],user,c['source_record_id'])
                    elif url.path=='/run':result=runtime.get_run(q['run_id'],c['company_id'],user,c['source_record_id'])
                    elif url.path=='/scenarios':result=runtime.scenarios(c,user)
                    else:result=runtime.metrics(c['company_id'],user,c['source_record_id'])
                elif url.path=='/bank-sources':result={'items':bank.documents(runtime.assets),'passages':bank.search(runtime.assets,q.get('q',''),q.get('as_of') or __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()) if q.get('q') else []}
                elif url.path=='/bank-file':
                    import sqlite3
                    with sqlite3.connect(runtime.assets) as db:r=db.execute('SELECT title,sha256 FROM bank_documents WHERE id=?',(q['document_id'],)).fetchone()
                    if not r:return self.reply(404,{'error':'Document not found'})
                    path=(DATA/'reports'/r[0]).resolve()
                    if path.parent!=(DATA/'reports').resolve() or not path.is_file():return self.reply(404,{'error':'Original PDF is not mounted'})
                    content=path.read_bytes()
                    import hashlib
                    if hashlib.sha256(content).hexdigest()!=r[1]:raise ValueError('PDF изменился после индексации; обновите bank assets')
                    self.send_response(200);self.send_header('Content-Type','application/pdf');self.send_header('Content-Length',str(len(content)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(content);return
                else:return self.reply(404,{'error':'not found'})
                self.reply(200,result)
            except (ValueError,KeyError,TypeError) as e:self.reply(400,{'error':str(e)})
            except (BrokenPipeError,ConnectionResetError):pass
            except Exception:self.reply(500,{'error':'internal error'})

        def do_POST(self):
            if not self.authorized():return self.reply(403,{'error':'Forbidden'})
            try:
                engine=self.engine=snapshots.current()
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=65536:raise ValueError('body must be 1..65536 bytes')
                p=json.loads(self.rfile.read(size));c,user=self.identity(p);company=c['company_id']
                if self.path=='/events':result=engine.event(company,user,p['article_id'],p['kind'],p['event_id'])
                elif self.path=='/profile':
                    engine.profile(company,user,p.get('topic_ids',[]),role=p.get('role','general'));result={'saved':True}
                elif self.path=='/review':result=runtime.review(p['run_id'],company,user,p['rating'],p.get('note',''),c['source_record_id'])
                elif self.path in ('/analysis','/chat'):
                    a=catalog.article(engine,p['article_id'])
                    if self.path=='/chat' and not p.get('parent_run_id'):raise ValueError('Выберите завершённый разбор для диалога')
                    vector=engine.vectors.get(a['article_id'])
                    result=runtime.submit(c,a,user,p.get('role','general'),p.get('question',''),p.get('parent_run_id'),retrieval={'vector':vector.tolist(),'encoder_sha':engine.encoder_sha} if vector is not None else None)
                elif self.path=='/scenario':result=runtime.scenario(c,user,p.get('parameters'))
                elif self.path=='/context':
                    result=runtime.delete_note(c,user,p['delete_id']) if p.get('delete_id') else runtime.add_note(c,user,p.get('text',''))
                elif self.path=='/insight':
                    a=catalog.article(engine,p['article_id']);vector=engine.vectors.get(a['article_id'])
                    result=runtime.submit(c,a,user,p.get('role','general'),retrieval={'vector':vector.tolist(),'encoder_sha':engine.encoder_sha} if vector is not None else None)
                else:return self.reply(404,{'error':'not found'})
                self.reply(202 if self.path in ('/analysis','/chat','/insight') else 200,result)
            except (ValueError,KeyError,TypeError) as e:self.reply(400,{'error':str(e)})
            except RuntimeError as e:self.reply(503,{'error':str(e)})
            except (BrokenPipeError,ConnectionResetError):pass
            except Exception:self.reply(500,{'error':'internal error'})
    return Handler

if __name__=='__main__':
    load_env()
    p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8091)
    p.add_argument('--no-embeddings',action='store_true');p.add_argument('--catalog');p.add_argument('--state');args=p.parse_args()
    feed=Feed(catalog=args.catalog,state=args.state or os.getenv('ALFA_FEEDBACK'),embeddings=not args.no_embeddings)
    import fcntl
    lock=Path(os.getenv('ALFA_SERVICE_STATE') or feed.state.parent/'service.sqlite').with_suffix('.lock')
    lock.parent.mkdir(parents=True,exist_ok=True)
    handle=lock.open('a')
    try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('Another API owns this service state; not starting a duplicate')
    releases=os.getenv('ALFA_CATALOG_RELEASES')
    if releases:
        import hashlib
        from pipeline.publication import clear_owner_leases
        clear_owner_leases(releases,hashlib.sha256(str(feed.state.resolve()).encode()).hexdigest()[:16])
    service=Runtime(feed)
    print(f'API listening on http://{args.host}:{args.port}',flush=True)
    ThreadingHTTPServer((args.host,args.port),handler(feed,service)).serve_forever()
