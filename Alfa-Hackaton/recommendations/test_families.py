"""Protect semantic level, company relation and review/date gates in the joined feed."""
import json
import sqlite3
import unittest
import test_engine

class FamilyFeedTests(unittest.TestCase):
    def setUp(self):
        test_engine.FeedTests.setUp(self)
        with sqlite3.connect(self.feed.catalog) as db:
            db.executescript('''DELETE FROM assignments;
            ALTER TABLE articles ADD COLUMN object_eligible_delivery INTEGER DEFAULT 0;
            ALTER TABLE articles ADD COLUMN kind TEXT DEFAULT 'news';
            CREATE TABLE company_family_mapping(okved TEXT,family_key TEXT,relation TEXT,reason TEXT);
            INSERT INTO company_family_mapping VALUES('01','f','declared_activity','Own activity');
            INSERT INTO company_family_mapping VALUES('01','f','operating_exposure','Indirect');
            CREATE TABLE object_families(family_key TEXT,object TEXT);
            INSERT INTO object_families VALUES('f','Пшеница');
            CREATE TABLE family_assignments(article_id TEXT,family_key TEXT,embedding_cosine REAL,reranker_logit REAL,evidence TEXT,status TEXT);
            INSERT INTO family_assignments VALUES('0','f',.9,1.,'Wheat text','accepted');
            INSERT INTO family_assignments VALUES('1','f',.8,-1.,'Wheat candidate','review');''')

    def test_object_is_not_expanded_into_ten_events(self):
        r=self.feed.recommend('c','fresh',scope='strict')
        self.assertEqual([a['article_id'] for a in r['items']],['0'])
        item=r['items'][0]
        self.assertEqual(item['matched_topics'],[])
        self.assertEqual(item['matched_objects'][0]['relation'],'declared_activity')
        self.assertFalse(item['matched_objects'][0]['specific_event_verified'])

    def test_review_is_explicit_and_keeps_quality_gate(self):
        r=self.feed.recommend('c','review',include_review=True)
        items={a['article_id']:a for a in r['items']}
        self.assertEqual(set(items),{'0','1'})
        self.assertTrue(items['1']['review_required'])
        with sqlite3.connect(self.feed.catalog) as db:
            db.execute("UPDATE articles SET eligible_delivery=0 WHERE article_id='1'")
        r=self.feed.recommend('c','other',include_review=True)
        self.assertNotIn('1',[a['article_id'] for a in r['items']])

    def test_unrelated_company_does_not_get_object(self):
        with sqlite3.connect(self.feed.catalog) as db:
            db.execute("UPDATE company_family_mapping SET okved='99'")
        self.assertEqual(self.feed.recommend('c','fresh')['items'],[])

    def tearDown(self):
        test_engine.FeedTests.tearDown(self)

class RankedFeedTests(FamilyFeedTests):
    def test_ranked_review_remains_thematic_and_kind_survives_history(self):
        with sqlite3.connect(self.feed.catalog) as db:
            db.execute("UPDATE family_assignments SET embedding_cosine=.85 WHERE article_id='1'")
            db.execute("UPDATE articles SET kind='telegram_post' WHERE article_id='1'")
        self.feed.event('c','u','0','view','visible-event')
        result = self.feed.recommend('c','u',mode='ranked',kind='telegram_post')
        self.assertEqual([a['article_id'] for a in result['items']],['1'])
        self.assertEqual(result['kind'],'telegram_post')
        self.assertEqual(result['items'][0]['match_level'],'thematic_candidate')
        self.assertFalse(result['items'][0]['matched_objects'][0]['specific_event_verified'])

    def test_content_duplicate_excluded_across_pages(self):
        with sqlite3.connect(self.feed.catalog) as db:
            db.execute("UPDATE articles SET text_hash='identical' WHERE article_id IN ('0','1')")
        self.feed.recommend('c','u',limit=1)
        result=self.feed.recommend('c','u',include_review=True)
        self.assertEqual(result['items'],[])

    def test_role_persisted_and_separate_from_company(self):
        self.feed.profile('c','u',[],role='accountant')
        result=self.feed.recommend('c','u',mode='ranked')
        self.assertEqual(result['role'],'accountant')
        self.assertEqual(result['weights']['company'],.6)
        self.assertEqual(result['weights']['personal'],.2)
        with self.assertRaises(ValueError): self.feed.profile('c','u',[],role='unknown')

    def test_ranked_keeps_date_quality_and_weak_candidate_gates(self):
        with sqlite3.connect(self.feed.catalog) as db:
            db.execute("UPDATE family_assignments SET embedding_cosine=.85 WHERE article_id='1'")
            db.execute("UPDATE articles SET eligible_delivery=0 WHERE article_id='1'")
        result=self.feed.recommend('c','u',mode='ranked')
        self.assertNotIn('1',[a['article_id'] for a in result['items']])
        with sqlite3.connect(self.feed.catalog) as db:
            db.execute("UPDATE articles SET eligible_delivery=1,published_at='2099-01-01' WHERE article_id='1'")
        self.assertNotIn('1',[a['article_id'] for a in self.feed.recommend('c','v',mode='ranked')['items']])

    def test_sidecar_is_retrieval_evidence_not_verified_events(self):
        sidecar=self.feed.catalog.parent/'ranking.sqlite'
        with sqlite3.connect(sidecar) as db:
            db.executescript('''CREATE TABLE article_features(article_id TEXT,business_score REAL,general_business INT);
            INSERT INTO article_features VALUES('1',.9,0);
            CREATE TABLE article_objects(article_id TEXT,family_key TEXT,score REAL,origin TEXT,evidence TEXT);
            INSERT INTO article_objects VALUES('1','f',.9,'semantic_supported','Explicit topic evidence');
            CREATE TABLE company_profiles(source_record_id TEXT,operating_families TEXT);''')
        result=self.feed.recommend('c','sidecar',mode='ranked')
        article=next(a for a in result['items'] if a['article_id']=='1')
        self.assertEqual(article['matched_topics'],[])
        self.assertTrue(article['review_required'])
        self.assertEqual(article['matched_objects'][0]['origin'],'semantic_supported')
        self.assertFalse(article['matched_objects'][0]['specific_event_verified'])

    def test_industry_context_is_not_declared_specialization(self):
        with sqlite3.connect(self.feed.catalog.parent/'ranking.sqlite') as db:
            db.executescript('''CREATE TABLE article_features(article_id TEXT,business_score REAL,general_business INT);
            INSERT INTO article_features VALUES('2',.9,0);
            CREATE TABLE article_objects(article_id TEXT,family_key TEXT,score REAL,origin TEXT,evidence TEXT);
            CREATE TABLE company_profiles(source_record_id TEXT,operating_families TEXT);
            CREATE TABLE article_industries(article_id TEXT,sector_id TEXT,score REAL,evidence TEXT);
            INSERT INTO article_industries VALUES('2','agro',.9,'Agriculture headline');
            CREATE TABLE company_industries(okved TEXT,sector_id TEXT,relation TEXT,reason TEXT);
            INSERT INTO company_industries VALUES('01','agro','industry_context','Sector context');''')
        result=self.feed.recommend('c','context',mode='ranked')
        article=next(a for a in result['items'] if a['article_id']=='2')
        self.assertEqual(article['match_level'],'industry_context')
        self.assertEqual(article['matched_topics'],[])
        self.assertEqual(article['matched_objects'],[])
        self.assertEqual(article['matched_industries'][0]['relation'],'industry_context')
        self.assertAlmostEqual(article['components']['company'],.675)
        with sqlite3.connect(self.feed.catalog.parent/'ranking.sqlite') as db:
            db.execute("INSERT INTO article_industries VALUES('0','agro',.9,'Another agriculture article')")
        self.feed.event('c','learning','2','like','industry-positive')
        learned=self.feed.recommend('c','learning',mode='ranked')
        next_article=next(a for a in learned['items'] if a['article_id']=='0')
        self.assertGreater(next_article['components']['personal'],0)
        self.assertNotIn('2',[a['article_id'] for a in learned['items']])

