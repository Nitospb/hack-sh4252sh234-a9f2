import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from recommendations.engine import Feed
from service.seed import create


class RelationshipRankingTests(unittest.TestCase):
    def test_observed_payment_adds_conditional_hint_without_changing_article_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);catalog=create(root/'catalog')
            with sqlite3.connect(catalog) as db:
                db.execute('DELETE FROM company_mapping');db.execute('DELETE FROM company_family_mapping')
            with sqlite3.connect(catalog.parent/'ranking.sqlite') as db:
                db.executescript('''CREATE TABLE article_industries(article_id TEXT,sector_id TEXT,score REAL,evidence TEXT);
                CREATE TABLE company_industries(okved TEXT,sector_id TEXT,reason TEXT,relation TEXT);
                CREATE TABLE article_features(article_id TEXT,business_score REAL,general_business INT);
                CREATE TABLE company_profiles(source_record_id TEXT,operating_families TEXT);
                CREATE TABLE article_objects(article_id TEXT,family_key TEXT,embedding_cosine REAL,reranker_logit REAL,evidence TEXT);
                INSERT INTO article_industries VALUES('seed_article_0','partner_sector',1,'source text');
                INSERT INTO company_industries VALUES('99','partner_sector','counterparty sector','declared_activity');''')
                db.executemany('INSERT INTO article_features VALUES(?,.9,1)',[(f'seed_article_{i}',) for i in range(6)])
            with sqlite3.connect(catalog.parent/'service-assets.sqlite') as db:
                db.execute('CREATE TABLE relationships(record_id TEXT,payload TEXT)')
                db.execute('INSERT INTO relationships VALUES(?,?)',('SEED_1:line:2',json.dumps({
                    'relationship_id':'payment_evidence_1','kind':'outgoing_payment','related_company_id':'other',
                    'related_okved':'99','evidence':['observed transfer'],'role_caveat':'Не доказывает договор поставки','ranking_weight':.5})))
            feed=Feed(catalog,root/'state.sqlite',embeddings=False)
            linked=feed.recommend('SEED_1','u1',scope='interest',mode='ranked',limit=6)
            independent=feed.recommend('SEED_2','u2',scope='interest',mode='ranked',limit=6)
            a=next(x for x in linked['items'] if x['article_id']=='seed_article_0')
            b=next(x for x in independent['items'] if x['article_id']=='seed_article_0')
            self.assertGreater(a['components']['company'],b['components']['company'])
            self.assertEqual(a['relationship_context'][0]['relationship_id'],'payment_evidence_1')
            self.assertTrue(a['relationship_context'][0]['conditional'])
            self.assertNotIn('relationship_context',b)
            with sqlite3.connect(catalog) as db:
                self.assertEqual(db.execute("SELECT status FROM articles WHERE article_id='seed_article_0'").fetchone()[0],'synthetic')
