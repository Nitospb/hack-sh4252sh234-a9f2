import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from service.seed import create
from pipeline.publication import publish,validate
from serving_bundle import package
from restore_release import restore


class ServingBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'repo'
        self.base=self.root/'Alfa-Hackaton/pipeline/output';create(self.base)
        self.generation=publish(self.base,self.base/'releases',allow_synthetic=True)
        (self.base/'feedback.sqlite').write_text('private user state')
        (self.root/'Alfa-Hackaton/.env').write_text('SECRET=do-not-export')
        self.out=Path(self.temp.name)/'bundle'

    def tearDown(self):self.temp.cleanup()

    def test_freeze_restore_and_state_exclusion(self):
        manifest=package(self.root,self.out,allow_synthetic=True,part_mib=1)
        names={f['path'] for f in manifest['files']}
        self.assertFalse(any('feedback' in n or '.env' in n or 'releases/' in n for n in names))
        target=Path(self.temp.name)/'clean'
        with contextlib.redirect_stdout(io.StringIO()):restore(self.out,target)
        restored=target/'Alfa-Hackaton/pipeline/output'
        self.assertEqual(validate(restored,synthetic=True)['articles'],6)
        self.assertTrue((restored/'service-assets.sqlite').exists())
        self.assertFalse(list((self.base/'reader-leases').glob('**/*.lease')))

    def test_generation_tamper_fails_without_bundle(self):
        path=self.base/'releases'/self.generation['version']/'report.json';path.write_text('{}')
        with self.assertRaisesRegex(ValueError,'integrity'):package(self.root,self.out,allow_synthetic=True)
        self.assertFalse(self.out.exists())

    def test_no_overwrite(self):
        self.out.mkdir()
        with self.assertRaises(ValueError):package(self.root,self.out,allow_synthetic=True)

    def test_synthetic_is_opt_in(self):
        with self.assertRaises(ValueError):package(self.root,self.out)
        self.assertFalse(self.out.exists())

    def test_training_option_is_explicit_and_does_not_package_runtime(self):
        models=self.root/'Alfa-Hackaton/news_matching/models';models.mkdir(parents=True)
        (models/'weights.onnx').write_bytes(b'test weights')
        training=self.root/'Alfa-Hackaton/training/data/news-v1';training.mkdir(parents=True)
        (training/'manifest.json').write_text('{}')
        manifest=package(self.root,self.out,allow_synthetic=True,with_training=True)
        self.assertEqual(manifest['bundle_kind'],'online-serving-and-training-kit')
        self.assertTrue(any(f['path'].endswith('weights.onnx') for f in manifest['files']))
