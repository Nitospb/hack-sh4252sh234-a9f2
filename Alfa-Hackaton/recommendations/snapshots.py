"""Request-pinned catalog generations, retaining the last healthy version on failure."""
import hashlib
import json
import re
import threading
import os
from datetime import datetime, timezone
from pathlib import Path
from recommendations.engine import Feed
from pipeline.publication import digest, REQUIRED, FileLease


class Snapshots:
    def __init__(self, initial, root=None, embeddings=True):
        self.active = initial
        self.root = Path(root).resolve() if root else None
        self.embeddings = embeddings
        self.lock = threading.Lock()
        self.version = None
        self.error = None
        self.failed_pointer = None

    def current(self):
        if self.root is None or not (self.root/'current.json').exists():return self.active
        with self.lock:
            lease=None
            try:
                raw = (self.root/'current.json').read_text()
                version = json.loads(raw)['version']
                if version == self.version or raw == self.failed_pointer:return self.active
                if not isinstance(version,str) or not re.fullmatch('[0-9a-f]{64}',version):
                    raise ValueError('Invalid catalog version')
                directory = self.root/version
                if directory.resolve().parent != self.root:raise ValueError('Invalid catalog directory')
                owner=hashlib.sha256(str(self.active.state.resolve()).encode()).hexdigest()[:16]
                lease=FileLease(self.root,version,owner)
                manifest = json.loads((directory/'manifest.json').read_text())
                if manifest['version'] != version:raise ValueError('Manifest version mismatch')
                files=manifest['files']
                if hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest() != version:
                    raise ValueError('Manifest content address mismatch')
                if not all(name in files for name in REQUIRED):raise ValueError('Incomplete manifest')
                for name, expected in files.items():
                    if Path(name).name != name:raise ValueError('Invalid manifest file')
                    if (directory/name).is_symlink() or digest(directory/name) != expected:
                        raise ValueError('Published file checksum mismatch')
                candidate = Feed(directory/'catalog.sqlite', self.active.state, embeddings=self.embeddings)
                candidate.assets = self.active.assets
                candidate._generation_lease = lease
                # Existing in-flight handlers keep their original Feed reference.
                self.active, self.version, self.error = candidate, version, None
                self.failed_pointer = None
            except Exception as error:
                if lease is not None:lease.close()
                self.error = type(error).__name__
                # Avoid repeatedly hashing a broken generation on every request.
                try:self.failed_pointer=(self.root/'current.json').read_text()
                except OSError:pass
            return self.active

    def status(self):
        result= {'enabled':self.root is not None,'serving_version':self.version,
                'reload_error':self.error,'policy':'retain_last_healthy_generation'}
        path=os.getenv('ALFA_LIVE_STATUS')
        status=Path(path) if path else self.root.parent/'live-status.json' if self.root else None
        if status and status.is_file():
            try:
                raw=json.loads(status.read_text())
                result['collection']={key:raw.get(key) for key in (
                    'phase','running','last_attempt','last_publish_success','last_cycle_success',
                    'updated_at','next_attempt_epoch','collected_articles','catalog_articles',
                    'eligible_articles','embedding_chunks_new','embedding_chunks_reused',
                    'thematic_articles_new','thematic_articles_reused','source_health',
                    'collection_results','error_type')}
                result['collection']['cooldown_sources']=sum(float(s.get('cooldown_until') or 0)>datetime.now(timezone.utc).timestamp() for s in raw.get('source_health',[]))
                heartbeat=raw.get('heartbeat_at') or raw.get('updated_at')
                last_tick=datetime.fromisoformat(heartbeat).timestamp() if heartbeat else 0
                deadline=max(last_tick+120,float(raw.get('next_attempt_epoch') or 0)+120)
                result['collection']['stale']=bool(raw.get('running')) and datetime.now(timezone.utc).timestamp()>deadline
                stamp=raw.get('last_publish_success')
                result['publication_lag_seconds']=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(stamp)).total_seconds()) if stamp else None
                result['pending_serving_reload']=raw.get('serving_version')!=self.version
            except (ValueError,OSError,TypeError):result['collection_status_error']='unreadable'
        return result
