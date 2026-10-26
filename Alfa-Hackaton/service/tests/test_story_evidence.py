from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from recommendations.engine import Feed
from recommendations import catalog
from service.seed import create


class StoryEvidenceTests(unittest.TestCase):
    def test_article_sources_preserve_versions_and_filter_future_excerpt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=create(root/'seed');feed=Feed(path,root/'state.sqlite',embeddings=False)
            with sqlite3.connect(path) as db:
                db.execute('UPDATE articles SET eligible_delivery=0 WHERE article_id="seed_article_2"')
                db.execute('UPDATE articles SET published_at=? WHERE article_id="seed_article_3"',((datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),))
            with sqlite3.connect(path.parent/'stories.sqlite') as db:
                db.executescript('CREATE TABLE stories(story_id TEXT,anchor_id TEXT,member_count INT,dedup_safe INT,distinct_hosts INT);CREATE TABLE members(article_id TEXT,story_id TEXT,content_hash TEXT,rule TEXT,cosine REAL);CREATE TABLE quantities(article_id TEXT,record TEXT);')
                db.execute('INSERT INTO stories VALUES("story","seed_article_0",5,0,5)')
                for i in range(5):
                    aid=f'seed_article_{i}';db.execute('INSERT INTO members VALUES(?,?,?,?,1)',(aid,'story','stale' if i==4 else aid,'candidate'))
                for i,value in [(0,'15'),(1,'16')]:db.execute('INSERT INTO quantities VALUES(?,?)',(f'seed_article_{i}',json.dumps({'value':value,'unit':'%','quote':'Дословная цитата'})))
            result=catalog.article(feed,'seed_article_0')['story']
            self.assertEqual([i['article_id'] for i in result['items']],['seed_article_0','seed_article_1'])
            self.assertEqual(result['member_count'],5)
            self.assertEqual(result['numeric_variants'][0]['status'],'needs_comparison')
            self.assertEqual(result['distinct_hosts'],1)

    def test_only_strict_groups_are_deduplicated_across_delivery_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=create(root/'seed');feed=Feed(path,root/'state.sqlite',embeddings=False)
            feed.similarity=lambda a,b:0.
            with sqlite3.connect(path.parent/'stories.sqlite') as db:
                db.executescript('CREATE TABLE stories(story_id TEXT,member_count INT,dedup_safe INT);CREATE TABLE members(article_id TEXT,story_id TEXT);')
                db.execute('INSERT INTO stories VALUES("same",2,1)')
                db.executemany('INSERT INTO members VALUES(?,"same")', [('seed_article_0',),('seed_article_1',)])
            first=feed.recommend('SEED_1','reader',limit=6)
            self.assertEqual(len([a for a in first['items'] if a.get('story_id')=='same']),1)
            second=feed.recommend('SEED_1','reader',limit=6)
            self.assertFalse(any(a.get('story_id')=='same' for a in second['items']))
            with sqlite3.connect(path.parent/'stories.sqlite') as db:db.execute('UPDATE stories SET dedup_safe=0')
            other=feed.recommend('SEED_1','another-reader',limit=6)
            self.assertEqual(len([a for a in other['items'] if a.get('story_id')=='same']),2)
