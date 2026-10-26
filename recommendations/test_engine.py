import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path
from engine import Feed

class FeedTests(unittest.TestCase):
    def setUp(self):
        clock=patch('engine.time.time',return_value=datetime(2026,10,26,tzinfo=timezone.utc).timestamp())
        clock.start();self.addCleanup(clock.stop)
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        catalog = root/'catalog.sqlite'
        with sqlite3.connect(catalog) as db:
            db.executescript('''CREATE TABLE companies(company_id TEXT,source_record_id TEXT,okved TEXT);
            INSERT INTO companies VALUES('c','r','01');
            CREATE TABLE company_mapping(okved TEXT,topic_id TEXT,relation TEXT);
            INSERT INTO company_mapping VALUES('01','t','declared_activity');
            CREATE TABLE topics(topic_id TEXT,name TEXT);
            INSERT INTO topics VALUES('t','Налоги');
            CREATE TABLE assignments(article_id TEXT,topic_id TEXT);
            CREATE TABLE articles(article_id TEXT,title TEXT,url TEXT,source TEXT,published_at TEXT,
            eligible_delivery INT,text_hash TEXT,content_hash TEXT);''')
            for i,title in enumerate(['Налоговые изменения','Новые технологии производства','Экспорт зерновых']):
                db.execute('INSERT INTO articles VALUES(?,?,?,?,?,1,?,?)',(str(i),title,'url','s','2026-10-20T12:00:00+00:00',str(i),str(i)))
                db.execute('INSERT INTO assignments VALUES(?,?)',(str(i),'t'))
        self.feed = Feed(catalog,root/'state.sqlite',embeddings=False)
        # Topic-only equality is too coarse for duplicate blocking: use title overlap in this fixture.
        self.feed.similarity = lambda a,b: 0.

    def tearDown(self):
        self.temp.cleanup()

    def test_delivery_retry_and_new_page(self):
        a = self.feed.recommend('c','u',limit=1,request_id='req')
        self.assertEqual(a,self.feed.recommend('c','u',limit=1,request_id='req'))
        b = self.feed.recommend('c','u',limit=3)
        self.assertNotIn(a['items'][0]['article_id'],[x['article_id'] for x in b['items']])
        with self.assertRaises(ValueError):
            self.feed.recommend('c','other',request_id='req')

    def test_feedback_idempotency_and_isolation(self):
        self.assertTrue(self.feed.event('c','u','0','hide','e')['recorded'])
        self.assertFalse(self.feed.event('c','u','0','hide','e')['recorded'])
        with self.assertRaises(ValueError):
            self.feed.event('c','u','1','hide','e')
        self.assertNotIn('0',[x['article_id'] for x in self.feed.recommend('c','u')['items']])
        self.assertIn('0',[x['article_id'] for x in self.feed.recommend('c','v')['items']])

    def test_future_quality_and_duplicate_gates(self):
        with sqlite3.connect(self.feed.catalog) as db:
            db.execute("UPDATE articles SET published_at='2099-01-01' WHERE article_id='0'")
            db.execute("UPDATE articles SET eligible_delivery=0 WHERE article_id='1'")
        result = self.feed.recommend('c','u')
        self.assertEqual([x['article_id'] for x in result['items']],['2'])
        self.assertEqual(result['shortfall'],19)

    def test_profile_validation(self):
        self.feed.profile('c','u',['t'])
        with self.assertRaises(ValueError):
            self.feed.profile('c','u',['unknown'])

if __name__=='__main__': unittest.main()

class ToggleTests(FeedTests):
    def test_hide_undo_restores_article_without_inventing_view(self):
        self.feed.event('c','u','0','hide','h')
        self.feed.event('c','u','0','unhide','uh')
        result=self.feed.recommend('c','u')
        self.assertIn('0',[a['article_id'] for a in result['items']])
        with self.feed.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM events WHERE kind='view'").fetchone()[0],0)

    def test_feedback_changes_future_topic_score_and_is_isolated(self):
        baseline=self.feed.recommend('c','baseline',limit=3)
        base=next(a for a in baseline['items'] if a['article_id']=='2')['components']['personal']
        self.feed.event('c','engaged','0','like','positive')
        updated=self.feed.recommend('c','engaged',limit=3)
        target=next(a for a in updated['items'] if a['article_id']=='2')
        self.assertGreater(target['components']['personal'],base)
        self.assertNotIn('0',[a['article_id'] for a in updated['items']])

    def test_it_role_does_not_match_country_suffix(self):
        with sqlite3.connect(self.feed.catalog) as db:
            db.execute("UPDATE topics SET name='Общий рынок'")
            db.execute("UPDATE articles SET title='России нужен новый рынок' WHERE article_id='2'")
        r=self.feed.recommend('c','role-boundary',role='it')
        article=next(a for a in r['items'] if a['article_id']=='2')
        self.assertEqual(article['components']['personal'],0)

class FeedSettingsTests(FeedTests):
    def test_weights_change_ranking_and_preserve_existing_callers(self):
        self.feed.profile('c','u',[],role='general',weights={'company':0,'general':0,'popular':0,'personal':1},global_topic_ids=['technology'])
        result=self.feed.recommend('c','u',source_record_id='r',request_id='settings',mode='ranked')
        self.assertEqual(result['items'][0]['article_id'],'1')
        self.assertEqual(result['weights']['personal'],1)
        self.assertEqual(result,self.feed.recommend('c','u',source_record_id='r',request_id='settings',mode='ranked'))
        self.feed.profile('c','u',['t'],role='accountant')
        self.assertEqual(self.feed.feed_settings('c','u')['global_topic_ids'],['technology'])
        self.assertEqual(self.feed.feed_settings('c','u')['weights']['personal'],1)
        self.assertEqual(self.feed.feed_settings('c','other')['weights']['company'],.6)
        self.assertEqual(self.feed.feed_settings('other','u')['global_topic_ids'],[])

    def test_invalid_settings_are_atomic(self):
        bad=[{'company':1},dict(company=.6,general=.1,popular=.1,personal=.3),dict(company=float('nan'),general=0,popular=0,personal=1),dict(company=-.1,general=.1,popular=0,personal=1)]
        self.feed.profile('c','u',[],role='treasurer')
        for weights in bad:
            with self.assertRaises(ValueError):self.feed.profile('c','u',[],role='it',weights=weights)
        with self.assertRaises(ValueError):self.feed.profile('c','u',[],global_topic_ids=['unknown'])
        with self.feed.connect() as db:self.assertEqual(db.execute("SELECT role FROM profiles WHERE company='c' AND user='u'").fetchone()[0],'treasurer')
