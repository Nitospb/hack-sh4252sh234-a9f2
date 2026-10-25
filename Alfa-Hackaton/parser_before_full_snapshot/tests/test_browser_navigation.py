import unittest
from unittest.mock import Mock
from selenium.common.exceptions import JavascriptException
from news_collector.browser import AccessBlocked, Browser, Page
from test_collector import SOURCE


class BrowserNavigationTests(unittest.TestCase):
    def browser(self):
        browser=object.__new__(Browser)
        browser.driver=Mock()
        browser.driver.current_url='https://news.example/economy'
        browser.driver.title='News'
        browser.driver.page_source='<article><h1>News</h1><p>Text</p></article>'
        browser.driver.get_log.return_value=[]
        return browser

    def test_site_url_polyfill_failure_falls_back_to_browser_navigation(self):
        browser=self.browser()
        def script(code,*_):
            if 'const clean=' in code:raise JavascriptException('searchParams.sort is not a function')
            return 'Article body' if code=='return document.body.innerText' else True
        browser.driver.execute_script.side_effect=script
        target='https://news.example/article/1'
        browser.driver.get.side_effect=lambda url:setattr(browser.driver,'current_url',url)
        result=browser.read(target,article=True)
        browser.driver.get.assert_called_once_with(target)
        self.assertEqual(result.url,target)

    def test_dynamic_listing_is_reread_and_late_access_challenge_is_rejected(self):
        browser=self.browser()
        browser.driver.execute_script.side_effect=lambda code:['https://news.example/article/1'] if 'querySelectorAll' in code else 'verify you are human'
        browser.driver.title='Just a moment'
        before=Page('https://news.example/economy','https://news.example/economy','Loading','<body>Loading</body>','Loading',200)
        with self.assertRaises(AccessBlocked):browser.wait_for_listing(before,SOURCE)
