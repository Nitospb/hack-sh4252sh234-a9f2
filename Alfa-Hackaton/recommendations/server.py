"""Local HTTP adapter. Bind only to loopback; put authentication in front for deployment."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from engine import Feed
import catalog


def handler(engine):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, value):
            body = json.dumps(value,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            try:
                url = urlparse(self.path)
                q = {k:v[0] for k,v in parse_qs(url.query).items()}
                if url.path == '/feed':
                    result = engine.recommend(q['company_id'],q.get('user_id','local'),int(q.get('limit',20)),q.get('source_record_id'),q.get('request_id'),
                        scope=q.get('scope','interest'),include_review=q.get('include_review')=='true',kind=q.get('kind','all'),mode=q.get('mode','ranked'),role=q.get('role'))
                elif url.path == '/health': result = catalog.health(engine)
                elif url.path == '/companies': result = catalog.companies(engine,q.get('q',''),q.get('limit',25))
                elif url.path == '/company': result = catalog.company(engine,q['company_id'],q.get('source_record_id'))
                elif url.path == '/profile': result = catalog.profile_state(engine,q['company_id'],q.get('user_id','local'))
                elif url.path == '/saved': result = catalog.saved(engine,q['company_id'],q.get('user_id','local'))
                elif url.path == '/article': result = catalog.article(engine,q['article_id'])
                elif url.path == '/news': result = catalog.news(engine,q.get('q',''),q.get('kind','all'),q.get('offset',0),q.get('limit',30))
                elif url.path == '/insight': result = catalog.insight(engine,q['company_id'],q['article_id'],q.get('source_record_id'),role=q.get('role','general'))
                else: return self.reply(404,{'error':'not found'})
                self.reply(200,result)
            except (ValueError,KeyError,TypeError) as e:
                self.reply(400,{'error':str(e)})
            except Exception:
                self.reply(500,{'error':'internal error'})

        def do_POST(self):
            try:
                size = int(self.headers.get('Content-Length',0))
                if not 0<size<=65536:
                    raise ValueError('body must be 1..65536 bytes')
                p = json.loads(self.rfile.read(size))
                company,user = p['company_id'],p['user_id']
                if not all(isinstance(v,str) and 0<len(v)<=200 for v in (company,user)):
                    raise ValueError('company_id and user_id must be nonempty strings')
                if self.path == '/events':
                    result = engine.event(company,user,p['article_id'],p['kind'],p['event_id'])
                elif self.path == '/profile':
                    engine.profile(company,user,p.get('topic_ids',[]),role=p.get('role','general'))
                    result = {'saved':True}
                elif self.path == '/insight':
                    result = catalog.insight(engine,company,p['article_id'],p.get('source_record_id'),generate=True,role=p.get('role','general'))
                else:
                    return self.reply(404,{'error':'not found'})
                self.reply(200,result)
            except (ValueError,KeyError,TypeError) as e:
                self.reply(400,{'error':str(e)})
            except RuntimeError as e:
                self.reply(503,{'error':str(e)})
            except Exception:
                self.reply(500,{'error':'internal error'})
    return Handler

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--port',type=int,default=8091)
    p.add_argument('--no-embeddings',action='store_true')
    p.add_argument('--catalog')
    p.add_argument('--state')
    args = p.parse_args()
    print(f'API listening on http://127.0.0.1:{args.port}',flush=True)
    HTTPServer(('127.0.0.1',args.port),handler(Feed(catalog=args.catalog,state=args.state,embeddings=not args.no_embeddings))).serve_forever()
