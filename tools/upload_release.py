"""Upload the verified multipart snapshot to the project's GitHub release."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import subprocess
import time

def main():
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    manifest=json.loads((args.directory/'release-manifest.json').read_text())
    files=[args.directory/p['file'] for p in manifest['parts']]+[args.directory/'release-manifest.json']
    def upload(path):
        for attempt in range(3):
            result=subprocess.run(['gh','release','upload',manifest['tag'],str(path),'--repo',manifest['repository'],'--clobber'],capture_output=True,text=True)
            if result.returncode==0:return path.name
            if attempt<2:time.sleep(2*(attempt+1))
        raise RuntimeError(path.name+': '+result.stderr[-400:])
    with ThreadPoolExecutor(max_workers=max(1,min(args.workers,6))) as pool:
        jobs=[pool.submit(upload,path) for path in files]
        for i,job in enumerate(as_completed(jobs),1):print(f'Uploaded {i}/{len(files)}: {job.result()}',flush=True)

if __name__=='__main__':main()
