"""Import a verified analysis subset of the final collector export.

Copies news views, topics, Telegram, input CSV, schemas and provenance. Raw HTML,
collector queues and source code remain in the original immutable package.
The imported SHA256SUMS still describes that full package, not just this subset.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def import_snapshot(source, destination):
    source, destination = source.resolve(), destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Source and destination must be separate directories')
    checks = {}
    for line in (source/'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        expected, relative = line.split('  ', 1)
        checks[relative.removeprefix('./')] = expected
    selected = []
    for path in sorted(source.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if path.is_symlink():
            raise ValueError(f'Symlink not permitted: {relative}')
        include = relative.parts[0] in {'topics', 'telegram', 'inputs', 'metadata', 'schema', 'tools'}
        include |= relative.parts[0] == 'data' and path.suffix == '.jsonl' and path.stem != 'revisions'
        include |= len(relative.parts) == 1
        if not include:
            continue
        actual = digest(path)
        if relative.as_posix() != 'SHA256SUMS' and checks.get(relative.as_posix()) != actual:
            raise ValueError(f'Source checksum failed: {relative}')
        output = destination/relative
        if output.exists() and digest(output) != actual:
            raise ValueError(f'Will not overwrite different file: {output}')
        selected.append((path, output, relative, actual))
    # Verify every selected source before writing any data.
    for path, output, relative, actual in selected:
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.exists():
            temporary = output.with_name(output.name + '.importing')
            shutil.copy2(path, temporary)
            if digest(temporary) != actual:
                raise ValueError(f'Copy checksum failed: {relative}')
            temporary.replace(output)
    report = {'source': str(source), 'files': len(selected), 'bytes': sum(p.stat().st_size for p, *_ in selected),
        'verified': True, 'scope': __doc__,
        'imported_files': {r.as_posix(): h for _, _, r, h in selected}}
    (destination/'LOCAL_IMPORT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    result = import_snapshot(args.source, args.destination)
    print(f"Verified/imported {result['files']} files; {result['bytes']} bytes")
