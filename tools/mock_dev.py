"""Start a synthetic Python API and Next.js dev server in isolated processes."""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

from service.seed import create

ROOT = Path(__file__).resolve().parents[1]


def check_port(port):
    if not 1 <= port <= 65535:
        raise ValueError('Port must be between 1 and 65535')
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', port)) == 0:
            raise ValueError(f'Port {port} is already in use')


def wait_for(url, children, token=None, timeout=90):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        for name, child in children:
            if child.poll() is not None:
                raise RuntimeError(f'{name} exited with code {child.returncode}')
        try:
            headers = {'X-Alfa-Internal': token} if token else {}
            with urlopen(Request(url, headers=headers), timeout=3) as response:
                body = json.load(response)
            if body.get('ok') and body.get('dataset_kind') == 'synthetic' and not body.get('llm_available'):
                return
            raise RuntimeError('The API did not return the expected synthetic dataset')
        except (OSError, TimeoutError):
            time.sleep(.5)
    raise RuntimeError(f'Timed out waiting for {url}')


def stop(children):
    for _, child in reversed(children):
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for _, child in reversed(children):
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()


def main():
    parser = argparse.ArgumentParser(description='Run the frontend in dev mode with synthetic API data')
    parser.add_argument('--web-port', type=int, default=3001)
    parser.add_argument('--api-port', type=int, default=8092)
    args = parser.parse_args()
    if args.web_port == args.api_port:
        parser.error('Web and API ports must differ')
    for port in (args.web_port, args.api_port):
        check_port(port)

    next_bin = ROOT / 'frontend/node_modules/next/dist/bin/next'
    if not next_bin.is_file():
        raise SystemExit('Install frontend dependencies with npm ci')
    token = secrets.token_urlsafe(24)
    children = []
    with tempfile.TemporaryDirectory(prefix='alfa-mock-') as temporary:
        directory = Path(temporary)
        create(directory / 'seed')
        (directory / 'state').mkdir()
        (directory / 'data').mkdir()
        env = {key: value for key, value in os.environ.items() if not key.startswith('ALFA_')}
        env.update({
            'ALFA_API_KEY': '',
            'ALFA_INTERNAL_TOKEN': token,
            'ALFA_CATALOG': str(directory / 'seed/catalog.sqlite'),
            'ALFA_ASSETS': str(directory / 'seed/service-assets.sqlite'),
            'ALFA_SERVICE_STATE': str(directory / 'state/service.sqlite'),
            'ALFA_FEEDBACK': str(directory / 'state/feedback.sqlite'),
            'ALFA_BANK_SEMANTIC': str(directory / 'seed/bank-semantic.sqlite'),
            'ALFA_DATA_DIR': str(directory / 'data'),
            'ALFA_CATALOG_RELEASES': '',
            'ALFA_LIVE_STATUS': '',
        })
        try:
            print('Starting synthetic API and Next.js dev server...', flush=True)
            api = subprocess.Popen([sys.executable, '-m', 'tools.mock_api',
                                    '--directory', str(directory), '--port', str(args.api_port)],
                                   cwd=ROOT, env=env, start_new_session=True)
            children.append(('Mock API', api))
            wait_for(f'http://127.0.0.1:{args.api_port}/health', children, token)
            web_env = {**env, 'ALFA_API_URL': f'http://127.0.0.1:{args.api_port}',
                       'ALFA_API_PORT': str(args.api_port)}
            web = subprocess.Popen(['node', str(next_bin), 'dev', '--webpack', '--hostname', '127.0.0.1',
                                    '--port', str(args.web_port)],
                                   cwd=ROOT / 'frontend', env=web_env, start_new_session=True)
            children.append(('Next.js', web))
            wait_for(f'http://127.0.0.1:{args.web_port}/api/live/health', children)
            print(f'Mock frontend: http://127.0.0.1:{args.web_port}/feed', flush=True)
            print('Only synthetic data is loaded. Ctrl+C stops both servers and removes mock state.', flush=True)
            while all(child.poll() is None for _, child in children):
                time.sleep(.5)
            raise RuntimeError('A child server stopped unexpectedly')
        except KeyboardInterrupt:
            pass
        finally:
            stop(children)


if __name__ == '__main__':
    main()
