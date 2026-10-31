import json
import threading
import unittest
import urllib.error
import urllib.request

from sentinel.gateway import GatewayConfig, create_gateway_server
from sentinel_research.mock_server import create_mock_server


class StreamableHttpGatewayTests(unittest.TestCase):
    token = "streamable-http-client-token-0123456789"

    def setUp(self):
        self.upstream, self.upstream_state = create_mock_server(
            streamable_http=True, require_sessions=True
        )
        self.upstream_thread = threading.Thread(target=self.upstream.serve_forever, daemon=True)
        self.upstream_thread.start()
        upstream_url = f"http://127.0.0.1:{self.upstream.server_address[1]}"
        self.server, self.gateway = create_gateway_server(
            GatewayConfig(
                upstream_url,
                "streamable-test",
                timeout_seconds=2,
                client_auth_token=self.token,
                allowed_tools=("safe_read",),
            ),
            port=0,
        )
        self.gateway_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.gateway_thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.upstream.shutdown()
        self.server.server_close()
        self.upstream.server_close()

    def rpc(self, method, request_id=None, session_id=None, params=None, protocol=None):
        payload = {"jsonrpc": "2.0", "method": method}
        if request_id is not None:
            payload["id"] = request_id
        if params is not None:
            payload["params"] = params
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "X-Sentinel-Session": "streamable-client",
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        if protocol:
            headers["MCP-Protocol-Version"] = protocol
        req = urllib.request.Request(self.url, json.dumps(payload).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as response:
            return response.code, response.read(), response.headers

    def test_sse_initialize_maps_session_and_reuses_it(self):
        status, body, headers = self.rpc(
            "initialize",
            1,
            params={
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["id"], 1)
        downstream_session = headers.get("Mcp-Session-Id")
        self.assertTrue(downstream_session)
        self.assertNotIn(downstream_session, self.upstream_state.upstream_sessions)

        status, body, _ = self.rpc("tools/list", 2, downstream_session, {})
        self.assertEqual(status, 200)
        self.assertIn("tools", json.loads(body)["result"])

        status, _, _ = self.rpc(
            "notifications/initialized", session_id=downstream_session, params={}
        )
        self.assertEqual(status, 202)

    def test_unknown_or_missing_required_session_is_rejected(self):
        _, _, headers = self.rpc(
            "initialize",
            1,
            params={
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        valid_session = headers.get("Mcp-Session-Id")
        self.assertTrue(valid_session)
        status, _, _ = self.rpc("tools/list", 3, "unknown-session", {})
        self.assertEqual(status, 404)
        status, body, _ = self.rpc("tools/list", 4, params={})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["error"]["code"], -32600)

    def test_gated_resource_method_is_unavailable_by_default(self):
        self.assertEqual(self.upstream_state.upstream_sessions, set())
        self.assertEqual(self.upstream_state.request_count, 0)
        _, _, headers = self.rpc(
            "initialize",
            1,
            params={
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        # initialize legitimately reaches upstream and creates a session.
        # Record that baseline so the gated resources/list request must add
        # neither a session nor an upstream request of its own.
        self.assertEqual(len(self.upstream_state.upstream_sessions), 1)
        self.assertEqual(self.upstream_state.request_count, 1)
        sessions_after_initialize = set(self.upstream_state.upstream_sessions)
        requests_after_initialize = self.upstream_state.request_count
        session = headers.get("Mcp-Session-Id")
        status, body, _ = self.rpc("resources/list", 5, session, {})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["error"]["code"], -32601)
        self.assertEqual(self.upstream_state.upstream_sessions, sessions_after_initialize)
        self.assertEqual(self.upstream_state.request_count, requests_after_initialize)


if __name__ == "__main__":
    unittest.main()
