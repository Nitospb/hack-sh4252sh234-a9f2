import sqlite3
import unittest
import test_engine
import catalog


class CatalogStateTests(unittest.TestCase):
    def setUp(self):
        test_engine.FeedTests.setUp(self)
        with sqlite3.connect(self.feed.catalog) as db:
            db.execute("ALTER TABLE articles ADD COLUMN kind TEXT DEFAULT 'news'")
            db.execute("ALTER TABLE articles ADD COLUMN text TEXT DEFAULT 'Original source text'")

    def tearDown(self):
        test_engine.FeedTests.tearDown(self)

    def test_default_role_is_not_an_inferred_job(self):
        state=catalog.profile_state(self.feed,'c','u')
        self.assertEqual(state['role'],'general')
        self.assertEqual(state['stats'],dict(viewed=0,saved=0,liked=0))

    def test_saved_is_persistent_and_respects_latest_toggle(self):
        self.feed.event('c','u','0','save','save-1')
        self.assertEqual(catalog.saved(self.feed,'c','u')['total'],1)
        self.assertEqual(catalog.saved(self.feed,'c','other')['total'],0)
        self.feed.event('c','u','0','unsave','unsave-1')
        self.assertEqual(catalog.saved(self.feed,'c','u')['total'],0)
        self.assertFalse(catalog.profile_state(self.feed,'c','u')['article_states']['0']['saved'])

    def test_views_and_likes_are_separate_and_company_scoped(self):
        self.feed.event('c','u','0','view','v1')
        self.feed.event('c','u','0','open','o1')
        state=catalog.profile_state(self.feed,'c','u')
        self.assertEqual(state['stats']['viewed'],1)
        self.assertEqual(state['stats']['liked'],0)
        self.assertEqual(catalog.profile_state(self.feed,'another','u')['stats']['viewed'],0)

    def test_selected_role_and_topics_are_read_back(self):
        self.feed.profile('c','u',['t'],role='accountant')
        state=catalog.profile_state(self.feed,'c','u')
        self.assertEqual(state['role'],'accountant')
        self.assertEqual(state['topic_ids'],['t'])
