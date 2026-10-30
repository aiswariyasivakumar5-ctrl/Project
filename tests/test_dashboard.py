import http.client
import json
import re
import threading
import unittest
from unittest.mock import patch

from sentinel.dashboard import DemoSession, SCENARIOS, create_dashboard


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = DemoSession().__enter__()
        cls.server = create_dashboard(cls.demo, port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.demo.__exit__(None, None, None)

    def setUp(self):
        self.demo.reset()
        _, body, _ = self.request('GET', '/')
        self.token = re.search(r'name="demo-token" content="([^"]+)"', body.decode()).group(1)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def post(self, path, body, **extra):
        return self.request('POST', path, json.dumps(body),
            {'Origin': self.origin, 'X-Demo-Token': self.token, 'Content-Type': 'application/json', **extra})

    def test_assets_and_state_are_local_and_not_cached(self):
        for path in ('/', '/app.js', '/style.css', '/api/state'):
            status, body, headers = self.request('GET', path)
            self.assertEqual(status, 200)
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
            self.assertTrue(body)
        self.assertEqual(self.request('GET', '/../../pyproject.toml')[0], 404)
        self.assertEqual(self.request('GET', '/', headers={'Host': 'evil.example'})[0], 403)

    def test_cross_origin_and_missing_token_cannot_run(self):
        for headers in ({}, {'Origin': self.origin}, {'Origin': 'https://evil.example', 'X-Demo-Token': self.token}):
            # Authorization rejects headers before reading the body. Avoid
            # unread bytes causing a Windows TCP reset; require an actual 403,
            # not a swallowed socket error or a body-validation 400.
            self.assertEqual(self.request('POST', '/api/run', headers=headers)[0], 403)
        self.assertEqual(self.demo.total, 0)

    def test_only_fixed_scenarios_and_valid_bodies_are_accepted(self):
        for body in ({'scenario': 'shell'}, {'scenario': ['normal']}, {'scenario': 'normal', 'upstream': 'https://example.com'}, []):
            self.assertEqual(self.post('/api/run', body)[0], 400)
        self.assertEqual(self.post('/api/reset', {'extra': True})[0], 400)
        self.assertEqual(self.demo.total, 0)

    def test_live_mismatch_is_not_forwarded_and_reset_restores_learning(self):
        before = self.demo.live.learning_state()
        status, body, _ = self.post('/api/run', {'scenario': 'intent_mismatch'})
        self.assertEqual(status, 200)
        row = json.loads(body)['events'][0]
        self.assertEqual(row['tool'], 'simulated_delete')
        self.assertFalse(row['forwarded'])
        self.assertEqual(row['model_updates'], 0)
        self.assertEqual(self.post('/api/reset', {})[0], 200)
        self.assertEqual(self.demo.total, 0)
        self.assertEqual(self.demo.live.learning_state(), before)

    def test_all_scenarios_return_real_gateway_evidence(self):
        for scenario in SCENARIOS:
            self.demo.reset()
            status, body, _ = self.post('/api/run', {'scenario': scenario})
            self.assertEqual(status, 200, body)
            data = json.loads(body)
            self.assertGreater(data['total'], 0)
            self.assertEqual(data['total'], len(data['events']))
            for row in data['events']:
                self.assertIn('decision', row)
                self.assertIsInstance(row['forwarded'], bool)
                self.assertGreaterEqual(row['latency_ms'], 0)
                self.assertIn('novelty', row)

    def test_busy_requests_do_not_mutate_state(self):
        with self.demo.lock:
            self.assertEqual(self.post('/api/run', {'scenario': 'normal'})[0], 409)
            self.assertEqual(self.request('GET', '/api/state')[0], 409)
        self.assertEqual(self.demo.total, 0)

    def test_partial_failure_keeps_evidence_without_retry(self):
        original = self.demo.live.execute
        count = 0
        def fail_second(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise TimeoutError('fixture')
            return original(*args, **kwargs)
        with patch.object(self.demo.live, 'execute', side_effect=fail_second), patch('sentinel.dashboard.traceback.print_exc'):
            status, _, _ = self.post('/api/run', {'scenario': 'normal'})
        self.assertEqual(status, 502)
        self.assertEqual(count, 2)
        self.assertEqual(self.demo.total, 1)
        self.assertEqual(len(self.demo.events), 1)


if __name__ == '__main__':
    unittest.main()
