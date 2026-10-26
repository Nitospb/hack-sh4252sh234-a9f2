import unittest

from service.openapi import openapi


class OpenApiTests(unittest.TestCase):
    def test_contract_covers_every_bff_endpoint_and_methods(self):
        paths = openapi()['paths']
        expected = {
            'health':'get', 'companies':'get', 'company':'get', 'feed':'get',
            'article':'get', 'news':'get', 'insight':'get post',
            'profile':'get post', 'saved':'get', 'events':'post',
            'context':'get post', 'analysis':'post', 'chat':'post',
            'runs':'get', 'run':'get', 'review':'post', 'metrics':'get',
            'bank-sources':'get', 'bank-file':'get', 'scenario':'post',
            'scenarios':'get',
        }
        self.assertEqual({path.lstrip('/'): set(methods) for path, methods in paths.items()},
                         {path: set(methods.split()) for path, methods in expected.items()})
        for path, operations in paths.items():
            for method, operation in operations.items():
                expected_status = '202' if method == 'post' and path in ('/analysis', '/chat', '/insight') else '200'
                self.assertIn(expected_status, operation['responses'])
                if method == 'post':
                    self.assertIn('company_id', operation['requestBody']['content']['application/json']['schema']['required'])

    def test_contract_is_not_mutable_by_callers(self):
        first = openapi()
        first['paths'].clear()
        self.assertIn('/health', openapi()['paths'])


if __name__ == '__main__':
    unittest.main()
