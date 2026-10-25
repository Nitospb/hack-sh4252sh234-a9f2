"""Run the connected local API and web app; Ctrl+C closes both owned children."""
import argparse
import json
import os
from pathlib import Path
import signal
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--web-port',type=int,default=3000)
    parser.add_argument('--api-port',type=int,default=8091)
    args = parser.parse_args()
    for port in (args.api_port,args.web_port):
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',port))==0:
                raise SystemExit(f'Port {port} is already in use; choose another --api-port/--web-port')
    catalog = ROOT / 'pipeline/output/catalog.sqlite'
    if not catalog.exists():
        raise SystemExit('First build the catalog: news_matching/.venv-mps/bin/python pipeline/build.py')
    python = next((path for path in [ROOT/'news_matching/.venv-mps/bin/python',ROOT/'news_matching/.venv/bin/python'] if path.exists()),None)
    if python is None:
        raise SystemExit('Install dependencies first: python3 tools/bootstrap.py (from repository root)')
    logs = ROOT / 'pipeline/output/logs';logs.mkdir(parents=True,exist_ok=True)
    children=[];handles=[]
    def stop(*_): raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,stop)
    try:
        api_log=(logs/'api.log').open('a');handles.append(api_log)
        command=[str(python),'recommendations/server.py','--port',str(args.api_port),'--catalog',str(catalog),'--state',str(ROOT/'pipeline/output/feedback.sqlite')]
        apple_silicon = sys.platform=='darwin' and subprocess.check_output(['sysctl','-n','hw.optional.arm64']).strip()==b'1'
        if apple_silicon:
            command=['/usr/bin/arch','-arm64',*command]
        api=subprocess.Popen(command,cwd=ROOT,stdout=api_log,stderr=subprocess.STDOUT)
        children.append(api)
        for _ in range(60):
            if api.poll() is not None: raise RuntimeError('API stopped; inspect pipeline/output/logs/api.log')
            try:
                with urlopen(f'http://127.0.0.1:{args.api_port}/health',timeout=1) as response:
                    if json.load(response).get('ok'):break
            except OSError: time.sleep(.5)
        else: raise RuntimeError('API did not become ready')
        web_log=(logs/'web.log').open('a');handles.append(web_log)
        env={**os.environ,'ALFA_API_PORT':str(args.api_port)}
        web_command=[shutil.which('node'),str(ROOT/'frontend/node_modules/next/dist/bin/next'),'dev','--hostname','127.0.0.1','--port',str(args.web_port)]
        if apple_silicon:web_command=['/usr/bin/arch','-arm64',*web_command]
        web=subprocess.Popen(web_command,cwd=ROOT/'frontend',stdout=web_log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        children.append(web)
        print(f'Web: http://127.0.0.1:{args.web_port}/feed\nAPI: http://127.0.0.1:{args.api_port}/health',flush=True)
        while all(p.poll() is None for p in children): time.sleep(1)
    except KeyboardInterrupt: pass
    finally:
        for p in reversed(children):
            if p.poll() is None:
                if p is children[-1] and len(children)>1: os.killpg(p.pid,signal.SIGTERM)
                else:p.terminate()
        for p in children:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill()
        for h in handles:h.close()

if __name__=='__main__':main()
