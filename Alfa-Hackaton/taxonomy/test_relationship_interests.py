"""Small, independent fixtures for graph interest propagation."""
import contextlib
import csv
import io
import json
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import enrich_relationship_interests as rel


class PaymentGraphTests(unittest.TestCase):
    def graph(self, rows, known=None, conflicts=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        path = root / 'payments.csv'
        with path.open('w', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['PAYER', 'BENEFICIARY', 'PAY_AMT', 'PAY_CNT'])
            writer.writerows(rows)
        result = rel.prepare_payments(path, root/'graph.sqlite', known or {'A', 'B', 'C'}, conflicts or set())
        return root, result

    def test_duplicate_pairs_keep_decimal_precision_and_source_counts(self):
        root, (_, outgoing, _, stats) = self.graph([
            ('A', 'B', '9007199254740993.1', 2), ('A', 'B', '0.2', 3)])
        with sqlite3.connect(root/'graph.sqlite') as db:
            amount, count, source_rows = db.execute('SELECT amount,payment_count,source_rows FROM payments').fetchone()
        self.assertEqual(Decimal(amount), Decimal('9007199254740993.3'))
        self.assertEqual((count, source_rows), (5, 2))
        self.assertEqual(stats['duplicate_rows_aggregated'], 1)
        self.assertEqual(outgoing['A'][0][2][1:], (5, 2))

    def test_self_payments_do_not_change_denominators_or_graph(self):
        root, (totals, _, _, stats) = self.graph([('A', 'A', '10000', 100), ('A', 'B', '10', 1)])
        self.assertEqual(totals['A']['out_amount'], Decimal('10'))
        self.assertEqual(totals['A']['in_amount'], 0)
        self.assertEqual(stats['excluded_self_payment_rows'], 1)
        with sqlite3.connect(root/'graph.sqlite') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM payments').fetchone()[0], 1)

    def test_unknown_and_conflicted_peers_remain_in_denominator(self):
        _, (totals, outgoing, incoming, _) = self.graph([
            ('A', 'B', '10', 1), ('A', 'UNKNOWN', '60', 6), ('A', 'C', '30', 3),
            ('UNKNOWN', 'A', '90', 9), ('B', 'A', '10', 1)], conflicts={'C'})
        self.assertEqual(totals['A']['out_amount'], Decimal(100))
        self.assertEqual(totals['A']['out_profiled_amount'], Decimal(10))
        self.assertEqual(totals['A']['out_peers'], 3)
        self.assertEqual([v[1] for v in outgoing['A']], ['B'])
        self.assertAlmostEqual(outgoing['A'][0][0], .1)
        self.assertAlmostEqual(incoming['A'][0][0], .1)

    def test_directional_amount_and_count_have_separate_weights(self):
        _, (_, outgoing, incoming, _) = self.graph([
            ('A', 'B', '90', 1), ('A', 'C', '10', 9),
            ('B', 'A', '10', 9), ('C', 'A', '90', 1)])
        out = {peer: score for score, peer, _ in outgoing['A']}
        inc = {peer: score for score, peer, _ in incoming['A']}
        self.assertAlmostEqual(out['B'], .7)
        self.assertAlmostEqual(out['C'], .3)
        self.assertAlmostEqual(inc['B'], .3)
        self.assertAlmostEqual(inc['C'], .7)


class ContextAndTopicTests(unittest.TestCase):
    def test_person_and_group_representatives_use_clusters_and_stable_ties(self):
        profiles = {'A': {'code': '46.51'}, 'B': {'code': '10.11'},
                    'C': {'code': '10.11'}, 'D': {'code': '20.10'}, 'E': {'code': '30.10'}}
        # The same selector serves shared-person and GROUP_ID membership.
        for members in [{'A', 'B', 'C', 'D', 'E', 'UNKNOWN'}, ['E', 'D', 'C', 'B', 'A', 'UNKNOWN']]:
            chosen, eligible, activities = rel.selected_context_peers('A', members, profiles)
            self.assertEqual(chosen, [('B', 2), ('D', 1)])
            self.assertEqual((eligible, activities), (4, 3))

    def test_direction_selector_and_missing_key_fallback(self):
        context = {('46.51', 'Computers'): dict(a='T1', b='T2', c='T3', d='T4', e='T5')}
        selector = {'46': {'outgoing_payment': ['e', 'missing'], 'incoming_payment': ['d', 'c'], 'related_company': ['b']}}
        peer = {'code': '46.51', 'activity': 'Computers'}
        self.assertEqual(rel.select_topics(peer, 'outgoing_payment', context, selector, set()), ['T5', 'T1', 'T2', 'T3'])
        self.assertEqual(rel.select_topics(peer, 'incoming_payment', context, selector, set()), ['T4', 'T3', 'T1', 'T2'])
        self.assertEqual(rel.select_topics(peer, 'shared_person', context, selector, set()), ['T2', 'T1', 'T3', 'T4'])

    def test_exact_override_avoids_semantically_unrelated_positional_keys(self):
        context = {('46.51', 'Computers'): dict(a='T1', b='T2', c='T3', d='T4', e='T5')}
        selector = {'46': {'outgoing_payment': ['e']}}
        self.assertEqual(rel.select_topics({'code': '46.51', 'activity': 'Computers'}, 'outgoing_payment', context, selector, {'46.51'}), ['T1', 'T2', 'T3', 'T4'])

    def test_build_filters_peer_product_flags_before_topic_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'source'; base = root/'base'
            source.mkdir(); base.mkdir()
            (source/'df_Uid_data_hack.csv').write_text('SYNTHETIC_U;MAINOKVED_CODE;MAINOKVED_NAME;GROUP_ID;REGION\nA;46.51;Computers;;R\nB;46.51;Computers;;R\n')
            (source/'df_Fid_Uid_link_hack.csv').write_text('SYNTHETIC_F;SYNTHETIC_U\n')
            (source/'df_Uid_payment_hack.csv').write_text('PAYER;BENEFICIARY;PAY_AMT;PAY_CNT\nA;B;10;1\n')
            catalog = [dict(topic_id='PRODUCT', activity_code='46.51', activity_name='Computers', aspect_key='product', required_flag='CL_PRODUCT_LOA_MARK', name='Credit')]
            catalog += [dict(topic_id=f'T{i}', activity_code='46.51', activity_name='Computers', aspect_key=f'aspect_{i:02}', required_flag=None, name=f'Own {i}') for i in range(1, 13)]
            (base/'activity_interest_catalog.jsonl').write_text(''.join(json.dumps(v)+'\n' for v in catalog))
            records = [dict(company_id=uid, source_record_id=uid, okved='46.51', activity='Computers', topic_ids=[f'T{i}' for i in range(1, 13)], status='ok') for uid in ['A', 'B']]
            (base/'company_interests.jsonl').write_text(''.join(json.dumps(v)+'\n' for v in records))
            with contextlib.redirect_stdout(io.StringIO()):
                rel.build(source, root/'out', base)
            links = [json.loads(v) for v in (root/'out'/'relationships.jsonl').read_text().splitlines()]
            self.assertEqual(len(links), 2)
            self.assertTrue(all(len(v['topic_ids']) == 4 for v in links))
            self.assertTrue(all('PRODUCT' not in v['topic_ids'] for v in links))
            self.assertTrue(all(.6 <= v['ranking_weight'] <= 1 for v in links))


if __name__ == '__main__':
    unittest.main()
