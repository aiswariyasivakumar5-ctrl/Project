import json
import threading
import time
import unittest
import urllib.request

from sentinel.engine import SentinelEngine
from sentinel.gateway import GatewayConfig, create_gateway_server
from sentinel_research.mock_server import create_mock_server


class GatewayIntegrationTests(unittest.TestCase):
    CLIENT_TOKEN = 'test-client-auth-token-0123456789abcdef'
    def setUp(self):
        self.mock_server, self.mock_state = create_mock_server()
        self.mock_thread = threading.Thread(target=self.mock_server.serve_forever, daemon=True)
        self.mock_thread.start()
        upstream = f"http://127.0.0.1:{self.mock_server.server_address[1]}"
        self.engine = SentinelEngine(warmup_events=8)
        self.gateway_server, self.gateway = create_gateway_server(
            GatewayConfig(upstream, "local-test-mcp", timeout_seconds=2,
                          allowed_tools=("safe_read", "calculate", "export_data", "schema_mutation", "simulated_delete"),
                          client_auth_token=self.CLIENT_TOKEN),
            self.engine, port=0
        )
        # Exercise real HTTP transport, but keep model input independent of
        # runner scheduling jitter. Audit latency still measures actual I/O.
        self.gateway.telemetry_latency_override_ms = 25.0
        self.gateway_thread = threading.Thread(target=self.gateway_server.serve_forever, daemon=True)
        self.gateway_thread.start()
        self.gateway_url = f"http://127.0.0.1:{self.gateway_server.server_address[1]}"
        self.rpc("initialize", {"protocolVersion": "2025-06-18"}, request_id=10)
        self.rpc("tools/list", request_id=11)

    def tearDown(self):
        self.gateway_server.shutdown()
        self.mock_server.shutdown()
        self.gateway_server.server_close()
        self.mock_server.server_close()

    def rpc(self, method, params=None, request_id=1, intent="test operation", session="integration"):
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        request = urllib.request.Request(
            self.gateway_url, json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.CLIENT_TOKEN}",
                     "X-Sentinel-Intent": intent,
                     "X-Sentinel-Session": session},
        )
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.loads(response.read()), dict(response.headers), (time.perf_counter() - started) * 1000

    def test_real_tool_call_traverses_gateway_and_generates_trace(self):
        before = self.mock_state.tool_calls.get("safe_read", 0)
        response, headers, _ = self.rpc(
            "tools/call", {"name": "safe_read", "arguments": {"record_id": "alpha"}},
            12, "Read record alpha", "normal-flow",
        )
        self.assertIn("result", response)
        self.assertEqual(self.mock_state.tool_calls.get("safe_read", 0), before + 1)
        audit = self.gateway.audit[-1]
        self.assertTrue(audit.forwarded)
        self.assertIsNotNone(audit.trace_id)
        self.assertNotIn("alpha", audit.parameter_fingerprint)
        self.assertEqual(headers.get("X-Sentinel-Trace"), audit.trace_id)

    def test_intent_mismatch_does_not_change_read_tool_policy(self):
        before = self.mock_state.tool_calls.get("simulated_delete", 0)
        response, _, _ = self.rpc(
            "tools/call", {"name": "simulated_delete", "arguments": {"record_id": "alpha"}},
            20, "Read record alpha", "blocked-flow",
        )
        self.assertIn("result", response)
        self.assertEqual(self.mock_state.tool_calls.get("simulated_delete", 0), before + 1)
        self.assertTrue(self.gateway.audit[-1].forwarded)
        self.assertEqual(self.gateway.audit[-1].risk_class, "read")
        self.assertFalse(self.gateway.audit[-1].response_withheld)

    def test_schema_mutation_is_detected_and_response_withheld(self):
        response, _, _ = self.rpc(
            "tools/call", {"name": "schema_mutation", "arguments": {}}, 30,
            "Read the schema", "schema-flow",
        )
        self.assertEqual(response["error"]["code"], -32042)
        audit = self.gateway.audit[-1]
        self.assertGreaterEqual(audit.causal_risk, 0.6)
        self.assertIn("policy-like instruction embedded in tool response", audit.reasons)

    def test_attestation_challenge_is_executed_against_server(self):
        for index in range(10):
            self.rpc("tools/call", {"name": "safe_read", "arguments": {"record_id": str(index)}},
                     300 + index, f"Read record {index}", "attestation-flow")
        self.assertGreaterEqual(self.engine.profiles["local-test-mcp"].trusted_count,
                                self.engine.warmup_events)
        self.rpc("tools/call", {"name": "schema_mutation", "arguments": {}}, 320,
                 "Read the schema", "attestation-flow")
        audit = self.gateway.audit[-1]
        self.assertIsNotNone(audit.challenge)
        self.assertTrue(audit.attestation_verified)

    def test_unexpected_parameters_elevate_behavioral_risk(self):
        for index in range(10):
            self.rpc("tools/call", {"name": "safe_read", "arguments": {"record_id": str(index)}},
                     400 + index, f"Read record {index}", "parameter-flow")
        self.rpc("tools/call", {"name": "safe_read", "arguments": {
            "record_id": "x" * 10000, "include_secret_tokens": True, "scope": "all"
        }}, 420, "Read record", "parameter-flow")
        self.assertGreaterEqual(self.gateway.audit[-1].anomaly_score, 0.4)

    def test_unseen_tool_transition_reaches_sequence_detector(self):
        for index in range(10):
            self.rpc("tools/call", {"name": "safe_read", "arguments": {"record_id": str(index)}},
                     500 + index, f"Read record {index}", "sequence-flow")
        self.rpc("tools/call", {"name": "calculate", "arguments": {"a": 2, "b": 3}},
                 520, "Calculate 2 plus 3", "sequence-flow")
        self.assertGreater(self.gateway.audit[-1].anomaly_score, 0.1)

    def test_capability_drift_reaches_existing_attestation_detector(self):
        for index in range(10):
            self.rpc("tools/call", {"name": "safe_read", "arguments": {"record_id": str(index)}},
                     100 + index, f"Read record {index}", "enrollment")
        self.mock_state.capability_version = 2
        self.rpc("tools/list", request_id=120)
        self.rpc("tools/call", {"name": "safe_read", "arguments": {"record_id": "drift"}},
                 121, "Read record drift", "drift")
        self.assertEqual(self.gateway.audit[-1].capability_risk, 1.0)

    def test_malformed_json_returns_parse_error(self):
        request = urllib.request.Request(self.gateway_url, b"{broken", method="POST",
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": f"Bearer {self.CLIENT_TOKEN}"})
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.loads(response.read())
        self.assertEqual(payload["error"]["code"], -32700)

    def test_unknown_method_is_rejected_without_forwarding(self):
        response, _, _ = self.rpc("resources/list", request_id=200)
        self.assertEqual(response["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
