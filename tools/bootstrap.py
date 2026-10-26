"""Install pinned dependencies after restoring the full project data release."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import venv

ROOT=Path(__file__).resolve().parents[1]

def run(command,cwd=ROOT):
    print('+ '+' '.join(map(str,command)),flush=True)
    subprocess.run(list(map(str,command)),cwd=cwd,check=True)

def environment(path,requirements):
    if not path.exists():venv.EnvBuilder(with_pip=True).create(path)
    python=path/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    run([python,'-m','pip','install','-r',requirements])
    return python

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--skip-parser',action='store_true');parser.add_argument('--skip-web',action='store_true');args=parser.parse_args()
    if not (3,11)<=sys.version_info[:2]<=(3,12):raise SystemExit('Use Python 3.11 or 3.12 for the pinned ML wheels.')
    project=ROOT
    python=environment(project/'news_matching/.venv',project/'news_matching/requirements.lock')
    run([python,'-m','pip','install','-r',project/'insight_generation/requirements.txt'])
    if not args.skip_parser:environment(project/'parser/.venv',project/'parser/requirements.lock')
    if not args.skip_web:
        npm=shutil.which('npm')
        if not npm:raise SystemExit('Install Node.js 20.9+ and npm first.')
        run([npm,'ci'],cwd=project/'frontend')
    print('Ready: python3 run_local.py')

if __name__=='__main__':main()
