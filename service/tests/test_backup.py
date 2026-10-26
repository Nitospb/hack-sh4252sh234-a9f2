from pathlib import Path
import sqlite3
import tempfile
import unittest
from service.backup import backup,restore,FILES


class BackupTests(unittest.TestCase):
    def test_live_wal_backup_restore_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=root/'state';state.mkdir();connections=[]
            try:
                for name in FILES:
                    db=sqlite3.connect(state/name);db.executescript('PRAGMA journal_mode=WAL; CREATE TABLE data(value TEXT); INSERT INTO data VALUES("before");');connections.append(db)
                manifest=backup(state,root/'backup')
                self.assertEqual(set(manifest['files']),set(FILES))
                for db in connections:db.execute('UPDATE data SET value="after"');db.commit()
                restore(root/'backup',root/'restored')
                for name in FILES:
                    with sqlite3.connect(root/'restored'/name) as db:self.assertEqual(db.execute('SELECT value FROM data').fetchone()[0],'before')
                with self.assertRaises(ValueError):restore(root/'backup',root/'restored')
                with self.assertRaises(ValueError):backup(state,root/'backup')
            finally:
                for db in connections:db.close()

    def test_corruption_is_rejected_before_state_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=root/'state';state.mkdir()
            for name in FILES:
                with sqlite3.connect(state/name) as db:db.execute('CREATE TABLE data(value TEXT)')
            backup(state,root/'backup')
            with (root/'backup/feedback.sqlite').open('ab') as stream:stream.write(b'tampered')
            with self.assertRaises(ValueError):restore(root/'backup',root/'restored')
            self.assertFalse((root/'restored').exists())
