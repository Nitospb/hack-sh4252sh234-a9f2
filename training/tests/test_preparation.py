from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from training.common import batches, config_fingerprint, retrieval_metrics, verify_bundle, write_json, digest
from training.prepare import duplicate_groups, split_records, validate_labels, validate_news


class PreparationTests(unittest.TestCase):
    def row(self, i):
        return {'id':str(i),'text_hash':'hash-'+str(i), 'content_hash':'content-'+str(i),
            'title':'Distinct title '+str(i), 'text':' '.join('token'+str(i)+'word'+str(j) for j in range(80)),
            'published_at':(datetime(2026,10,1,tzinfo=timezone.utc)+timedelta(hours=i)).isoformat(),
            'text_scope':'extracted_article'}

    def test_telegram_and_excerpt_and_unknown_dates_fail_closed(self):
        for change in [{'kind':'telegram_post'}, {'ml_export_allowed':False},
                       {'text_scope':'accessible_excerpt'}, {'published_at':'2026-10-02'},
                       {'published_at':'2026-11-02T00:00:00Z'}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_news([{**self.row(1), **change}])

    def test_exact_duplicates_rejected(self):
        with self.assertRaises(ValueError):
            validate_news([self.row(1), {**self.row(2), 'text_hash':'hash-1'}])

    def test_copy_clusters_do_not_cross_time_splits(self):
        rows = [self.row(i) for i in range(20)]
        rows[19]['title'] = rows[0]['title'] = 'Same news title long enough for a syndication fingerprint'
        grouped = duplicate_groups(validate_news(rows))
        self.assertEqual(len(grouped), 19)
        group = next(r for r in grouped if len(r['group_member_ids'])==2)
        self.assertEqual(group['id'], '19')
        splits = split_records(grouped)
        identifiers = [{r['group_id'] for r in split} for split in splits.values()]
        self.assertFalse(identifiers[0]&identifiers[1] or identifiers[0]&identifiers[2] or identifiers[1]&identifiers[2])
        self.assertLess(max(r['published_at'] for r in splits['train']), min(r['published_at'] for r in splits['validation']))

    def test_reworded_copy_detected_by_shingle_jaccard(self):
        a, b = self.row(1), self.row(2)
        b['text'] = a['text']+' an extra short sentence'
        self.assertEqual(len(duplicate_groups([a,b])), 1)

    def test_pending_null_is_not_a_negative(self):
        row = dict(family_key='family', article_id='1', judgment=None, review_status='pending')
        with self.assertRaises(ValueError):
            validate_labels([row], {'1':self.row(1)}, {'family':{}})

    def test_positive_needs_real_evidence(self):
        row = dict(family_key='family', article_id='1', judgment=2, review_status='approved', annotator='reviewer',
                   reviewed_at='2026-10-25T12:00:00Z', reason='checked', evidence='fabricated evidence')
        with self.assertRaises(ValueError):
            validate_labels([row], {'1':self.row(1)}, {'family':{}})
        row['evidence'] = self.row(1)['text'][:20]
        self.assertEqual(len(validate_labels([row], {'1':self.row(1)}, {'family':{}})), 1)

    def test_no_singleton_contrastive_batch_and_no_data_loss(self):
        planned = batches(list(range(17)), 16)
        self.assertEqual([len(batch) for batch in planned], [17])
        self.assertEqual(sorted(i for batch in planned for i in batch), list(range(17)))

    def test_known_retrieval_ranks(self):
        result = retrieval_metrics([[.1,.9,.4],[.8,.3,.1]], [{1},{1}])
        self.assertEqual(result['recall@1'], .5)
        self.assertEqual(result['mrr@10'], .75)
        self.assertEqual(result['evaluated_queries'], 2)

    def test_data_manifest_detects_tampering(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'pairs.jsonl').write_text('{}\n')
            write_json(root/'manifest.json', {'schema_version':1,'files_sha256':{'pairs.jsonl':digest(root/'pairs.jsonl')}})
            verify_bundle(root)
            (root/'pairs.jsonl').write_text('tampered')
            with self.assertRaises(ValueError):
                verify_bundle(root)

    def test_resume_fingerprint_ignores_only_machine_paths(self):
        a = {'epochs':3,'device':'mps','data_dir':'/one'}
        self.assertEqual(config_fingerprint(a),config_fingerprint({**a,'device':'cuda','data_dir':'/two'}))
        self.assertNotEqual(config_fingerprint(a),config_fingerprint({**a,'epochs':4}))


if __name__=='__main__':unittest.main()

class EvidenceWindowTests(unittest.TestCase):
    def test_late_positive_evidence_not_lost_by_lead_truncation(self):
        from training.prepare import positive_passage
        evidence = 'Подтвержденная информация о банковской гарантии'
        article = {'title':'Финансовый обзор','text':'Общий контекст. '*1000+evidence+' Подробности.'}
        passage = positive_passage(article,evidence)
        self.assertIn(evidence,passage)
        self.assertLess(passage.index(evidence),700)
