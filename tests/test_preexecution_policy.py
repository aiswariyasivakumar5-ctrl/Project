import json
import tempfile
import threading
import unittest
from pathlib import Path

from sentinel.gateway import GatewayConfig, SentinelGateway
from sentinel.policy import PreExecutionPolicy


class PreExecutionPolicyTests(unittest.TestCase):
    def gateway(self, rule):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "policy.json"
        path.write_text(json.dumps({"tools": {"safe_read": rule}}), encoding="utf-8")
        gateway = SentinelGateway(
            GatewayConfig(
                "http://127.0.0.1:8765",
                "policy-test",
                allowed_tools=("safe_read",),
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
        self.assertEqual(policy.evaluate("other_tool", {}, "client-a"), ([], False))

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


if __name__ == "__main__":
    unittest.main()
