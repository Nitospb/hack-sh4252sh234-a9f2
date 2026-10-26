import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from import_snapshot import import_snapshot


class ImportSnapshotTests(unittest.TestCase):
    def fixture(self, root):
        source = root/'source'
        source.mkdir()
        files = {'data/training-news.jsonl': b'{"id":"a"}\n',
                 'raw/page.html.gz': b'not-needed', 'README.md': b'original readme'}
        for relative, content in files.items():
            path = source/relative
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_bytes(content)
        (source/'SHA256SUMS').write_text(''.join(
            hashlib.sha256(content).hexdigest()+'  '+relative+'\n' for relative, content in files.items()))
        return source

    def test_subset_verified_and_repeatable(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.fixture(root)
            result = import_snapshot(source, root/'destination')
            self.assertTrue(result['verified'])
            self.assertTrue((root/'destination/data/training-news.jsonl').exists())
            self.assertFalse((root/'destination/raw').exists())
            self.assertEqual(result['files'], import_snapshot(source, root/'destination')['files'])

    def test_tampered_source_rejected_before_copy(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.fixture(root)
            (source/'data/training-news.jsonl').write_text('tampered')
            with self.assertRaises(ValueError):
                import_snapshot(source, root/'destination')
            self.assertFalse((root/'destination').exists())

    def test_existing_different_destination_is_preserved(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.fixture(root)
            destination = root/'destination'
            destination.mkdir()
            (destination/'README.md').write_text('team additions')
            with self.assertRaises(ValueError):
                import_snapshot(source, destination)
            self.assertEqual((destination/'README.md').read_text(), 'team additions')


if __name__ == '__main__':
    unittest.main()
