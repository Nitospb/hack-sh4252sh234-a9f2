"""Consistent SQLite backups and guarded restore of separate mutable service state."""
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile

FILES=('feedback.sqlite','service.sqlite')


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def check(path):
    if path.is_symlink():raise ValueError('Database symlinks are not allowed')
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity failed')


def backup(state,output):
    state,output=Path(state).resolve(),Path(output).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise ValueError('Backup target already exists')
    stage=Path(tempfile.mkdtemp(prefix='.backup-',dir=output.parent))
    started=datetime.now(timezone.utc).isoformat()
    try:
        checksums={}
        for name in FILES:
            source=state/name
            if not source.is_file():raise ValueError('Missing state database: '+name)
            check(source)
            with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as db:
                with sqlite3.connect(stage/name) as target:db.backup(target)
            check(stage/name);checksums[name]=sha(stage/name)
        manifest={'schema_version':1,'started_at':started,'completed_at':datetime.now(timezone.utc).isoformat(),
            'files':checksums,'semantics':'Each SQLite is transaction-consistent; databases are captured separately within the recorded time window.',
            'excludes':['API keys','Chrome profiles','catalog/model/source datasets']}
        (stage/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        stage.rename(output);return manifest
    finally:
        if stage.exists():shutil.rmtree(stage)


def restore(source,state):
    source,state=Path(source).resolve(),Path(state).resolve()
    manifest=json.loads((source/'manifest.json').read_text())
    if manifest.get('schema_version')!=1 or set(manifest.get('files',{}))!=set(FILES):raise ValueError('Invalid backup manifest')
    for name,expected in manifest['files'].items():
        check(source/name)
        if sha(source/name)!=expected:raise ValueError('Backup checksum mismatch')
    state.mkdir(parents=True,exist_ok=True)
    with (state/'service.lock').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if any((state/name).exists() or (state/(name+'-wal')).exists() for name in FILES):
            raise ValueError('Restore requires an empty state directory; existing data will not be overwritten')
        temps=[]
        try:
            for name in FILES:
                temp=state/(name+'.restore');shutil.copyfile(source/name,temp);check(temp);temps.append((temp,state/name))
            for temp,target in temps:temp.replace(target)
        finally:
            for temp,_ in temps:temp.unlink(missing_ok=True)
    return {'restored_files':list(FILES),'source_completed_at':manifest['completed_at']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('backup','restore'))
    p.add_argument('--state',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True)
    a=p.parse_args();print(json.dumps(backup(a.state,a.bundle) if a.command=='backup' else restore(a.bundle,a.state),indent=2))
