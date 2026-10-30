import json
import threading
import unittest
import urllib.error
import urllib.request

from sentinel.gateway import GatewayConfig, create_gateway_server


class GatewayOperatorHttpTests(unittest.TestCase):
    operator_token = "operator-token-that-is-long-enough-for-tests-123"
    client_token = "client-token-that-is-long-enough-for-tests-123456"

    def setUp(self):
        self.server, self.gateway = create_gateway_server(
            GatewayConfig(
                "http://127.0.0.1:1",
                "operator-http-test",
                auth_token=self.operator_token,
                client_auth_token=self.client_token,
            ),
            port=0,
        )
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=5)

    def request(self, method, path, *, token=None, headers=None):
        request_headers = dict(headers or {})
        if token is not None:
            request_headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            self.url + path,
            data=b"" if method == "POST" else None,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as response:
            return response.code, response.read(), dict(response.headers)

    def add_action(self):
        return self.gateway.create_pending_action(
            "trace", "operator-test", "safe_read", {"record_id": "1"}, b"{}"
        )

    def test_health_readiness_metrics_and_operator_auth_routes(self):
        for path in ("/livez", "/health"):
            status, body, _ = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), {"status": "ok"})

        status, body, _ = self.request("GET", "/readyz")
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body)["status"], "not_ready")

        for path in ("/metrics", "/v1/audit", "/v1/pending"):
            status, _, headers = self.request("GET", path)
            self.assertEqual(status, 401)
            self.assertEqual(headers.get("Content-Type"), "application/json")

        status, metrics, _ = self.request("GET", "/metrics", token=self.operator_token)
        self.assertEqual(status, 200)
        self.assertIn(b"mcp_sentinel_pending_actions", metrics)
        status, audit, _ = self.request("GET", "/v1/audit", token=self.operator_token)
        self.assertEqual(status, 200)
        self.assertIsInstance(json.loads(audit), list)
        status, pending, _ = self.request("GET", "/v1/pending", token=self.operator_token)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(pending), [])
        self.assertEqual(self.request("GET", "/unknown")[0], 404)

    def test_pending_get_approve_deny_conflict_and_invalid_control_paths(self):
        pending = self.add_action()
        status, body, _ = self.request(
            "GET", f"/v1/pending/{pending.action_id}", token=self.operator_token
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["action_id"], pending.action_id)
        self.assertEqual(
            self.request("GET", "/v1/pending/missing", token=self.operator_token)[0], 404
        )

        status, body, _ = self.request(
            "POST", f"/v1/pending/{pending.action_id}/approve", token=self.operator_token
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "approved")
        status, body, _ = self.request(
            "POST", f"/v1/pending/{pending.action_id}/approve", token=self.operator_token
        )
        self.assertEqual(status, 409)
        self.assertIn(b"already resolved", body)
        self.assertEqual(
            self.request("POST", "/v1/pending/missing/approve", token=self.operator_token)[0],
            404,
        )
        self.assertEqual(
            self.request("POST", "/v1/pending/id/unknown", token=self.operator_token)[0], 404
        )

        denied = self.add_action()
        status, body, _ = self.request(
            "POST", f"/v1/pending/{denied.action_id}/deny", token=self.operator_token
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "denied")

    def test_untrusted_host_and_origin_are_rejected(self):
        status, body, _ = self.request("GET", "/livez", headers={"Host": "evil.example"})
        self.assertEqual(status, 403)
        self.assertIn(b"Untrusted Host or Origin", body)

        status, _, _ = self.request("GET", "/livez", headers={"Origin": "https://evil.example"})
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
