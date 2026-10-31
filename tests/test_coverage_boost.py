import hashlib
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import urllib.request
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

from sentinel.audit_log import AuditLog, verify_audit_log
from sentinel.gateway import (
    GatewayAudit,
    GatewayConfig,
    PendingAction,
    SentinelGateway,
    create_gateway_server,
    serve_gateway,
)
from sentinel.http_limits import BoundedHTTPServer
from sentinel.jsonrpc import JsonRpcError
from sentinel.models import Action
from sentinel.policy import PreExecutionPolicy


class PolicyCoverageTests(unittest.TestCase):
    def test_invalid_tool_rule_types(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "policy.json"
            # Non-dict rule
            p.write_text(json.dumps({"tools": {"tool1": "not-a-dict"}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                PreExecutionPolicy(p)

            # Empty tool name
            p.write_text(json.dumps({"tools": {"": {}}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                PreExecutionPolicy(p)

    def test_nested_list_argument_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "policy.json"
            p.write_text(
                json.dumps(
                    {
                        "tools": {
                            "batch_op": {
                                "risk_class": "read",
                                "input_schema": {
                                    "type": "object",
                                    "properties": {
                                        "records": {"type": "array"}
                                    },
                                },
                                "forbidden_paths": ["records[0].secret"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            policy = PreExecutionPolicy(p)
            reasons, _ = policy.evaluate(
                "batch_op",
                {"records": [{"secret": "classified"}, {"public": "ok"}]},
                "client-1",
            )
            self.assertIn("policy forbidden argument path", reasons)


class AuditLogCoverageTests(unittest.TestCase):
    def test_corrupted_audit_log_on_load(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "audit.jsonl"
            p.write_text("corrupted json content\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid hash chain"):
                AuditLog(p)

    def test_rotation_and_tampering(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "audit.jsonl"
            log = AuditLog(p, max_bytes=1024)
            # Write enough records to trigger rotation
            for i in range(15):
                log.append({"event": "test", "index": i, "padding": "x" * 100})

            # Check that rotated file exists
            rotated = p.with_name(p.name + ".1")
            self.assertTrue(rotated.exists())
            valid, _ = verify_audit_log(p)
            self.assertTrue(valid)
            valid_rot, _ = verify_audit_log(rotated)
            self.assertTrue(valid_rot)

            # Tamper with rotated file
            lines = rotated.read_text(encoding="utf-8").splitlines(keepends=True)
            if lines:
                corrupted_line = lines[0].replace('"test"', '"tampered"')
                rotated.write_text(corrupted_line + "".join(lines[1:]), encoding="utf-8")
                tampered_valid, msg = verify_audit_log(rotated)
                self.assertFalse(tampered_valid)
                self.assertIn("hash mismatch", msg)


class HttpLimitsCoverageTests(unittest.TestCase):
    def test_process_request_rejection_oserror_handling(self):
        mock_sock = MagicMock(spec=socket.socket)
        mock_sock.sendall.side_effect = OSError("network unreachable")

        class DummyHandler:
            pass

        server = BoundedHTTPServer(("127.0.0.1", 0), DummyHandler, max_connections=1)
        # Artificially exhaust slots
        server._slots.acquire()
        try:
            # When slots are exhausted, it should try sendall and catch OSError
            server.process_request(mock_sock, ("127.0.0.1", 12345))
            mock_sock.close.assert_called()
        finally:
            server._slots.release()
            server.server_close()


class GatewayCoverageTests(unittest.TestCase):
    def test_pending_action_non_json_payload_bytes(self):
        act = PendingAction(
            action_id="act-nonjson",
            trace_id="tr-1",
            session_id="s1",
            server_id="srv",
            tool_name="tool",
            arguments={},
            upstream_response=b"\x80\x02binary\xff",
            created_at=time.time(),
            expires_at=time.time() + 60,
        )
        d = act.to_dict(include_payload=True)
        self.assertIn("response_bytes", d)
        self.assertEqual(d["response_bytes"], len(b"\x80\x02binary\xff"))
        self.assertNotIn("response", d)

    def test_credentials_from_file_edge_cases(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "creds.json"

            # Nonexistent file
            with self.assertRaises(ValueError):
                SentinelGateway._credentials_from_file(Path(td) / "missing.json")

            # Non-dict
            p.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                SentinelGateway._credentials_from_file(p)

            # Empty dict
            p.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                SentinelGateway._credentials_from_file(p)

            # Invalid hash key
            p.write_text(json.dumps({"not-a-valid-sha256": "client-1"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                SentinelGateway._credentials_from_file(p)

            # Valid file and reload
            valid_hash = hashlib.sha256(b"secret").hexdigest()
            p.write_text(json.dumps({valid_hash: "client-1"}), encoding="utf-8")
            creds = SentinelGateway._credentials_from_file(p)
            self.assertEqual(creds[valid_hash], "client-1")

            cfg = GatewayConfig("http://127.0.0.1:8765", "srv", credentials_file=str(p))
            gw = SentinelGateway(cfg)
            self.assertIn(valid_hash, gw.client_credentials)

            # Reload with updated file
            new_hash = hashlib.sha256(b"secret2").hexdigest()
            p.write_text(json.dumps({new_hash: "client-2"}), encoding="utf-8")
            gw.reload_client_credentials()
            self.assertIn(new_hash, gw.client_credentials)

    def test_deny_action_validation_paths(self):
        gw = SentinelGateway(GatewayConfig("http://127.0.0.1:8765", "srv"))
        # 1. Nonexistent action
        with self.assertRaises(KeyError):
            gw.deny_action("act-missing")

        # 2. Expired action
        act = gw.create_pending_action(
            "tr-1", "s1", "safe_read", {}, b"{}", reasons=["risk"]
        )
        gw.pending_actions[act.action_id].expires_at = time.time() - 10
        with self.assertRaises(ValueError):
            gw.deny_action(act.action_id)

        # 3. Deny pending action with event notification
        act2 = gw.create_pending_action(
            "tr-2", "s1", "safe_read", {}, b"{}", reasons=["risk"]
        )
        evt = threading.Event()
        gw._approval_events[act2.action_id] = evt
        denied = gw.deny_action(act2.action_id, reviewer="admin", reason="custom deny")
        self.assertEqual(denied["status"], "denied")
        self.assertTrue(evt.is_set())

        # 4. Denying already resolved action
        with self.assertRaises(ValueError):
            gw.deny_action(act2.action_id)

    def test_preexecution_approval_denied_returns_isolate(self):
        with tempfile.TemporaryDirectory() as td:
            pol_file = Path(td) / "policy.json"
            pol_file.write_text(
                json.dumps(
                    {
                        "tools": {
                            "safe_read": {
                                "risk_class": "read",
                                "input_schema": {
                                    "type": "object",
                                    "additionalProperties": True,
                                },
                                "approval_required": True,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            gw = SentinelGateway(
                GatewayConfig(
                    "http://127.0.0.1:8765",
                    "srv",
                    policy_file=str(pol_file),
                    allowed_tools=("safe_read",),
                    confirm_timeout_seconds=5,
                )
            )
            created_evt = threading.Event()
            orig_create = gw.create_pending_action

            def intercept_create(*args, **kwargs):
                action = orig_create(*args, **kwargs)
                created_evt.set()
                return action

            gw.create_pending_action = intercept_create

            result_box = []

            def run_req():
                req = {
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "tools/call",
                    "params": {"name": "safe_read", "arguments": {}},
                }
                status, body, headers = gw.handle(json.dumps(req).encode(), {"x-sentinel-session": "s1"})
                result_box.append((status, body, headers))

            t = threading.Thread(target=run_req)
            t.start()
            self.assertTrue(created_evt.wait(5))
            pending = gw.get_pending_actions()
            self.assertTrue(pending)
            gw.deny_action(pending[0]["action_id"])
            t.join(5)

            self.assertEqual(len(result_box), 1)
            status, body, headers = result_box[0]
            self.assertEqual(status, 200)
            self.assertEqual(headers.get("X-Sentinel-Decision"), "isolate")
            resp = json.loads(body)
            self.assertEqual(resp["error"]["code"], -32043)
            self.assertEqual(resp["error"]["data"]["reason"], "pre-execution approval was not granted")

    def test_state_load_validation_errors(self):
        gw = SentinelGateway(GatewayConfig("http://127.0.0.1:8765", "srv"))
        with tempfile.TemporaryDirectory() as td:
            # 1. Missing file
            with self.assertRaises(FileNotFoundError):
                gw.load_state(Path(td) / "missing_state.json")

            # 2. Invalid JSON
            corrupt = Path(td) / "corrupt.json"
            corrupt.write_text("{bad-json", encoding="utf-8")
            with self.assertRaises(ValueError):
                gw.load_state(corrupt)

            # 3. Root not dict
            not_dict = Path(td) / "not_dict.json"
            not_dict.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                gw.load_state(not_dict)

            # 4. Empty MCP_SENTINEL_STATE_KEY env
            valid_state_path = Path(td) / "valid.json"
            gw.save_state(valid_state_path)
            with patch.dict(os.environ, {"MCP_SENTINEL_STATE_KEY": ""}):
                with self.assertRaises(ValueError):
                    gw.load_state(valid_state_path)

            # 5. Mismatched server_id in state
            state_data = json.loads(valid_state_path.read_text(encoding="utf-8"))
            state_data["server_id"] = "different-server"
            mismatch_path = Path(td) / "mismatch.json"
            mismatch_path.write_text(json.dumps(state_data), encoding="utf-8")
            with self.assertRaises(ValueError):
                gw.load_state(mismatch_path)

    def test_upstream_headers_configuration_and_missing_env(self):
        # 1. Missing environment variable raises JsonRpcError(-32056)
        cfg = GatewayConfig(
            "http://127.0.0.1:8765",
            "srv",
            upstream_headers=(("X-API-Key", "NONEXISTENT_ENV_TOKEN_XYZ"),),
        )
        gw = SentinelGateway(cfg)
        with self.assertRaises(JsonRpcError) as raised:
            gw._forward_with_budget({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        self.assertEqual(raised.exception.code, -32056)

        # 2. Present environment variable is included in connection headers
        with patch.dict(os.environ, {"TEST_ENV_VAR_123": "secret-upstream-val"}):
            cfg2 = GatewayConfig(
                "http://127.0.0.1:8765",
                "srv",
                upstream_headers=(("X-Custom-Auth", "TEST_ENV_VAR_123"),),
            )
            gw2 = SentinelGateway(cfg2)
            # Mock HTTPConnection inside _forward_with_budget
            with patch("http.client.HTTPConnection") as MockConn:
                mock_inst = MagicMock()
                MockConn.return_value = mock_inst
                mock_resp = MagicMock()
                mock_resp.headers.get.return_value = "application/json"
                mock_resp.headers.get_all.return_value = []
                mock_resp.status = 200
                mock_resp.read.return_value = b'{"jsonrpc":"2.0","id":1,"result":{}}'
                mock_inst.getresponse.return_value = mock_resp

                status, body, _, _ = gw2._forward_with_budget(
                    {"jsonrpc": "2.0", "id": 1, "method": "ping"}
                )
                self.assertEqual(status, 200)
                # Verify request headers included X-Custom-Auth
                _, kwargs = mock_inst.request.call_args
                self.assertEqual(kwargs["headers"]["X-Custom-Auth"], "secret-upstream-val")

    def test_action_isolate_verdict_withholding(self):
        class MockIsolateVerdict:
            action = Action.ISOLATE
            trace_id = "trace-iso-1"
            reasons = ["severe anomaly detected"]
            challenge = None
            anomaly_score = 0.99
            uncertainty = 0.05
            components = {}
            trust_score = 0.1
            provenance = None

        gw = SentinelGateway(
            GatewayConfig("http://127.0.0.1:8765", "srv", allowed_tools=("safe_read",))
        )
        gw.in_process_forwarder = lambda p: (200, json.dumps({"jsonrpc": "2.0", "id": p["id"], "result": {}}).encode(), "application/json")
        req_body = json.dumps({"jsonrpc": "2.0", "id": 77, "method": "tools/call", "params": {"name": "safe_read", "arguments": {}}}).encode()
        with patch.object(gw.engine, "evaluate", return_value=MockIsolateVerdict()):
            status, body, headers = gw.handle(req_body, {"x-sentinel-intent": "test"})
            self.assertEqual(status, 200)
            self.assertEqual(headers.get("X-Sentinel-Decision"), "isolate")
            resp = json.loads(body)
            self.assertEqual(resp["error"]["data"]["decision"], "isolate")

    def test_http_endpoints_readyz_metrics_and_deny(self):
        cfg = GatewayConfig(
            "http://127.0.0.1:8765",
            "srv",
            auth_token="operator-secret-token",
            client_auth_token="client-secret-token-long-enough-32c",
            allowed_tools=("safe_read",),
        )
        server, gw = create_gateway_server(cfg, host="127.0.0.1", port=0)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        port = server.server_address[1]
        base_url = f"http://127.0.0.1:{port}"

        try:
            # 1. GET /readyz when baseline_loaded is False -> 503
            req = urllib.request.Request(f"{base_url}/readyz")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=3)
            self.assertEqual(ctx.exception.code, 503)

            # 2. GET /metrics without auth -> 401
            req_metrics_noauth = urllib.request.Request(f"{base_url}/metrics")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req_metrics_noauth, timeout=3)
            self.assertEqual(ctx.exception.code, 401)

            # 3. GET /metrics with auth -> 200
            req_metrics = urllib.request.Request(
                f"{base_url}/metrics",
                headers={"Authorization": "Bearer operator-secret-token"},
            )
            with urllib.request.urlopen(req_metrics, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                content = resp.read().decode("utf-8")
                self.assertIn("mcp_sentinel_requests_total", content)

            # 4. POST /v1/pending/{id}/deny via HTTP
            act = gw.create_pending_action("tr-http-1", "s1", "safe_read", {}, b"{}")
            deny_req = urllib.request.Request(
                f"{base_url}/v1/pending/{act.action_id}/deny",
                data=b"",
                headers={"Authorization": "Bearer operator-secret-token"},
                method="POST",
            )
            with urllib.request.urlopen(deny_req, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data["status"], "denied")

            # 5. Invalid control command on pending action -> 404
            bad_cmd_req = urllib.request.Request(
                f"{base_url}/v1/pending/{act.action_id}/invalid",
                data=b"",
                headers={"Authorization": "Bearer operator-secret-token"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(bad_cmd_req, timeout=3)
            self.assertEqual(ctx.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()

    def test_serve_gateway_validation_guards(self):
        # 1. Missing client credential
        with self.assertRaisesRegex(ValueError, "Refusing to start gateway without client authentication"):
            serve_gateway(GatewayConfig("http://127.0.0.1:8765", "srv"))

        # 2. Operator token < 32 chars
        with self.assertRaisesRegex(ValueError, "without a strong operator credential"):
            serve_gateway(
                GatewayConfig(
                    "http://127.0.0.1:8765",
                    "srv",
                    client_auth_token="long-client-token-that-is-32-chars-ok",
                    auth_token="short-operator-token",
                )
            )

        # 3. Missing state_file
        with self.assertRaisesRegex(ValueError, "without a trained --state-file baseline"):
            serve_gateway(
                GatewayConfig(
                    "http://127.0.0.1:8765",
                    "srv",
                    client_auth_token="long-client-token-that-is-32-chars-ok",
                    auth_token="long-operator-token-that-is-32-chars-ok",
                ),
                state_file=None,
            )

        # 4. State file does not exist
        with tempfile.TemporaryDirectory() as td:
            policy = Path(td) / "policy.json"
            policy.write_text(
                json.dumps(
                    {
                        "tools": {
                            "safe_read": {
                                "risk_class": "read",
                                "input_schema": {"type": "object", "additionalProperties": True},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(FileNotFoundError):
                serve_gateway(
                    GatewayConfig(
                        "http://127.0.0.1:8765",
                        "srv",
                        client_auth_token="long-client-token-that-is-32-chars-ok",
                        auth_token="long-operator-token-that-is-32-chars-ok",
                        policy_file=str(policy),
                    ),
                    state_file="definitely_nonexistent_state_file.json",
                )


    def test_additional_gateway_branches(self):
        # 1. reload_client_credentials with corrupted file logs error
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "creds.json"
            h = hashlib.sha256(b"init").hexdigest()
            p.write_text(json.dumps({h: "c1"}), encoding="utf-8")
            cfg = GatewayConfig("http://127.0.0.1:8765", "srv", credentials_file=str(p))
            gw = SentinelGateway(cfg)
            p.write_text("not json", encoding="utf-8")
            gw.reload_client_credentials()

            # 2. _persist_configured_state
            state_p = Path(td) / "state.json"
            gw.state_path = state_p
            gw._persist_configured_state()
            self.assertTrue(state_p.exists())

            # 3. audit_sink append
            audit_p = Path(td) / "audit.jsonl"
            cfg_audit = GatewayConfig("http://127.0.0.1:8765", "srv", audit_log_path=str(audit_p))
            gw_audit = SentinelGateway(cfg_audit)
            gw_audit._append_audit(
                GatewayAudit(time.time(), "s", "srv", "test", 1, None, "", None, 1.0, True, "forward")
            )
            self.assertTrue(audit_p.exists())

        # 4. _await_preexecution_approval timeout
        with tempfile.TemporaryDirectory() as td:
            pol = Path(td) / "pol.json"
            pol.write_text(
                json.dumps(
                    {
                        "tools": {
                            "safe_read": {
                                "risk_class": "read",
                                "input_schema": {
                                    "type": "object",
                                    "additionalProperties": True,
                                },
                                "approval_required": True,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            cfg_timeout = GatewayConfig(
                "http://127.0.0.1:8765", "srv",
                policy_file=str(pol),
                allowed_tools=("safe_read",),
                confirm_timeout_seconds=0.001
            )
            gw_to = SentinelGateway(cfg_timeout)
            status, body, headers = gw_to.handle(
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "safe_read", "arguments": {}}}).encode(),
                {"x-sentinel-session": "s"}
            )
            self.assertEqual(headers["X-Sentinel-Decision"], "isolate")

        # 5. Initialize with downstream session header
        gw5 = SentinelGateway(GatewayConfig("http://127.0.0.1:8765", "srv"))
        with self.assertRaises(JsonRpcError) as exc:
            gw5.handle(
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).encode(),
                {"mcp-session-id": "downstream-sess"}
            )
        self.assertEqual(exc.exception.code, -32600)

        # 6. Initialize with malformed protocol version
        with self.assertRaises(JsonRpcError) as exc:
            gw5.handle(
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).encode(),
                {"mcp-protocol-version": "invalid\x00header"}
            )
        self.assertEqual(exc.exception.code, -32600)

        # 7. Upstream response exceeds max_request_bytes
        gw7 = SentinelGateway(GatewayConfig("http://127.0.0.1:8765", "srv", allowed_tools=("safe_read",), max_request_bytes=200))
        gw7.in_process_forwarder = lambda p: (200, b"x" * 250, "application/json")
        with self.assertRaises(JsonRpcError) as exc:
            gw7.handle(
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "safe_read", "arguments": {}}}).encode(),
                {}
            )
        self.assertEqual(exc.exception.code, -32052)

        # 8. Malformed upstream tools/list and tools/call
        gw8 = SentinelGateway(GatewayConfig("http://127.0.0.1:8765", "srv"))
        gw8.in_process_forwarder = lambda p: (200, json.dumps({"jsonrpc": "2.0", "id": p["id"], "result": {"tools": "not-a-list"}}).encode(), "application/json")
        with self.assertRaises(JsonRpcError) as exc:
            gw8.handle(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode(), {})
        self.assertEqual(exc.exception.code, -32053)

        gw8.in_process_forwarder = lambda p: (200, json.dumps({"jsonrpc": "2.0", "id": p["id"], "result": "not-a-dict"}).encode(), "application/json")
        gw8.config.allowed_tools = ("safe_read",)
        with tempfile.TemporaryDirectory() as policy_dir:
            policy_path = Path(policy_dir) / "policy.json"
            policy_path.write_text(
                json.dumps(
                    {
                        "tools": {
                            "safe_read": {
                                "risk_class": "read",
                                "input_schema": {
                                    "type": "object",
                                    "additionalProperties": True,
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            gw8.policy = PreExecutionPolicy(policy_path)
            with self.assertRaises(JsonRpcError) as exc:
                gw8.handle(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "safe_read", "arguments": {}}}).encode(), {})
            self.assertEqual(exc.exception.code, -32053)

        # 9. operator and client credentials must be different
        with self.assertRaises(ValueError):
            GatewayConfig("http://127.0.0.1:8765", "srv", auth_token="same-token-32-chars-long-enough-ok", client_auth_token="same-token-32-chars-long-enough-ok")

    def test_state_validation_detailed_branches(self):
        gw = SentinelGateway(GatewayConfig("http://127.0.0.1:8765", "srv"))
        state = gw.export_state()

        # unsupported schema version
        bad_version = dict(state, schema_version=99)
        with self.assertRaisesRegex(ValueError, "unsupported schema version"):
            gw._validate_state(bad_version)

        # invalid engine sessions
        bad_sessions = dict(state, engine=dict(state["engine"], sessions=["dup", "dup"]))
        with self.assertRaisesRegex(ValueError, "engine.sessions"):
            gw._validate_state(bad_sessions)

        # invalid novelty
        bad_novelty = dict(state, novelty={"unknown": True})
        with self.assertRaisesRegex(ValueError, "novelty"):
            gw._validate_state(bad_novelty)

        # invalid tool_metadata
        bad_meta = dict(state, tool_metadata={"tool": "not-a-dict"})
        with self.assertRaisesRegex(ValueError, "tool_metadata"):
            gw._validate_state(bad_meta)

        # duplicate pending action ids
        bad_actions = dict(state, pending_actions=[
            {"action_id": "a1", "trace_id": "t1", "session_id": "s", "server_id": "srv", "tool_name": "t", "arguments": {}, "created_at": 1, "expires_at": 2, "status": "pending", "reasons": [], "reviewed_by": None, "reviewed_at": None, "containment": None, "upstream_response_b64": ""},
            {"action_id": "a1", "trace_id": "t1", "session_id": "s", "server_id": "srv", "tool_name": "t", "arguments": {}, "created_at": 1, "expires_at": 2, "status": "pending", "reasons": [], "reviewed_by": None, "reviewed_at": None, "containment": None, "upstream_response_b64": ""},
        ])
        with self.assertRaisesRegex(ValueError, "pending action IDs must be unique"):
            gw._validate_state(bad_actions)


if __name__ == "__main__":
    unittest.main()

