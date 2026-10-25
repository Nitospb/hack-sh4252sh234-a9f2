"""Download and safely restore all data/models attached to the private GitHub release."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
REPO='Nitospb/hack-sh4252sh234-a9f2'
TAG='full-snapshot-v1'

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()

class Joined(io.RawIOBase):
    def __init__(self,paths):self.paths=iter(paths);self.stream=None
    def readable(self):return True
    def read(self,size=-1):
        if size<0:raise ValueError('Streaming reads require a bounded size')
        blocks=[];remaining=size
        while remaining:
            if self.stream is None:
                try:self.stream=next(self.paths).open('rb')
                except StopIteration:break
            block=self.stream.read(remaining)
            if block:blocks.append(block);remaining-=len(block)
            else:self.stream.close();self.stream=None
        return b''.join(blocks)
    def close(self):
        if self.stream:self.stream.close()
        super().close()

def restore(folder,target,overwrite=False,verify_only=False):
    folder=folder.resolve();target=target.resolve()
    manifest=json.loads((folder/'release-manifest.json').read_text())
    parts=[]
    for part in manifest['parts']:
        if Path(part['file']).name!=part['file']:raise ValueError('Unsafe archive part name')
        path=folder/part['file']
        if path.stat().st_size!=part['bytes'] or digest(path)!=part['sha256']:raise ValueError('Part integrity failed: '+part['file'])
        parts.append(path)
    expected={f['path']:f for f in manifest['files']};seen=set();restored=0
    with Joined(parts) as stream,tarfile.open(fileobj=stream,mode='r|gz') as tar:
        for entry in tar:
            if not entry.isfile() or entry.name not in expected:raise ValueError('Unexpected archive member: '+entry.name)
            path=(target/entry.name).resolve()
            if not path.is_relative_to(target):raise ValueError('Unsafe archive path')
            if entry.name in seen:raise ValueError('Duplicate archive member')
            seen.add(entry.name);record=expected[entry.name]
            if entry.size!=record['bytes']:raise ValueError('Unexpected file size: '+entry.name)
            keep_existing=path.exists() and digest(path)==record['sha256']
            if path.exists() and not keep_existing and not overwrite and not verify_only:raise ValueError('Existing file differs; use --overwrite explicitly: '+entry.name)
            output=None;temporary=path.with_name(path.name+'.restore-tmp')
            if not verify_only and not keep_existing:
                path.parent.mkdir(parents=True,exist_ok=True);output=temporary.open('wb')
            h=hashlib.sha256()
            with tar.extractfile(entry) as source:
                while True:
                    block=source.read(4*1024*1024)
                    if not block:break
                    h.update(block)
                    if output:output.write(block)
            if output:output.close()
            if h.hexdigest()!=record['sha256']:
                if temporary.exists():temporary.unlink()
                raise ValueError('File integrity failed: '+entry.name)
            if output:temporary.replace(path)
            restored+=1
            if restored%1000==0:print('Verified',restored,'/',len(expected),flush=True)
    if seen!=set(expected):raise ValueError('Archive is incomplete')
    print('Verified' if verify_only else 'Restored',restored,'files',flush=True)
    return restored

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,default=ROOT/'.release-downloads');parser.add_argument('--target',type=Path,default=ROOT);parser.add_argument('--no-download',action='store_true');parser.add_argument('--verify-only',action='store_true');parser.add_argument('--overwrite',action='store_true');args=parser.parse_args()
    args.directory.mkdir(parents=True,exist_ok=True)
    if not args.no_download:
        subprocess.run(['gh','release','download',TAG,'--repo',REPO,'--dir',str(args.directory),'--pattern','project-data.tar.gz.part*','--pattern','release-manifest.json','--skip-existing'],check=True)
    restore(args.directory,args.target,args.overwrite,args.verify_only)

if __name__=='__main__':main()
