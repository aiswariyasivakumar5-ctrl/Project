import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error

from sentinel.engine import SentinelEngine, ServerProfile
from sentinel.gateway import GatewayConfig, SentinelGateway, create_gateway_server
from sentinel_research.mock_server import create_mock_server
from sentinel.models import Action, Interaction


class EnforcementFlowsTests(unittest.TestCase):
    def setUp(self):
        self.mock_server, self.mock_state = create_mock_server()
        self.mock_thread = threading.Thread(target=self.mock_server.serve_forever, daemon=True)
        self.mock_thread.start()
        upstream = f"http://127.0.0.1:{self.mock_server.server_address[1]}"
        self.auth_token = "secret-sentinel-bearer-token"
        self.client_token = "test-client-auth-token-0123456789abcdef"
        self.config = GatewayConfig(
            upstream_url=upstream,
            server_id="local-test-mcp",
            auth_token=self.auth_token,
            client_auth_token=self.client_token,
            confirm_timeout_seconds=2.0,
            timeout_seconds=2.0,
            allowed_tools=(
                "safe_read",
                "calculate",
                "export_data",
                "schema_mutation",
                "simulated_delete",
            ),
        )
        self.engine = SentinelEngine(warmup_events=5)
        self.gateway_server, self.gateway = create_gateway_server(self.config, self.engine, port=0)
        self.gateway_thread = threading.Thread(
            target=self.gateway_server.serve_forever, daemon=True
        )
        self.gateway_thread.start()
        self.url = f"http://127.0.0.1:{self.gateway_server.server_address[1]}"

    def tearDown(self):
        self.gateway_server.shutdown()
        self.mock_server.shutdown()
        self.gateway_server.server_close()
        self.mock_server.server_close()

    def rpc(self, method, params=None, request_id=1, intent="test operation", session="session-1"):
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        req = urllib.request.Request(
            self.url,
            json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.client_token}",
                "X-Sentinel-Intent": intent,
                "X-Sentinel-Session": session,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read()), dict(resp.headers)

    def test_confirm_flow_registers_pending_action_and_approves(self):
        # Programmatically trigger a confirm action
        pending = self.gateway.create_pending_action(
            trace_id="tr-test-1",
            session_id="s1",
            tool="safe_read",
            arguments={"record_id": "1"},
            upstream_response=json.dumps({"result": {"data": "secret_content"}}).encode("utf-8"),
            reasons=["high risk threshold"],
        )
        self.assertEqual(pending.status, "pending")
        self.assertIn(
            pending.action_id, [a["action_id"] for a in self.gateway.get_pending_actions()]
        )

        # Approve the action
        approved = self.gateway.approve_action(pending.action_id, reviewer="security-admin")
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["reviewed_by"], "security-admin")
        self.assertEqual(approved["response"]["result"]["data"], "secret_content")

        # Second approval attempt fails with conflict
        with self.assertRaises(ValueError):
            self.gateway.approve_action(pending.action_id)

    def test_confirm_flow_deny_and_purge_payload(self):
        pending = self.gateway.create_pending_action(
            trace_id="tr-test-2",
            session_id="s2",
            tool="calculate",
            arguments={"a": 1, "b": 2},
            upstream_response=json.dumps({"result": "3"}).encode("utf-8"),
            reasons=["untrusted sequence"],
        )
        denied = self.gateway.deny_action(
            pending.action_id, reviewer="security-admin", reason="blocked by policy"
        )
        self.assertEqual(denied["status"], "denied")
        self.assertNotIn("response", denied)
        self.assertIsNone(self.gateway.pending_actions[pending.action_id].upstream_response)

    def test_confirm_action_expires_after_timeout(self):
        pending = self.gateway.create_pending_action(
            trace_id="tr-test-3",
            session_id="s3",
            tool="safe_read",
            arguments={},
            upstream_response=b"{}",
        )
        # Fast-forward expiration
        self.gateway.pending_actions[pending.action_id].expires_at = time.time() - 1.0
        with self.assertRaises(ValueError):
            self.gateway.approve_action(pending.action_id)
        self.assertEqual(self.gateway.get_action(pending.action_id)["status"], "expired")

    def test_sandbox_containment_response(self):
        # Synthesize a sandbox response via handle directly
        class MockVerdict:
            action = Action.SANDBOX
            trace_id = "trace-sandbox-1"
            reasons = ["sandbox containment policy"]
            challenge = None
            anomaly_score = 0.8
            uncertainty = 0.1
            components = {}
            trust_score = 0.5
            provenance = None

        req_body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 99,
                "method": "tools/call",
                "params": {"name": "safe_read", "arguments": {}},
            }
        ).encode()
        self.gateway.in_process_forwarder = lambda payload: (
            200,
            json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": {"content": []}}).encode(),
            "application/json",
        )
        with patch.object(self.engine, "evaluate", return_value=MockVerdict()):
            status, body, headers = self.gateway.handle(
                req_body, {"x-sentinel-intent": "read", "x-sentinel-session": "s"}
            )
            self.assertEqual(status, 200)
            self.assertEqual(headers.get("X-Sentinel-Decision"), "contained-withheld")
            self.assertEqual(headers.get("X-Sentinel-Sandbox"), "true")
            self.assertEqual(headers.get("X-Sentinel-Sandbox-Containment"), "isolated")
            resp_data = json.loads(body)
            self.assertTrue(resp_data["error"]["data"]["sandbox_contained"])

    def test_mcp_requests_require_client_bearer_before_upstream_dispatch(self):
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 900,
                "method": "tools/call",
                "params": {"name": "safe_read", "arguments": {"record_id": "private"}},
            }
        ).encode()
        before = self.mock_state.tool_calls.get("safe_read", 0)
        for headers in (
            {"Content-Type": "application/json"},
            {"Content-Type": "application/json", "Authorization": "Bearer wrong-client-token"},
        ):
            req = urllib.request.Request(self.url, payload, headers=headers)
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(req, timeout=3)
            self.assertEqual(raised.exception.code, 401)
        self.assertEqual(self.mock_state.tool_calls.get("safe_read", 0), before)

    def test_local_gateway_rejects_untrusted_host_and_origin(self):
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 901,
                "method": "tools/call",
                "params": {"name": "safe_read", "arguments": {"record_id": "1"}},
            }
        ).encode()
        before = self.mock_state.tool_calls.get("safe_read", 0)
        bad_headers = (
            {
                "Authorization": f"Bearer {self.client_token}",
                "Host": f"attacker.invalid:{self.gateway_server.server_port}",
            },
            {"Authorization": f"Bearer {self.client_token}", "Origin": "http://attacker.invalid"},
        )
        for headers in bad_headers:
            req = urllib.request.Request(self.url, payload, headers=headers)
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(req, timeout=3)
            self.assertEqual(raised.exception.code, 403)
        self.assertEqual(self.mock_state.tool_calls.get("safe_read", 0), before)

    def test_bearer_authentication_audit_and_control_endpoints(self):
        # 1. Access without header fails closed with 401
        req_no_auth = urllib.request.Request(f"{self.url}/v1/audit")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_no_auth, timeout=3)
        self.assertEqual(ctx.exception.code, 401)

        # 2. Access with invalid token fails with 401
        req_bad_auth = urllib.request.Request(
            f"{self.url}/v1/audit", headers={"Authorization": "Bearer wrong-token"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_bad_auth, timeout=3)
        self.assertEqual(ctx.exception.code, 401)

        # 3. Access with valid bearer token succeeds
        req_valid = urllib.request.Request(
            f"{self.url}/v1/audit", headers={"Authorization": f"Bearer {self.auth_token}"}
        )
        with urllib.request.urlopen(req_valid, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            audit_records = json.loads(resp.read())
            self.assertIsInstance(audit_records, list)

        # 4. Pending actions endpoint with valid token
        req_pending = urllib.request.Request(
            f"{self.url}/v1/pending", headers={"Authorization": f"Bearer {self.auth_token}"}
        )
        with urllib.request.urlopen(req_pending, timeout=3) as resp:
            self.assertEqual(resp.status, 200)

        # 5. Gateway with auth_token=None fails closed by default
        unauth_config = GatewayConfig(
            upstream_url=self.config.upstream_url,
            server_id="srv-unauth",
            auth_token=None,
            client_auth_token=self.client_token,
            allowed_tools=self.config.allowed_tools,
        )
        server_unauth, _ = create_gateway_server(unauth_config, self.engine, port=0)
        t = threading.Thread(target=server_unauth.serve_forever, daemon=True)
        t.start()
        try:
            req_default = urllib.request.Request(
                f"http://127.0.0.1:{server_unauth.server_address[1]}/v1/audit"
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req_default, timeout=3)
            self.assertEqual(ctx.exception.code, 401)
        finally:
            server_unauth.shutdown()
            server_unauth.server_close()

    def test_state_persistence_save_and_load(self):
        # Configure some profiles in engine
        prof = self.engine._profile("server-a", 16)
        prof.trusted_count = 42
        prof.trust = 0.92
        self.gateway.tool_metadata = {"tool1": {"name": "tool1"}}
        self.gateway.capability_digest = "cap-digest-test"

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "gateway_state.json"
            self.gateway.save_state(state_file)
            self.assertTrue(state_file.exists())

            # Create fresh gateway and restore
            new_engine = SentinelEngine()
            new_gateway = SentinelGateway(self.config, new_engine)
            self.assertNotIn("server-a", new_engine.profiles)

            new_gateway.load_state(state_file)
            self.assertIn("server-a", new_engine.profiles)
            self.assertEqual(new_engine.profiles["server-a"].trusted_count, 42)
            self.assertEqual(new_engine.profiles["server-a"].trust, 0.92)
            self.assertEqual(new_gateway.capability_digest, "cap-digest-test")


if __name__ == "__main__":
    unittest.main()
