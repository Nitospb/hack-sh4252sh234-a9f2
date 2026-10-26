"""Publish immutable serving generations; never mutate the active snapshot in place."""
import argparse
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone

REQUIRED = ('catalog.sqlite', 'report.json')
OPTIONAL = ('ranking.sqlite', 'ranking_report.json', 'article_chunk_embeddings.npy',
            'article_chunks.jsonl', 'embedding_metadata.json', 'object_family_embeddings.npy',
            'object_family_embedding_metadata.json', 'corpus_manifest.json', 'stories.sqlite', 'stories_report.json')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate(directory, *, synthetic=False):
    directory = Path(directory)
    for name in REQUIRED:
        if not (directory/name).is_file():
            raise ValueError('Missing serving file: '+name)
    report = json.loads((directory/'report.json').read_text())
    if report.get('synthetic') and not synthetic:
        raise ValueError('Synthetic publication requires --allow-synthetic')
    with sqlite3.connect((directory/'catalog.sqlite').resolve().as_uri()+'?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Catalog integrity failed')
        articles = dict(db.execute('SELECT article_id,content_hash FROM articles'))
        if not articles or not db.execute('SELECT 1 FROM companies LIMIT 1').fetchone():
            raise ValueError('Empty catalog')
    ranking = directory/'ranking.sqlite'
    if ranking.exists():
        with sqlite3.connect(ranking.resolve().as_uri()+'?mode=ro', uri=True) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Ranking integrity failed')
            metadata = json.loads(db.execute("SELECT value FROM metadata WHERE key='report'").fetchone()[0])
        if metadata['catalog_sha256'] != digest(directory/'catalog.sqlite'):
            raise ValueError('Ranking belongs to a different catalog')
    if (directory/'stories.sqlite').exists():
        with sqlite3.connect((directory/'stories.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Stories integrity failed')
            story_report=json.loads(db.execute("SELECT value FROM metadata WHERE key='report'").fetchone()[0])
            if story_report['catalog_sha256']!=digest(directory/'catalog.sqlite'):raise ValueError('Stories belong to another catalog')
            source_rows=dict(db.execute('SELECT article_id,content_hash FROM members'))
            if source_rows!=articles:raise ValueError('Story/article version mismatch')
            if db.execute('SELECT 1 FROM members m LEFT JOIN stories s USING(story_id) WHERE s.story_id IS NULL LIMIT 1').fetchone():raise ValueError('Unknown story ID')
    vector_names = OPTIONAL[2:7]
    present = [name for name in vector_names if (directory/name).exists()]
    if present and len(present) != len(vector_names):
        raise ValueError('Incomplete embedding bundle')
    if not present and not report.get('synthetic'):
        raise ValueError('Collected catalog requires embeddings')
    if present:
        import numpy as np
        vectors = np.load(directory/'article_chunk_embeddings.npy', mmap_mode='r', allow_pickle=False)
        seen = set(); count = 0
        with (directory/'article_chunks.jsonl').open() as stream:
            for count, line in enumerate(stream, 1):
                chunk = json.loads(line); aid = chunk['article_id']
                if articles.get(aid) != chunk['content_hash']:
                    raise ValueError('Chunk/catalog content mismatch')
                seen.add(aid)
        if vectors.shape != (count, 384) or seen != set(articles) or not np.isfinite(vectors).all():
            raise ValueError('Invalid article vectors')
        encoder = json.loads((directory/'embedding_metadata.json').read_text())['fingerprint']['model_sha256']
        if encoder != json.loads((directory/'object_family_embedding_metadata.json').read_text())['model_sha256']:
            raise ValueError('Mixed encoders')
    return {'articles':len(articles), 'synthetic':bool(report.get('synthetic'))}


def publish(candidate, root, *, allow_synthetic=False):
    candidate, root = Path(candidate).resolve(), Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root/'publication.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Copy first: validation must describe exactly the frozen bytes being published.
        stage = Path(tempfile.mkdtemp(prefix='.staging-', dir=root))
        try:
            for name in REQUIRED+OPTIONAL:
                src = candidate/name
                if src.exists():
                    if src.is_symlink():raise ValueError('Candidate files must not be symlinks')
                    shutil.copyfile(src, stage/name)
            counts = validate(stage, synthetic=allow_synthetic)
            if (root/'current.json').exists():
                previous=json.loads((root/'current.json').read_text())['version']
                if not re.fullmatch('[0-9a-f]{64}', previous):raise ValueError('Invalid previous version')
                with sqlite3.connect((stage/'catalog.sqlite').as_uri()+'?mode=ro', uri=True) as db:
                    old=(root/previous/'catalog.sqlite').resolve()
                    if old.parent.parent != root:raise ValueError('Invalid previous catalog')
                    db.execute('ATTACH DATABASE ? AS previous', (old.as_uri()+'?mode=ro',))
                    for table,key in (('articles','article_id'),('companies','source_record_id')):
                        missing=db.execute(f'SELECT {key} FROM previous.{table} EXCEPT SELECT {key} FROM main.{table} LIMIT 1').fetchone()
                        if missing:raise ValueError('Publication would drop existing '+table+' IDs')
            files = {p.name:digest(p) for p in stage.iterdir() if p.is_file()}
            version = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
            manifest = {'version':version, 'created_at':datetime.now(timezone.utc).isoformat(),
                        'files':files, **counts}
            (stage/'manifest.json').write_text(json.dumps(manifest, indent=2))
            # Ensure data is durable before publishing its pointer.
            for path in stage.iterdir():
                with path.open('rb') as stream:os.fsync(stream.fileno())
            descriptor=os.open(stage, os.O_RDONLY)
            try:os.fsync(descriptor)
            finally:os.close(descriptor)
            target = root/version
            if target.exists():
                if json.loads((target/'manifest.json').read_text())['files'] != files or any(digest(target/name) != value for name,value in files.items()):
                    raise ValueError('Version collision')
                shutil.rmtree(stage)
            else:stage.rename(target)
            temp = root/'current.tmp'
            temp.write_text(json.dumps({'version':version}))
            with temp.open('rb') as stream:os.fsync(stream.fileno())
            temp.replace(root/'current.json')
            descriptor=os.open(root, os.O_RDONLY)
            try:os.fsync(descriptor)
            finally:os.close(descriptor)
            return manifest
        finally:
            if stage.exists():shutil.rmtree(stage)


class FileLease:
    """Visible reader lease across macOS/Linux mounts (flock is not cross-VM)."""
    def __init__(self, root, version, owner='reader'):
        if not re.fullmatch('[0-9a-f]{64}',version):raise ValueError('Invalid generation')
        self.path=None
        registry=Path(root).parent/'reader-leases'/version
        registry.mkdir(parents=True,exist_ok=True)
        # Cross-user host/container use is limited to non-secret lease metadata.
        try:registry.chmod(0o777)
        except PermissionError:pass
        path=registry/(owner+'-'+uuid.uuid4().hex+'.lease')
        with path.open('x') as stream:stream.write(str(os.getpid()))
        self.path=path
        if (registry/'.deleting').exists():
            self.close();raise RuntimeError('Generation is being retired; retry next request')

    def close(self):
        if self.path is not None:
            self.path.unlink(missing_ok=True);self.path=None

    def __del__(self):self.close()


def clear_owner_leases(root, owner):
    """Only call after acquiring the API's exclusive service-state lock."""
    registry=Path(root).parent/'reader-leases'
    if registry.exists():
        for path in registry.glob('*/'+owner+'-*.lease'):path.unlink(missing_ok=True)


def prune(root, keep=3):
    """Retire only derived generations with no registered readers, across VM mounts."""
    if keep < 2:raise ValueError('Retain at least two generations')
    root=Path(root).resolve();removed=[]
    with (root/'publication.lock').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        current=json.loads((root/'current.json').read_text())['version']
        directories=sorted((p for p in root.iterdir() if p.is_dir() and not p.is_symlink()
                            and re.fullmatch('[0-9a-f]{64}',p.name)),key=lambda p:p.stat().st_mtime_ns,reverse=True)
        protected={p.name for p in directories[:keep]}|{current}
        for directory in directories:
            if directory.name in protected:continue
            registry=root.parent/'reader-leases'/directory.name
            registry.mkdir(parents=True,exist_ok=True)
            barrier=registry/'.deleting'
            try:
                with barrier.open('x') as stream:stream.write('retiring')
            except FileExistsError:continue
            try:
                if any(registry.glob('*.lease')):continue
                manifest=json.loads((directory/'manifest.json').read_text())
                if manifest.get('version')!=directory.name:continue
                if not all(name in manifest.get('files',{}) for name in REQUIRED):continue
                shutil.rmtree(directory);removed.append(directory.name)
            except FileNotFoundError:continue
            finally:barrier.unlink(missing_ok=True)
    return removed


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--allow-synthetic', action='store_true')
    a=p.parse_args();print(json.dumps(publish(a.candidate,a.root,allow_synthetic=a.allow_synthetic),indent=2))
