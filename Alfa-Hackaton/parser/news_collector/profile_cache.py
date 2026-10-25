"""Own Chrome storage, separate from the news corpus; prune only closed profiles.

No cookies, local storage, IndexedDB, site preferences or news files are deleted.
Locks coordinate new browsers and maintenance; Chrome SingletonLock and a grace
period also protect browsers started by older collector processes.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import errno
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

LOG = logging.getLogger(__name__)
HTTP_CACHE_BYTES = 8 * 1024 * 1024
# Exact allowlist. In particular, do not prune Network/Cookies, Local Storage,
# IndexedDB, Service Worker state, Preferences, certificates or safety lists.
DISPOSABLE = (
    'Default/Cache', 'Default/Code Cache', 'Default/GPUCache',
    'Default/DawnWebGPUCache', 'Default/DawnGraphiteCache',
    'GraphiteDawnCache', 'GrShaderCache', 'ShaderCache',
    'component_crx_cache', 'optimization_guide_model_store',
    'WasmTtsEngine', 'OnDeviceHeadSuggestModel', 'BrowserMetrics',
    'BrowserMetrics-spare.pma', 'Crashpad',
)


class ProfileBusy(RuntimeError):
    pass


def cache_base():
    override = os.environ.get('ALFA_BROWSER_CACHE')
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Caches' / 'alfa-news-collector'
    return Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'alfa-news-collector'


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def chrome_paths():
    """Also covers the short startup interval before SingletonLock appears."""
    output = subprocess.check_output(['ps', '-Ao', 'command='], text=True)
    paths = set()
    for line in output.splitlines():
        if '--type=' in line or '--user-data-dir=' not in line:
            continue
        if not any(name in line.lower() for name in ('chrome', 'chromium')):
            continue
        match = re.search(r'--user-data-dir=(.*?)(?=\s--[\w-]+(?:=|\s|$)|$)', line)
        if match:
            paths.add(Path(match[1].strip(' "')).resolve())
    return paths


def native_busy(profile, running=()):
    if profile.resolve() in running:
        return True
    lock = profile / 'SingletonLock'
    if lock.is_symlink():
        try:
            target = os.readlink(lock)
            return alive(int(target.rsplit('-', 1)[1]))
        except (OSError, ValueError, IndexError):
            return True  # unknown lock formats are left alone
    return lock.exists()


def size_bytes(path):
    if path.is_symlink():
        return path.lstat().st_size
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for directory, _, files in os.walk(path, followlinks=False):
        for name in files:
            try:
                total += (Path(directory) / name).lstat().st_size
            except FileNotFoundError:
                pass
    return total


def remove_cache(path, profile):
    """Never follow nested symlinks outside our profile."""
    for parent in path.parents:
        if parent == profile:
            break
        if parent.is_symlink():
            raise ValueError('Symlink inside a cache path: ' + str(parent))
    amount = size_bytes(path)
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)
    return amount


class ProfileStore:
    def __init__(self, logical_root, base=None):
        self.logical_root = Path(logical_root).absolute()
        if self.logical_root.is_symlink():
            raise ValueError('The logical profile root must be a real collector-owned directory')
        self.logical_root = self.logical_root.resolve()
        self.base = (Path(base) if base is not None else cache_base()).resolve()
        runtime = self.logical_root.parent.resolve()
        if self.base == runtime or self.base.is_relative_to(runtime):
            raise ValueError('Chrome cache must be outside the news runtime')
        key = hashlib.sha256(str(self.logical_root).encode()).hexdigest()[:20]
        self.root = self.base / key
        self.base.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.base / (key + '.ownership.lock')).open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.root.mkdir(exist_ok=True, mode=0o700)
            marker = self.root / 'ownership.json'
            owner = {'kind': 'alfa-news-collector-browser-cache', 'version': 1,
                     'logical_profile_root': str(self.logical_root)}
            if marker.exists():
                if json.loads(marker.read_text()) != owner:
                    raise ValueError('Browser-cache ownership mismatch')
            else:
                if any(self.root.iterdir()):
                    raise ValueError('Refusing an unmarked nonempty cache directory')
                marker.write_text(json.dumps(owner, indent=2) + '\n')
        for name in ('profiles', 'http', 'locks'):
            (self.root / name).mkdir(exist_ok=True, mode=0o700)
        self.logical_root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def paths(self, name):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', name):
            raise ValueError('Unsafe profile name')
        return self.logical_root / name, self.root / 'profiles' / name, self.root / 'http' / name

    @contextmanager
    def lease(self, name):
        self.paths(name)
        with (self.root / 'locks' / (name + '.lock')).open('a+') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ProfileBusy(name + ': browser profile is leased') from exc
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def check_closed(self, logical, physical, running=()):
        if logical.is_symlink() and logical.resolve() != physical:
            raise ValueError('Refusing a foreign profile symlink: ' + str(logical))
        if physical.is_symlink():
            raise ValueError('Managed physical profile must not be a symlink')
        if native_busy(logical, running) or native_busy(physical, running):
            raise ProfileBusy(logical.name + ': Chrome is running')

    def prune(self, name, running=()):
        logical, physical, http = self.paths(name)
        self.check_closed(logical, physical, running)
        profile = physical if logical.is_symlink() or not logical.exists() else logical
        removed = 0
        for relative in DISPOSABLE:
            # Recheck before every deletion for the legacy collector which does
            # not yet acquire our lease. New Browser instances always lease.
            self.check_closed(logical, physical)
            removed += remove_cache(profile / relative, profile)
        if http.exists() or http.is_symlink():
            self.check_closed(logical, physical)
            removed += remove_cache(http, self.root / 'http')
        return removed

    def prepare(self, name, running=()):
        logical, physical, http = self.paths(name)
        self.check_closed(logical, physical, running)
        removed = self.prune(name, running)
        if logical.exists() and not logical.is_symlink():
            if not logical.is_dir():
                raise ValueError('Expected a profile directory')
            if physical.exists():
                if any(physical.iterdir()):
                    raise ValueError('Both legacy and managed profiles exist; preserve both for review')
                physical.rmdir()
            try:
                logical.rename(physical)
            except OSError as exc:
                if exc.errno != errno.EXDEV:
                    raise
                # Across filesystems, retain the original until a complete copy
                # exists and Chrome is confirmed closed again.
                temporary = physical.with_name(physical.name + '.migration')
                shutil.copytree(logical, temporary, symlinks=True)
                self.check_closed(logical, physical)
                temporary.rename(physical)
                shutil.rmtree(logical)
        physical.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not logical.is_symlink():
            try:
                logical.symlink_to(physical, target_is_directory=True)
            except FileExistsError:
                # An old browser created the logical directory in the interim.
                # Do not overwrite or merge its live state.
                raise ProfileBusy(name + ': legacy profile appeared during migration')
        http.mkdir(parents=True, exist_ok=True, mode=0o700)
        return physical, http, removed

    def sweep(self, names, grace_seconds=180):
        running = chrome_paths()  # if ps fails, abort without deleting anything
        result = {'removed_bytes': 0, 'prepared': 0, 'busy': 0, 'recent': 0, 'errors': []}
        for name in names:
            try:
                with self.lease(name):
                    logical, physical, _ = self.paths(name)
                    self.check_closed(logical, physical, running)
                    existing = physical if logical.is_symlink() else logical
                    if existing.exists() and time.time() - existing.stat().st_mtime < grace_seconds:
                        result['recent'] += 1
                        continue
                    _, _, removed = self.prepare(name, running)
                    result['removed_bytes'] += removed
                    result['prepared'] += 1
            except ProfileBusy:
                result['busy'] += 1
            except Exception as exc:
                result['errors'].append({'profile': name, 'error': str(exc)[:400]})
        return result


class ProfileSession:
    """Lease for the whole Chrome lifetime, including startup and shutdown."""
    def __init__(self, logical):
        logical = Path(logical)
        self.store = ProfileStore(logical.parent)
        self.name = logical.name
        self._lease = None

    def open(self):
        lease = self.store.lease(self.name)
        lease.__enter__()
        self._lease = lease
        try:
            profile, http, _ = self.store.prepare(self.name, chrome_paths())
            return profile, http
        except BaseException:
            self.close()
            raise

    def close(self):
        if self._lease is not None:
            try:
                self.store.prune(self.name, chrome_paths())
            except Exception as exc:
                LOG.warning('Profile cleanup skipped profile=%s: %s', self.name, exc)
            finally:
                self._lease.__exit__(None, None, None)
                self._lease = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path('config/sources.json'))
    parser.add_argument('--watch-pid', type=int)
    parser.add_argument('--interval', type=float, default=30)
    parser.add_argument('--grace-seconds', type=float, default=180)
    args = parser.parse_args()
    if args.interval < 5 or args.grace_seconds < 0 or args.watch_pid is not None and args.watch_pid < 1:
        parser.error('Interval >=5, grace >=0, positive PID required')
    store = ProfileStore(args.runtime.resolve() / 'profiles')
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    with (store.root / 'maintenance.lock').open('a+') as manager_lock:
        try:
            fcntl.flock(manager_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.exit(1, 'Cache maintenance is already running for this runtime\n')
        path = store.root / 'maintenance.json'
        previous = json.loads(path.read_text()) if path.exists() else {}
        total_removed = previous.get('removed_bytes_total', 0) if previous.get('collector_pid') == args.watch_pid else 0
        while not stop.is_set():
            finished = bool(args.watch_pid and not alive(args.watch_pid))
            names = [source['id'] for source in json.loads(args.config.read_text())['sources'] if source.get('enabled', True)]
            # Once the collector exits, remove caches of the last closed batch
            # immediately. Native Chrome locks still protect any live browser.
            result = store.sweep(names, 0 if finished else args.grace_seconds)
            total_removed += result['removed_bytes']
            report = {'updated_at': datetime.now(timezone.utc).isoformat(), 'pid': os.getpid(),
                      'status': 'complete' if finished or not args.watch_pid else 'watching',
                      'collector_pid': args.watch_pid, 'cache_root': str(store.root),
                      'removed_bytes_total': total_removed, **result}
            temporary = store.root / 'maintenance.json.tmp'
            temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            temporary.replace(path)
            print(json.dumps(report, ensure_ascii=False), flush=True)
            if not args.watch_pid or finished:
                break
            stop.wait(args.interval)


if __name__ == '__main__':
    main()
