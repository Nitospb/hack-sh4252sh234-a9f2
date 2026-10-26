"""Freeze one leased catalog generation and the assets needed for online serving."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.publication import FileLease, validate
from package_release import Parts, digest


def package(root, output, *, allow_synthetic=False, part_mib=64, with_training=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    if part_mib < 1:raise ValueError('part_mib must be positive')
    if output.exists():raise ValueError('Use a new bundle directory')
    base=root/'pipeline/output'
    releases=base/'releases'
    version=json.loads((releases/'current.json').read_text())['version']
    if not isinstance(version,str) or not re.fullmatch('[0-9a-f]{64}',version):raise ValueError('Invalid generation')
    lease=FileLease(releases,version,'export')
    try:
        generation=releases/version
        if generation.is_symlink():raise ValueError('Symlink generation')
        frozen=json.loads((generation/'manifest.json').read_text())
        files=frozen['files']
        if frozen['version']!=version or hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()!=version:
            raise ValueError('Generation manifest mismatch')
        for name,sha in files.items():
            if Path(name).name!=name or (generation/name).is_symlink() or digest(generation/name)!=sha:
                raise ValueError('Generation integrity failed')
        counts=validate(generation,synthetic=allow_synthetic)
        paths={f'pipeline/output/{name}':generation/name for name in files}
        for name in ('service-assets.sqlite','bank-semantic.sqlite'):
            source=base/name
            if name=='service-assets.sqlite' or source.exists():paths[f'pipeline/output/{name}']=source
        with sqlite3.connect((base/'service-assets.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            for stored,expected_sha in db.execute('SELECT path,sha256 FROM bank_documents'):
                name=Path(stored).name
                if Path(name).name!=name:raise ValueError('Invalid PDF filename')
                pdf=root/'data/reports'/name
                if pdf.is_symlink() or digest(pdf)!=expected_sha:raise ValueError('PDF integrity failed')
                paths['data/reports/'+name]=pdf
        if with_training:
            for relative in ('news_matching/models','training/data/news-v1'):
                directory=root/relative
                if not directory.is_dir() or directory.is_symlink():raise ValueError('Missing training kit: '+relative)
                for source in directory.rglob('*'):
                    if source.is_symlink():raise ValueError('Training kit contains symlink')
                    if source.is_file() and not any(p.startswith('.') or p in ('__pycache__','node_modules') for p in source.relative_to(directory).parts):
                        if source.suffix.lower() in ('.log','.tmp','.lock') or any(w in source.name.lower() for w in ('credential','cookie','secret')):continue
                        paths[source.relative_to(root).as_posix()]=source
        if any(p.is_symlink() or not p.is_file() for p in paths.values()):raise ValueError('Missing or symlink serving asset')
        try:commit=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
        except subprocess.CalledProcessError:commit=None
        output.mkdir(parents=True)
        manifest={'schema_version':2,'bundle_kind':'online-serving-and-training-kit' if with_training else 'online-serving','created_at':datetime.now(timezone.utc).isoformat(),
                  'code_commit':commit,'catalog_generation':version,'counts':counts,'files':[],
                  'archive_format':'concatenated gzip tar parts','snapshot_note':'One immutable catalog generation. Assets use SQLite backup; no shared transaction between assets databases.',
                  'excluded':['mutable user state','secrets','browser runtime','raw collection queues',*(['training data'] if not with_training else []),*(['model weights (online serving uses precomputed vectors)'] if not with_training else [])]}
        writer=Parts(output,part_mib*1024*1024)
        with tempfile.TemporaryDirectory(prefix='serving-assets-') as temp:
            with gzip.GzipFile(fileobj=writer,mode='wb',compresslevel=3,mtime=0) as compressed,tarfile.open(mode='w|',fileobj=compressed) as tar:
                for relative,source in sorted(paths.items()):
                    method='immutable_generation' if source.parent==generation else 'file'
                    if source.name in ('service-assets.sqlite','bank-semantic.sqlite'):
                        snapshot=Path(temp)/source.name
                        with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as live,sqlite3.connect(snapshot) as copy:live.backup(copy)
                        source=snapshot;method='sqlite_backup'
                        with sqlite3.connect(source) as db:
                            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Assets integrity failed')
                    info=tar.gettarinfo(str(source),arcname=relative);info.uid=info.gid=0;info.uname=info.gname='';info.mode=0o644
                    with source.open('rb') as stream:tar.addfile(info,stream)
                    manifest['files'].append({'path':relative,'bytes':info.size,'sha256':digest(source),'snapshot_method':method})
            writer.finish_part()
        manifest['parts']=writer.entries
        manifest['total_uncompressed_bytes']=sum(f['bytes'] for f in manifest['files'])
        manifest['total_compressed_bytes']=writer.total
        (output/'release-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
        (output/'README.md').write_text('''# Online serving bundle\n\nRestore into a NEW checkout/folder:\n\n    python3 tools/restore_release.py --no-download --directory /absolute/bundle --target /absolute/checkout\n\nThe catalog is a frozen generation placed at pipeline/output for first startup.\nNo active-worker status, leases or old generation pointers are restored.\nRun Docker with ALFA_REQUIRE_FULL=1. Supply a gateway key separately.\nUser state is deliberately excluded; transfer it separately with service.backup.\nThis bundle runs the web/API with precomputed vectors. Training/rebuilding/live\nindexing requires the original model/data kit described in .ai/training/RUNBOOK.md.\nDo not publish company assets or private state without the owner's approval.\n''')
        return manifest
    finally:lease.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--with-training',action='store_true');parser.add_argument('--part-mib',type=int,default=64);parser.add_argument('--allow-synthetic',action='store_true');args=parser.parse_args()
    result=package(args.root,args.output,allow_synthetic=args.allow_synthetic,part_mib=args.part_mib,with_training=args.with_training)
    print(json.dumps({key:result[key] for key in ('catalog_generation','counts','total_uncompressed_bytes','total_compressed_bytes')},indent=2))
