"""Create a complete portable data/model snapshot split into release-size parts.

Live SQLite files are copied through SQLite backup, not by copying a possibly
incomplete WAL database. No credentials, browser sessions or installed software.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import gzip
import io
import json
import os
from pathlib import Path
import sqlite3
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
REPO='Nitospb/hack-sh4252sh234-a9f2'
TAG='full-snapshot-v1'
ASSET_ROOTS=['data','imports','taxonomy/output','news_matching/input',
    'news_matching/output','news_matching/models',
    'parser/runtime','pipeline/output']
SKIP_DIRS={'.git','.codex','.agents','node_modules','.next','.venv','.venv-mps','__pycache__',
    'vendor','profiles','diagnostics','logs','.pytest_cache'}

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()

def allowed(path):
    name=path.name.lower()
    return (not path.is_symlink() and not any(p in SKIP_DIRS for p in path.relative_to(ROOT).parts)
        and not name.startswith('.env') and name not in {'.ds_store','singletonlock','singletoncookie','singletonport'}
        and not name.endswith(('-wal','-shm','.pyc','.log','.tmp','.lockfile'))
        and not any(word in name for word in ('credential','cookies','session.key','private.key')))

def assets():
    found={}
    for name in ASSET_ROOTS:
        root=ROOT/name
        if not root.exists():continue
        for folder,dirs,files in os.walk(root,followlinks=False):
            dirs[:]=[d for d in dirs if d not in SKIP_DIRS and not (Path(folder)/d).is_symlink()]
            for name in files:
                path=Path(folder)/name
                if allowed(path):found[path.relative_to(ROOT).as_posix()]=path
    for path in (ROOT/'recommendations').glob('*.sqlite'):
        if allowed(path):found[path.relative_to(ROOT).as_posix()]=path
    return sorted(found.items())

class Parts(io.RawIOBase):
    def __init__(self,folder,maximum):
        self.folder=folder;self.maximum=maximum;self.stream=None;self.size=0;self.total=0;self.entries=[];self.hasher=None;self.name=None
    def writable(self):return True
    def tell(self):return self.total
    def finish_part(self):
        if self.stream:
            self.stream.close();self.entries.append({'file':self.name,'bytes':self.size,'sha256':self.hasher.hexdigest()});self.stream=None
    def write(self,data):
        value=memoryview(data);length=len(value)
        while value:
            if self.stream is None:
                self.name=f'project-data.tar.gz.part{len(self.entries)+1:04d}'
                self.stream=(self.folder/self.name).open('wb');self.size=0;self.hasher=hashlib.sha256()
            count=min(len(value),self.maximum-self.size);block=value[:count]
            self.stream.write(block);self.hasher.update(block);self.size+=count;self.total+=count;value=value[count:]
            if self.size==self.maximum:self.finish_part()
        return length
    def flush(self):
        if self.stream:self.stream.flush()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--part-mib',type=int,default=64);args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if list(out.glob('project-data.tar.gz.part*')):raise SystemExit('Output directory already contains an archive; use a new directory.')
    files=assets();manifest={'schema_version':1,'repository':REPO,'tag':TAG,'created_at':datetime.now(timezone.utc).isoformat(),
        'archive_format':'concatenated gzip tar parts','files':[],'parts':[],
        'excluded':['installed dependencies','build and browser caches','credentials and .env','personal browser profiles','WAL/SHM sidecars (SQLite backup includes committed records)','debug logs'],
        'snapshot_note':'Each SQLite is a consistent read-only backup; different DBs do not share one global transaction.'}
    print('Packaging',len(files),'asset files',sum(p.stat().st_size for _,p in files),'source bytes',flush=True)
    writer=Parts(out,args.part_mib*1024*1024)
    with tempfile.TemporaryDirectory(prefix='alfa-sqlite-snapshot-') as temporary:
        with gzip.GzipFile(fileobj=writer,mode='wb',compresslevel=3,mtime=0) as compressed,tarfile.open(mode='w|',fileobj=compressed) as tar:
            for i,(relative,path) in enumerate(files):
                source=path;method='file'
                with path.open('rb') as f:is_sqlite=f.read(16)==b'SQLite format 3\0'
                if is_sqlite:
                    source=Path(temporary)/'snapshot.sqlite'
                    if source.exists():source.unlink()
                    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=60) as live,sqlite3.connect(source) as copy:
                        live.backup(copy,pages=8192)
                    method='sqlite_backup'
                size=source.stat().st_size;sha=digest(source)
                info=tar.gettarinfo(str(source),arcname=relative);info.uid=info.gid=0;info.uname=info.gname='';info.mode=0o644
                with source.open('rb') as f:tar.addfile(info,f)
                manifest['files'].append({'path':relative,'bytes':size,'sha256':sha,'snapshot_method':method})
                if (i+1)%500==0:print('Archived',i+1,'/',len(files),'compressed MiB',round(writer.total/1024**2,1),flush=True)
    writer.finish_part();manifest['parts']=writer.entries;manifest['total_files']=len(files);manifest['total_uncompressed_bytes']=sum(f['bytes'] for f in manifest['files']);manifest['total_compressed_bytes']=writer.total
    (out/'release-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    summary={k:v for k,v in manifest.items() if k!='files'}
    (ROOT/'tools/release-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({k:manifest[k] for k in ['total_files','total_uncompressed_bytes','total_compressed_bytes']},indent=2),flush=True)

if __name__=='__main__':main()
