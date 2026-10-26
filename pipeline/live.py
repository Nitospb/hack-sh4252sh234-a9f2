"""Bounded fresh-news collection, incremental staging and atomic serving publication."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import sqlite3
import subprocess
import sys
import threading
import time

from pipeline.publication import publish, prune

ROOT=Path(__file__).resolve().parents[1]


def now():return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    temp.replace(path)


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def prepare_runtime(runtime):
    runtime.mkdir(parents=True,exist_ok=True)
    marker=runtime/'live-worker.json'
    if (runtime/'history-job.json').exists() or (runtime/'collection-objectives.json').exists():
        raise ValueError('Historical collection runtime cannot be used for online collection')
    if (runtime/'news.sqlite3').exists() and not marker.exists():
        raise ValueError('Existing collector runtime requires its original live-worker marker')
    if not marker.exists():atomic_json(marker,{'schema_version':1,'purpose':'fresh_news_only','created_at':now()})
    if json.loads(marker.read_text()).get('purpose')!='fresh_news_only':raise ValueError('Invalid runtime marker')


def freeze_news(runtime):
    source=runtime/'news.sqlite3';target=runtime/'index-input.sqlite3'
    with lock(runtime/'collector.lock'):
        with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True) as db:
            with sqlite3.connect(target) as out:db.backup(out)
    # Includes metadata/date/media revisions, not just text changes.
    with sqlite3.connect(target) as db:
        h=hashlib.sha256()
        for aid,record in db.execute('SELECT id,record FROM articles ORDER BY id'):
            item=json.loads(record)
            for field in ('fetched_at','last_seen_at','first_seen_at'):item.pop(field,None)
            h.update(json.dumps([aid,item],sort_keys=True,ensure_ascii=False).encode())
        sources=[dict(zip([c[0] for c in cursor.description],row)) for cursor in [db.execute('SELECT * FROM source_state')] for row in cursor]
        count=db.execute('SELECT count(*) FROM articles').fetchone()[0]
    return target,h.hexdigest(),count,sources


class Worker:
    def __init__(self,args):
        self.args=args;self.stop=threading.Event();self.child=None;self.collecting=False
        self.status_path=args.status
        self.status=json.loads(self.status_path.read_text()) if self.status_path.exists() else {}

    def persist(self,**fields):
        self.status.update(fields);self.status['updated_at']=now();atomic_json(self.status_path,self.status)

    def request_stop(self,*_):
        self.stop.set()
        if self.collecting and self.child and self.child.poll() is None:self.child.send_signal(signal.SIGTERM)

    def command(self,argv,cwd,phase,partial=False):
        self.persist(phase=phase)
        log=self.args.runtime/(phase+'.log')
        with log.open('a') as stream:
            self.child=subprocess.Popen(argv,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT)
            try:
                while True:
                    try:code=self.child.wait(timeout=15);break
                    except subprocess.TimeoutExpired:self.persist(heartbeat_at=now())
            finally:self.child=None
        if code and not partial:raise RuntimeError(phase+' failed (see '+log.name+')')
        return code

    def cycle(self):
        a=self.args;start=time.time()
        if shutil.disk_usage(a.runtime).free<2*1024**3:raise RuntimeError('Less than 2 GiB free; collection paused')
        self.persist(phase='collecting',running=True,stopped_at=None,last_attempt=now(),last_error=None,error_type=None,pid=os.getpid(),sources_requested=a.sources)
        if not a.skip_collect:
            self.collecting=True
            try:
                code=self.command([a.collector_python,'-m','news_collector','--runtime',str(a.runtime),
                    '--config',str(a.config),'--headless','collect','--sources',*a.sources,
                    '--workers',str(a.workers),'--max-articles',str(a.max_articles),
                    '--max-links',str(a.max_links),'--defer-images'],ROOT/'parser','collecting',partial=True)
                self.persist(collector_exit=code)
            finally:self.collecting=False
        if not (a.runtime/'news.sqlite3').exists():raise RuntimeError('Collector produced no SQLite; see collecting.log')
        frozen,fingerprint,count,sources=freeze_news(a.runtime)
        # Daily eligibility refresh also runs when no new content arrives.
        signature=hashlib.sha256((fingerprint+'|stories-v2|'+now()[:10]+'|'+str(a.snapshot)).encode()).hexdigest()
        last_collection=a.runtime/'last-collection.json'
        self.persist(collected_articles=count,source_health=sources,
                     collection_results=json.loads(last_collection.read_text()) if last_collection.exists() else None)
        if signature==self.status.get('published_input') and (a.releases/'current.json').exists():
            self.persist(phase='unchanged',last_cycle_success=now(),last_cycle_seconds=round(time.time()-start,2));return
        candidate=a.runtime/'candidate';candidate.mkdir(exist_ok=True)
        a.releases.mkdir(parents=True,exist_ok=True)
        pointer=a.releases/'current.json'
        reuse=a.baseline
        if pointer.exists():
            version=json.loads(pointer.read_text())['version']
            if not re.fullmatch('[0-9a-f]{64}',version):raise ValueError('Invalid current pointer')
            reuse=a.releases/version
        self.command([a.python,'pipeline/build.py','--backend',a.backend,'--snapshot',str(a.snapshot),
                      '--output',str(candidate),'--news-live',str(frozen),'--reuse-from',str(reuse)],ROOT,'indexing')
        self.command([a.python,'pipeline/ranked_catalog.py','--catalog',str(candidate/'catalog.sqlite'),
                      '--output',str(candidate/'ranking.sqlite')],ROOT,'ranking')
        self.command([a.python,'-m','pipeline.stories','--directory',str(candidate),'--previous',str(reuse)],ROOT,'stories')
        # The first generation must also preserve every delivered baseline ID.
        if not pointer.exists():
            with sqlite3.connect(candidate/'catalog.sqlite') as db:
                db.execute('ATTACH DATABASE ? AS baseline',(str(a.baseline/'catalog.sqlite'),))
                for table,key in (('articles','article_id'),('companies','source_record_id')):
                    if db.execute(f'SELECT {key} FROM baseline.{table} EXCEPT SELECT {key} FROM main.{table} LIMIT 1').fetchone():
                        raise ValueError('Candidate drops baseline '+table+' IDs')
        self.persist(phase='publishing')
        manifest=publish(candidate,a.releases)
        removed=prune(a.releases,keep=3)
        self.persist(pruned_generations=removed)
        build_report=json.loads((candidate/'report.json').read_text())
        embeddings=json.loads((candidate/'embedding_metadata.json').read_text())
        # Do not count collected records as delivered/accepted.
        with sqlite3.connect(candidate/'catalog.sqlite') as db:
            eligible=db.execute('SELECT count(*) FROM articles WHERE eligible_delivery=1').fetchone()[0]
        self.persist(phase='published',last_publish_success=now(),last_cycle_success=now(),
                     serving_version=manifest['version'],published_input=signature,
                     catalog_articles=manifest['articles'],eligible_articles=eligible,
                     embedding_chunks_new=embeddings['new'],embedding_chunks_reused=embeddings['reused'],
                     thematic_articles_new=build_report['thematic_articles_new'],
                     thematic_articles_reused=build_report['thematic_articles_reused'],
                     last_cycle_seconds=round(time.time()-start,2))

    def run(self):
        a=self.args
        with lock(a.runtime/'worker.lock'):
            prepare_runtime(a.runtime)
            leases=a.releases.parent/'reader-leases'
            leases.mkdir(parents=True,exist_ok=True);leases.chmod(0o777)
            for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,self.request_stop)
            cycles=0
            try:
                while not self.stop.is_set():
                    try:self.cycle()
                    except Exception as error:
                        self.persist(phase='error',last_error=str(error)[:500],error_type=type(error).__name__)
                        if not a.forever:raise
                    cycles+=1
                    if not a.forever or (a.cycles and cycles>=a.cycles):break
                    self.persist(next_attempt_epoch=time.time()+a.interval)
                    self.stop.wait(a.interval)
            finally:self.persist(running=False,stopped_at=now(),pid=None)


def arguments(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--releases',type=Path,default=ROOT/'pipeline/output/releases')
    p.add_argument('--status',type=Path,default=ROOT/'pipeline/output/live-status.json')
    p.add_argument('--baseline',type=Path,default=ROOT/'pipeline/output')
    p.add_argument('--snapshot',type=Path,default=ROOT/'imports/alfa-final-dataset-2026-10-25-0900')
    p.add_argument('--config',type=Path,default=ROOT/'parser/config/sources.json')
    p.add_argument('--sources',nargs='+',required=True)
    p.add_argument('--python',default=sys.executable)
    p.add_argument('--collector-python',default=sys.executable)
    p.add_argument('--backend',choices=('mps','cpu','cuda'),default='mps')
    p.add_argument('--workers',type=int,choices=range(1,5),default=1)
    p.add_argument('--max-articles',type=int,default=3)
    p.add_argument('--max-links',type=int,default=40)
    p.add_argument('--interval',type=int,default=900)
    p.add_argument('--forever',action='store_true')
    p.add_argument('--cycles',type=int,default=0,help='Optional finite limit with --forever')
    p.add_argument('--skip-collect',action='store_true',help='Resume indexing an existing online staging database')
    a=p.parse_args(argv)
    if a.interval<300 or min(a.max_articles,a.max_links)<1 or a.cycles<0:p.error('Invalid pacing or budgets')
    for key in ('runtime','releases','status','baseline','snapshot','config'):setattr(a,key,getattr(a,key).resolve())
    if a.runtime==a.baseline or a.releases==a.baseline:p.error('Runtime/releases must differ from baseline')
    return a


if __name__=='__main__':Worker(arguments()).run()
