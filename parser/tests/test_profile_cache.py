import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import fcntl

from news_collector.browser import Browser
from news_collector.profile_cache import ProfileBusy, ProfileSession, ProfileStore, chrome_paths, main


class ProfileCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.runtime = self.root / 'runtime'
        self.profiles = self.runtime / 'profiles'
        self.base = self.root / 'chrome-cache'
        self.store = ProfileStore(self.profiles, self.base)

    def put(self, name, data=b'important'):
        path = self.profiles / 'example' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_migration_prunes_cache_but_preserves_site_state_and_news(self):
        self.runtime.joinpath('news.sqlite3').write_bytes(b'news database')
        self.runtime.joinpath('raw').mkdir()
        self.runtime.joinpath('raw/news.html.gz').write_bytes(b'news DOM')
        keep = ['Local State', 'Default/Preferences', 'Default/Network/Cookies',
                'Default/Local Storage/leveldb/state', 'Default/IndexedDB/data',
                'Default/Service Worker/Database/state', 'CertificateRevocation/version/data']
        for name in keep:
            self.put(name)
        self.put('Default/Cache/Cache_Data/file', b'x'*500)
        self.put('optimization_guide_model_store/model.bin', b'x'*1000)
        self.put('WasmTtsEngine/engine.wasm', b'x'*500)
        with self.store.lease('example'):
            physical, http, removed = self.store.prepare('example')
        self.assertEqual(removed, 2000)
        self.assertTrue((self.profiles/'example').is_symlink())
        self.assertTrue(physical.is_relative_to(self.base))
        self.assertFalse(physical.is_relative_to(self.runtime))
        for name in keep:
            self.assertEqual((physical/name).read_bytes(), b'important')
        self.assertFalse((physical/'optimization_guide_model_store').exists())
        self.assertEqual((self.runtime/'news.sqlite3').read_bytes(), b'news database')
        self.assertEqual((self.runtime/'raw/news.html.gz').read_bytes(), b'news DOM')
        self.assertTrue(http.is_dir())

    def test_running_chrome_is_never_moved_or_cleaned(self):
        cache = self.put('Default/Cache/file')
        logical = self.profiles/'example'
        (logical/'SingletonLock').symlink_to('hostname-'+str(os.getpid()))
        result = self.store.sweep(['example'], grace_seconds=0)
        self.assertEqual(result['busy'], 1)
        self.assertEqual(result['removed_bytes'], 0)
        self.assertFalse(logical.is_symlink())
        self.assertTrue(cache.exists())

    def test_startup_process_without_singleton_lock_is_protected(self):
        cache = self.put('Default/Cache/file')
        with patch('news_collector.profile_cache.chrome_paths', return_value={self.profiles/'example'}):
            result = self.store.sweep(['example'], grace_seconds=0)
        self.assertEqual(result['busy'], 1)
        self.assertTrue(cache.exists())

    def test_recent_closed_profiles_are_left_for_later(self):
        cache = self.put('Default/Cache/file')
        result = self.store.sweep(['example'], grace_seconds=180)
        self.assertEqual(result['recent'], 1)
        self.assertTrue(cache.exists())
        result = self.store.sweep(['example'], grace_seconds=0)
        self.assertEqual(result['errors'], [])
        self.assertFalse(cache.exists())

    def test_shared_lease_protects_the_whole_browser_lifetime(self):
        self.put('Default/Network/Cookies')
        with self.store.lease('example'):
            with self.assertRaises(ProfileBusy):
                with self.store.lease('example'):
                    self.fail('Second lease acquired')
            self.assertEqual(self.store.sweep(['example'], 0)['busy'], 1)
        with self.store.lease('example'):
            pass

    def test_foreign_links_and_nested_links_cannot_delete_external_files(self):
        outside = self.root/'outside'
        outside.mkdir()
        important = outside/'Cache/file'
        important.parent.mkdir()
        important.write_bytes(b'keep me')
        logical = self.profiles/'example'
        logical.symlink_to(outside, target_is_directory=True)
        result = self.store.sweep(['example'], 0)
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(important.read_bytes(), b'keep me')
        logical.unlink()
        logical.mkdir()
        (logical/'Default').symlink_to(outside, target_is_directory=True)
        result = self.store.sweep(['example'], 0)
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(important.read_bytes(), b'keep me')

    def test_leaf_cache_symlink_is_unlinked_without_following(self):
        outside = self.root/'outside'
        outside.mkdir()
        (outside/'keep').write_bytes(b'important')
        logical = self.profiles/'example'
        logical.mkdir()
        (logical/'component_crx_cache').symlink_to(outside, target_is_directory=True)
        self.store.prepare('example')
        self.assertEqual((outside/'keep').read_bytes(), b'important')

    def test_collisions_preserve_both_profiles_for_review(self):
        self.put('Default/Network/Cookies', b'legacy cookies')
        _, physical, _ = self.store.paths('example')
        physical.mkdir()
        (physical/'Local State').write_bytes(b'other state')
        with self.assertRaises(ValueError):
            self.store.prepare('example')
        self.assertEqual((self.profiles/'example/Default/Network/Cookies').read_bytes(), b'legacy cookies')
        self.assertEqual((physical/'Local State').read_bytes(), b'other state')

    def test_prepared_path_works_for_legacy_mkdir_and_resolve(self):
        physical, _, _ = self.store.prepare('example')
        logical = self.profiles/'example'
        logical.mkdir(parents=True, exist_ok=True)
        self.assertEqual(logical.resolve(), physical)

    def test_browser_failure_releases_profile_lease(self):
        with patch.dict(os.environ, {'ALFA_BROWSER_CACHE':str(self.base)}), \
             patch('news_collector.profile_cache.chrome_paths', return_value=set()), \
             patch.object(Browser, '_open', side_effect=RuntimeError('driver unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'driver unavailable'):
                Browser(self.profiles/'example')
            with self.store.lease('example'):
                pass

    def test_browser_close_cleans_cache_after_quit_and_keeps_cookies(self):
        class Driver:
            closed = False
            def quit(self): self.closed = True
        driver = Driver()
        def start(browser, profile, http, *_):
            browser.driver = driver
            (profile/'Default/Network').mkdir(parents=True)
            (profile/'Default/Network/Cookies').write_bytes(b'cookie state')
            (profile/'optimization_guide_model_store').mkdir()
            (profile/'optimization_guide_model_store/model').write_bytes(b'model bytes')
            (http/'response').write_bytes(b'cached response')
        with patch.dict(os.environ, {'ALFA_BROWSER_CACHE':str(self.base)}), \
             patch('news_collector.profile_cache.chrome_paths', return_value=set()), \
             patch.object(Browser, '_open', start):
            browser = Browser(self.profiles/'example')
            self.assertEqual(self.store.sweep(['example'], 0)['busy'], 1)
            browser.close()
            self.assertTrue(driver.closed)
            logical = self.profiles/'example'
            self.assertEqual((logical/'Default/Network/Cookies').read_bytes(), b'cookie state')
            self.assertFalse((logical/'optimization_guide_model_store').exists())
            self.assertFalse(self.store.paths('example')[2].exists())

    def test_cache_cannot_be_created_in_dataset_and_ownership_is_checked(self):
        with self.assertRaises(ValueError):
            ProfileStore(self.profiles, self.runtime/'cache')
        marker = self.store.root/'ownership.json'
        marker.write_text(json.dumps({'kind':'foreign'}))
        with self.assertRaises(ValueError):
            ProfileStore(self.profiles, self.base)

    def test_process_parser_handles_spaces_in_paths(self):
        output = '/Applications/Google Chrome --user-data-dir=/tmp/profile with spaces --window-size=1440,1000\n'
        with patch('subprocess.check_output', return_value=output):
            self.assertEqual(chrome_paths(), {Path('/tmp/profile with spaces').resolve()})

    def test_watcher_finishes_with_final_cleanup_and_retains_total(self):
        cache = self.put('Default/Cache/file', b'temporary')
        self.put('Default/Network/Cookies', b'site state')
        config = self.root/'sources.json'
        config.write_text(json.dumps({'sources':[{'id':'example','enabled':True}]}))
        (self.store.root/'maintenance.json').write_text(json.dumps({'collector_pid':2147483647,'removed_bytes_total':100}))
        argv = ['profile_cache','--runtime',str(self.runtime),'--config',str(config),
                '--watch-pid','2147483647','--grace-seconds','3600']
        with patch.dict(os.environ, {'ALFA_BROWSER_CACHE':str(self.base)}), \
             patch('news_collector.profile_cache.chrome_paths', return_value=set()), \
             patch('news_collector.profile_cache.alive', return_value=False), \
             patch('sys.argv', argv), patch('builtins.print'):
            main()
        report = json.loads((self.store.root/'maintenance.json').read_text())
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['removed_bytes_total'], 109)
        self.assertFalse(cache.exists())
        self.assertEqual((self.profiles/'example/Default/Network/Cookies').read_bytes(), b'site state')

    def test_second_maintenance_process_cannot_run_for_same_namespace(self):
        with (self.store.root/'maintenance.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.dict(os.environ, {'ALFA_BROWSER_CACHE':str(self.base)}), \
                 patch('sys.argv', ['profile_cache','--runtime',str(self.runtime)]), \
                 patch('sys.stderr'):
                with self.assertRaises(SystemExit) as stopped:
                    main()
                self.assertEqual(stopped.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
