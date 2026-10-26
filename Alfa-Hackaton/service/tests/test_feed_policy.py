import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'recommendations'))
from test_engine import FeedTests
from datetime import datetime,timezone
import sqlite3
import json

class ServingPolicyTests(FeedTests):
    def test_serve_time_cutoff_including_cached_delivery(self):
        self.feed.recommend('c','u',request_id='old')
        now=datetime(2026,12,26,tzinfo=timezone.utc).timestamp()
        self.assertEqual(self.feed.recommend('c','u',request_id='old',now=now)['items'],[])
    def test_request_id_cannot_change_scope_or_role(self):
        self.feed.recommend('c','u',request_id='r',role='director')
        with self.assertRaises(ValueError):self.feed.recommend('c','u',request_id='r',role='it')

    def test_resignation_is_not_a_financing_exposure(self):
        with sqlite3.connect(self.feed.catalog) as d:
            d.execute("UPDATE articles SET title='Советники призвали к отставке правительства' WHERE article_id='0'")
            d.execute("UPDATE topics SET name='Общий рынок'")
        with sqlite3.connect(self.feed.catalog.parent/'service-assets.sqlite') as d:
            d.execute('CREATE TABLE raw_profiles(record_id TEXT,facts TEXT)')
            d.execute('INSERT INTO raw_profiles VALUES(?,?)',('r',json.dumps({'CL_PRODUCT_LOA_MARK':'1.0'})))
        result=self.feed.recommend('c','u',role='finance')
        item=next(a for a in result['items'] if a['article_id']=='0')
        self.assertEqual(item['components']['personal'],0)
        self.assertNotIn('observed_profile',[r['kind'] for r in item['recommendation_reasons']])

    def test_implicit_role_cache_changes_after_profile_update(self):
        first=self.feed.recommend('c','u',request_id='profile-cache')
        self.feed.profile('c','u',['t'],role='finance')
        second=self.feed.recommend('c','u',request_id='profile-cache')
        self.assertNotEqual(first['role'],second['role'])
        self.assertEqual(second['role'],'finance')
