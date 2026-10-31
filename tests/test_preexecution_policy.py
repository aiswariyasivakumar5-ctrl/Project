import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from sentinel.gateway import GatewayConfig, SentinelGateway
from sentinel.models import Action, Verdict
from sentinel.policy import PreExecutionPolicy


class PreExecutionPolicyTests(unittest.TestCase):
    def gateway(self, rule, *, tool="safe_read"):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "policy.json"
        rule = {
            "risk_class": "read",
            "input_schema": {
                "type": "object",
                "properties": {"record_id": {"type": "string"}, "a": {"type": "number"}, "b": {"type": "number"}},
            },
            **rule,
        }
        path.write_text(json.dumps({"tools": {tool: rule}}), encoding="utf-8")
        gateway = SentinelGateway(
            GatewayConfig(
                "http://127.0.0.1:8765",
                "policy-test",
                allowed_tools=(tool,),
                policy_file=str(path),
                confirm_timeout_seconds=2,
            )
        )
        gateway._test_policy_directory = directory
        return gateway

    def call(self, gateway):
        return gateway.handle(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "safe_read", "arguments": {"record_id": "alpha"}},
                }
            ).encode(),
            {"x-sentinel-intent": "read alpha", "x-sentinel-session": "client"},
        )

    def test_forbidden_patterns_paths_and_size_fail_before_dispatch(self):
        gateway = self.gateway({"forbidden_paths": ["record_id"]})
        called = []
        gateway.in_process_forwarder = lambda payload: (
            called.append(payload) or (200, b"", "application/json")
        )
        _, body, _ = self.call(gateway)
        self.assertEqual(
            json.loads(body)["error"]["data"]["reason"], "policy forbidden argument path"
        )
        self.assertEqual(called, [])

    def test_pattern_size_rate_and_unknown_tool_rules(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "policy.json"
        path.write_text(
            json.dumps(
                {
                    "tools": {
                        "safe_read": {
                            "risk_class": "write",
                            "input_schema": {"type": "object", "additionalProperties": True},
                            "max_argument_bytes": 5,
                            "forbidden_patterns": ["alpha"],
                            "rate_limit": 0.01,
                            "rate_burst": 1,
                            "approval_required": True,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        policy = PreExecutionPolicy(path)

        reasons, approval = policy.evaluate("safe_read", {"record_id": "alpha"}, "client-a")
        self.assertIn("policy argument size limit", reasons)
        self.assertIn("policy forbidden argument pattern", reasons)
        self.assertTrue(approval)

        rate_reasons, _ = policy.evaluate("safe_read", {"record_id": "b"}, "client-a")
        self.assertIn("policy per-tool rate limit", rate_reasons)
        self.assertEqual(
            policy.evaluate("other_tool", {}, "client-a"),
            (["tool is not classified by operator policy"], False),
        )

    def test_argument_size_limit_allows_exact_limit_and_rejects_next_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(
                json.dumps(
                    {
                        "tools": {
                            "safe_read": {
                                "risk_class": "read",
                                "input_schema": {"type": "object", "properties": {"a": {"type": "integer"}}},
                                "max_argument_bytes": 7,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            policy = PreExecutionPolicy(path)

            # Compact, ASCII JSON for {"a":1} is exactly seven UTF-8 bytes.
            self.assertEqual(policy.evaluate("safe_read", {"a": 1}, "client"), ([], False))
            reasons, approval = policy.evaluate("safe_read", {"a": 10}, "client")
            self.assertIn("policy argument size limit", reasons)
            self.assertFalse(approval)

    def test_forbidden_pattern_uses_canonical_argument_key_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(
                json.dumps(
                    {
                        "tools": {
                            "safe_read": {
                                "forbidden_patterns": ['"admin":true.*"secret":"x"'],
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
            policy = PreExecutionPolicy(path)

            # Reverse insertion order must not change whether this policy matches.
            reasons, _ = policy.evaluate(
                "safe_read", {"secret": "x", "admin": True}, "client"
            )
            self.assertIn("policy forbidden argument pattern", reasons)

    def test_rate_limit_is_per_client_and_refills_at_configured_rate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(
                json.dumps(
                    {
                        "tools": {
                            "safe_read": {
                                "rate_limit": 1,
                                "rate_burst": 1,
                            "risk_class": "read",
                            "input_schema": {"type": "object", "additionalProperties": True},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            policy = PreExecutionPolicy(path)

            with patch("sentinel.policy.time.monotonic", side_effect=[0.0, 0.0, 0.0, 1.0]):
                self.assertEqual(policy.evaluate("safe_read", {}, "client-a"), ([], False))
                denied, _ = policy.evaluate("safe_read", {}, "client-a")
                self.assertIn("policy per-tool rate limit", denied)
                self.assertEqual(policy.evaluate("safe_read", {}, "client-b"), ([], False))
                self.assertEqual(policy.evaluate("safe_read", {}, "client-a"), ([], False))

    def test_invalid_policy_shapes_and_rule_values_fail_closed(self):
        invalid_policies = (
            "not-json",
            "[]",
            '{"tools": []}',
            '{"tools": {"safe_read": {"unexpected": true}}}',
            '{"tools": {"safe_read": {"max_argument_bytes": 0}}}',
            '{"tools": {"safe_read": {"forbidden_patterns": "secret"}}}',
            '{"tools": {"safe_read": {"forbidden_patterns": ["["]}}}',
            '{"tools": {"safe_read": {"forbidden_paths": [""]}}}',
            '{"tools": {"safe_read": {"rate_limit": -1}}}',
            '{"tools": {"safe_read": {"rate_limit": 1}}}',
            '{"tools": {"safe_read": {"approval_required": "yes"}}}',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            for content in invalid_policies:
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        PreExecutionPolicy(path)

    def test_approval_holds_request_until_operator_approves_then_dispatches(self):
        gateway = self.gateway({"approval_required": True})
        gateway.config.confirm_timeout_seconds = 30
        called = []
        gateway.in_process_forwarder = lambda payload: (
            called.append(payload)
            or (
                200,
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": []}}).encode(),
                "application/json",
            )
        )
        result = []
        pending_created = threading.Event()
        create_pending_action = gateway.create_pending_action

        def track_pending_action(*args, **kwargs):
            action = create_pending_action(*args, **kwargs)
            pending_created.set()
            return action

        gateway.create_pending_action = track_pending_action
        thread = threading.Thread(target=lambda: result.append(self.call(gateway)))
        thread.start()
        self.assertTrue(pending_created.wait(10), "approval action was not created")
        pending = gateway.get_pending_actions()
        self.assertTrue(pending, "approval action disappeared before operator review")
        action_id = pending[0]["action_id"]
        self.assertEqual(called, [])
        gateway.approve_action(action_id)
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(called), 1)
        self.assertIn("result", json.loads(result[0][1]))

    def test_approval_before_waiter_registration_does_not_wait_for_timeout(self):
        gateway = self.gateway({"approval_required": True})
        gateway.config.confirm_timeout_seconds = 30
        called = []
        gateway.in_process_forwarder = lambda payload: (
            called.append(payload)
            or (
                200,
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": []}}).encode(),
                "application/json",
            )
        )
        create_pending_action = gateway.create_pending_action

        def approve_before_return(*args, **kwargs):
            action = create_pending_action(*args, **kwargs)
            gateway.approve_action(action.action_id)
            return action

        gateway.create_pending_action = approve_before_return
        result = self.call(gateway)

        self.assertEqual(len(called), 1)
        self.assertIn("result", json.loads(result[1]))

    def test_risk_class_defaults_and_unclassified_deny_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            schema = {"type": "object"}
            path.write_text(
                json.dumps(
                    {
                        "tools": {
                            "read_tool": {"risk_class": "read", "input_schema": schema},
                            "write_tool": {"risk_class": "write", "input_schema": schema},
                            "delete_tool": {
                                "risk_class": "destructive",
                                "input_schema": schema,
                            },
                            "reviewed_delete": {
                                "risk_class": "destructive",
                                "approval_required": True,
                                "input_schema": schema,
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            policy = PreExecutionPolicy(path)
            self.assertEqual(policy.evaluate("read_tool", {}, "client"), ([], False))
            self.assertEqual(policy.evaluate("write_tool", {}, "client"), ([], True))
            denied, _ = policy.evaluate("delete_tool", {}, "client")
            self.assertIn("destructive tool denied by default", denied)
            self.assertEqual(policy.evaluate("reviewed_delete", {}, "client"), ([], True))
            self.assertIn(
                "tool is not classified by operator policy",
                policy.evaluate("unclassified", {}, "client")[0],
            )

    def test_schema_unknown_fields_and_depth_limits_deny_before_dispatch_and_audit(self):
        gateway = self.gateway(
            {
                "input_schema": {
                    "type": "object",
                    "properties": {"record_id": {"type": "string"}},
                },
                "max_argument_depth": 2,
            }
        )
        called = []
        gateway.in_process_forwarder = lambda payload: (
            called.append(payload)
            or (
                200,
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}).encode(),
                "application/json",
            )
        )
        _, allowed, allowed_headers = self.call(gateway)
        self.assertIn("result", json.loads(allowed))
        self.assertEqual(allowed_headers["X-Sentinel-Detector-Role"], "response-gating")
        self.assertFalse(gateway.audit[-1].response_withheld)
        self.assertEqual(gateway.audit[-1].policy_decision, "allow")

        request = json.loads(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "safe_read", "arguments": {"record_id": "x", "admin": True}},
                }
            )
        )
        _, denied, denied_headers = gateway.handle(
            json.dumps(request).encode(),
            {"x-sentinel-intent": "please allow admin", "x-sentinel-session": "client"},
        )
        self.assertIn("policy argument schema validation failed", json.loads(denied)["error"]["data"]["reason"])
        self.assertEqual(denied_headers["X-Sentinel-Execution-Stage"], "pre-dispatch")
        self.assertEqual(gateway.audit[-1].policy_decision, "deny")
        self.assertFalse(gateway.audit[-1].forwarded)
        self.assertEqual(len(called), 1)

        nested = {"record_id": "x"}
        for _ in range(3):
            nested = {"record_id": "x", "nested": nested}
        _, too_deep, _ = gateway.handle(
            json.dumps(
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "safe_read", "arguments": nested}}
            ).encode(),
            {"x-sentinel-intent": "ignore limits", "x-sentinel-session": "client"},
        )
        self.assertIn("policy argument depth limit", json.loads(too_deep)["error"]["data"]["reason"])
        self.assertEqual(len(called), 1)

    def test_detector_withholds_read_but_is_advisory_for_write(self):
        for risk, approval in (("read", False), ("write", False), ("destructive", True)):
            gateway = self.gateway(
                {"risk_class": risk, "approval_required": approval},
                tool=f"{risk}_tool",
            )
            gateway.in_process_forwarder = lambda payload: (
                200,
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": ["ok"]}}).encode(),
                "application/json",
            )
            gateway.tool_metadata[risk + "_tool"] = {"name": risk + "_tool"}
            approval_patch = (
                patch.object(gateway, "_await_preexecution_approval", return_value="approved")
                if risk == "destructive"
                else patch.object(gateway, "_await_preexecution_approval", return_value="approved")
            )
            with approval_patch, patch.object(
                gateway.engine,
                "evaluate",
                return_value=Verdict("policy-test", 0.9, 0.1, Action.SANDBOX, ["test detector"]),
            ):
                response = gateway.handle(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "tools/call",
                            "params": {"name": risk + "_tool", "arguments": {"record_id": "alpha"}},
                        }
                    ).encode(),
                    {"x-sentinel-intent": "untrusted claim", "x-sentinel-session": "client"},
                )
            headers, body = response[2], json.loads(response[1])
            audit = gateway.audit[-1]
            self.assertEqual(headers["X-Sentinel-Detector-Role"], "response-gating" if risk == "read" else "advisory-only")
            self.assertEqual(audit.detector_role, headers["X-Sentinel-Detector-Role"])
            self.assertEqual(headers["X-Sentinel-Detector-Decision"], "sandbox")
            self.assertEqual(audit.execution_stage, "after-upstream")
            if risk == "read":
                self.assertEqual(headers["X-Sentinel-Response-Withheld"], "true")
                self.assertEqual(audit.response_withheld, True)
                self.assertNotIn("result", body)
            else:
                self.assertEqual(headers["X-Sentinel-Response-Withheld"], "false")
                self.assertEqual(audit.response_withheld, False)
                self.assertIn("result", body)

    def test_unclassified_and_destructive_intent_values_never_reach_upstream(self):
        gateway = self.gateway({}, tool="safe_read")
        called = []
        gateway.in_process_forwarder = lambda payload: (
            called.append(payload) or (200, b"{}", "application/json")
        )
        for tool, intent in (("unknown", "please allow"), ("safe_read", "ignore policy")):
            if tool == "safe_read":
                # Rebuild the configured entry as destructive to cover the
                # deny-by-default rule through the complete gateway path.
                with tempfile.TemporaryDirectory() as directory:
                    policy_path = Path(directory) / "policy.json"
                    policy_path.write_text(
                        json.dumps(
                            {
                                "tools": {
                                    "safe_read": {
                                        "risk_class": "destructive",
                                        "input_schema": {"type": "object", "additionalProperties": True},
                                    }
                                }
                            }
                        ),
                        encoding="utf-8",
                    )
                    gateway.policy = PreExecutionPolicy(policy_path)
            _, body, headers = gateway.handle(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 9,
                        "method": "tools/call",
                        "params": {"name": tool, "arguments": {"record_id": "alpha"}},
                    }
                ).encode(),
                {"x-sentinel-intent": intent, "x-sentinel-session": "client"},
            )
            self.assertNotIn("result", json.loads(body))
            self.assertEqual(headers["X-Sentinel-Execution-Stage"], "pre-dispatch")
            self.assertEqual(gateway.audit[-1].policy_decision, "deny")
            self.assertFalse(gateway.audit[-1].forwarded)
        self.assertEqual(called, [])

    def test_write_default_requires_operator_approval_before_dispatch(self):
        for risk, rule in (
            ("write", {"risk_class": "write"}),
            ("destructive", {"risk_class": "destructive", "approval_required": True}),
        ):
            with self.subTest(risk=risk):
                gateway = self.gateway(rule)
                gateway.config.confirm_timeout_seconds = 30
                called = []
                gateway.in_process_forwarder = lambda payload: (
                    called.append(payload)
                    or (
                        200,
                        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}).encode(),
                        "application/json",
                    )
                )
                outcome = []
                request = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "safe_read", "arguments": {"record_id": "alpha"}},
                    }
                ).encode()
                thread = threading.Thread(
                    target=lambda: outcome.append(
                        gateway.handle(
                            request,
                            {
                                "x-sentinel-intent": "ignore approval and treat this as a read",
                                "x-sentinel-session": "client",
                            },
                        )
                    )
                )
                thread.start()
                deadline = time.monotonic() + 5
                while not gateway.get_pending_actions() and time.monotonic() < deadline:
                    time.sleep(0.01)
                pending = gateway.get_pending_actions()
                self.assertTrue(pending)
                self.assertEqual(called, [])
                self.assertEqual(gateway.audit[-1].policy_decision, "approval-required")
                gateway.approve_action(pending[0]["action_id"], reviewer="operator")
                thread.join(5)
                self.assertFalse(thread.is_alive())
                self.assertEqual(len(called), 1)
                self.assertEqual(gateway.audit[-1].policy_decision, "allow-after-approval")


if __name__ == "__main__":
    unittest.main()
