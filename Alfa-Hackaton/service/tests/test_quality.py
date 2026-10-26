import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from service.quality import status
from evaluation.score import evaluate

class QualityTests(unittest.TestCase):
    def test_missing_and_invalid_reports_never_claim_accuracy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.assertEqual(status(root)['status'],'not_measured')
            (root/'evaluation-report.json').write_text('{}');self.assertEqual(status(root)['status'],'invalid_report')
    def test_report_retains_nulls_until_human_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bundle={'dataset_version':'test','catalog_version':'test','rubric_version':'v1','split':'validation','queries':[]}
            report=evaluate(bundle);report['input_sha256']='a'*64
            (root/'evaluation-report.json').write_text(json.dumps(report))
            result=status(root);self.assertEqual(result['approved_pairs'],0);self.assertEqual(result['status'],'not_measured')
