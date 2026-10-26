import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from training.common import digest, write_json
from training.compare import compare
from training.train import load_resume, replace_directory


class CheckpointTests(unittest.TestCase):
    def test_only_complete_checksum_valid_state_resumes(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'latest'
            path.mkdir()
            expected = {key:'value' for key in ('data_manifest_sha256','source_model_sha256','tokenizer_sha256','config_fingerprint','code_sha256')}
            write_json(path/'state.json', expected)
            write_json(path/'CHECKSUMS.json', {'state.json':digest(path/'state.json')})
            self.assertEqual(load_resume(path,expected),expected)
            with self.assertRaises(ValueError):
                load_resume(path,{**expected,'data_manifest_sha256':'different'})
            (path/'state.json').write_text('corrupt')
            with self.assertRaises(ValueError):load_resume(path,expected)

    def test_recovers_previous_generation_after_interrupted_rename(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'latest'
            old = path.with_name('latest.previous')
            old.mkdir()
            expected = {key:'value' for key in ('data_manifest_sha256','source_model_sha256','tokenizer_sha256','config_fingerprint','code_sha256')}
            write_json(old/'state.json',expected)
            write_json(old/'CHECKSUMS.json',{'state.json':digest(old/'state.json')})
            self.assertEqual(load_resume(path,expected),expected)
            self.assertTrue(path.exists())

    def test_publishes_next_checkpoint_generation(self):
        with TemporaryDirectory() as tmp:
            latest, new = Path(tmp)/'latest',Path(tmp)/'new'
            latest.mkdir();new.mkdir()
            (latest/'data').write_text('old');(new/'data').write_text('new')
            replace_directory(new,latest)
            self.assertEqual((latest/'data').read_text(),'new')
            self.assertFalse((Path(tmp)/'latest.previous').exists())

    def test_rejects_comparison_of_different_heldouts(self):
        metrics = {key:.5 for key in ('recall@1','recall@5','recall@10','mrr@10','ndcg@10')}
        row = {**metrics,'mode':'weak_title_body','split':'test','data_manifest_sha256':'a',
               'evaluated_queries':2,'documents':2}
        with self.assertRaises(ValueError):compare(row,{**row,'data_manifest_sha256':'b'})
        report = compare(row,{**row,'mrr@10':.6})
        self.assertTrue(report['retrieval_improved'])
        self.assertFalse(report['automatic_promotion'])


if __name__=='__main__':unittest.main()
