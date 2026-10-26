import contextlib
import io
import json
from pathlib import Path
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import package_release
import restore_release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'project';self.out=Path(self.temp.name)/'parts'
        (self.root/'tools').mkdir(parents=True);(self.root/'data').mkdir()
        (self.root/'data/example.txt').write_text('Business data\n')
        (self.root/'data/random.bin').write_bytes(os.urandom(1300000))
        (self.root/'data/.env').write_text('DO_NOT_DISTRIBUTE=private')
        self.db=sqlite3.connect(self.root/'data/live.sqlite');self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('CREATE TABLE rows(value TEXT)');self.db.execute("INSERT INTO rows VALUES('committed WAL data')");self.db.commit()
        with patch.object(package_release,'ROOT',self.root),patch.object(sys,'argv',['package_release','--output',str(self.out),'--part-mib','1']),contextlib.redirect_stdout(io.StringIO()):
            package_release.main()

    def tearDown(self):self.db.close();self.temp.cleanup()

    def test_roundtrip_includes_committed_wal_without_credentials(self):
        manifest=json.loads((self.out/'release-manifest.json').read_text())
        self.assertEqual(len(manifest['parts']),2)
        self.assertEqual({r['path'] for r in manifest['files']},{'data/example.txt','data/random.bin','data/live.sqlite'})
        target=Path(self.temp.name)/'restored'
        with contextlib.redirect_stdout(io.StringIO()):restore_release.restore(self.out,target)
        self.assertEqual((target/'data/random.bin').read_bytes(),(self.root/'data/random.bin').read_bytes())
        with sqlite3.connect(target/'data/live.sqlite') as db:self.assertEqual(db.execute('SELECT value FROM rows').fetchone()[0],'committed WAL data')
        with contextlib.redirect_stdout(io.StringIO()):restore_release.restore(self.out,target)

    def test_tampered_part_is_rejected_before_extraction(self):
        manifest=json.loads((self.out/'release-manifest.json').read_text());part=self.out/manifest['parts'][0]['file']
        with part.open('r+b') as stream:stream.write(b'BROKEN')
        target=Path(self.temp.name)/'restored'
        with self.assertRaisesRegex(ValueError,'Part integrity failed'):restore_release.restore(self.out,target)
        self.assertFalse(target.exists())

    def test_existing_changed_data_requires_explicit_overwrite(self):
        target=Path(self.temp.name)/'restored';(target/'data').mkdir(parents=True);(target/'data/example.txt').write_text('My local edits')
        with self.assertRaisesRegex(ValueError,'Existing file differs'):restore_release.restore(self.out,target)
        self.assertEqual((target/'data/example.txt').read_text(),'My local edits')

    def test_legacy_nested_application_restores_at_repository_root(self):
        legacy=self.root/'Alfa-Hackaton/pipeline/output'
        legacy.mkdir(parents=True)
        (legacy/'catalog.sqlite').write_bytes(b'legacy catalog')
        archive=Path(self.temp.name)/'legacy-parts'
        with patch.object(package_release,'ROOT',self.root), patch.object(package_release,'ASSET_ROOTS',['Alfa-Hackaton/pipeline/output']), patch.object(sys,'argv',['package_release','--output',str(archive)]), contextlib.redirect_stdout(io.StringIO()):
            package_release.main()
        target=Path(self.temp.name)/'legacy-restored'
        with contextlib.redirect_stdout(io.StringIO()):restore_release.restore(archive,target)
        self.assertEqual((target/'pipeline/output/catalog.sqlite').read_bytes(),b'legacy catalog')
        self.assertFalse((target/'Alfa-Hackaton').exists())

if __name__=='__main__':unittest.main()
