from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sentinel.audit_log import verify_audit_log
from sentinel.baseline import manage_baseline
from sentinel.gateway import GatewayConfig, SentinelGateway


class BaselineManagementTests(unittest.TestCase):
    def test_online_learning_change_records_actor_time_version_and_diff_in_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = root / "policy.json"
            audit = root / "gateway-audit.jsonl"
            policy.write_text(
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
            gateway = SentinelGateway(
                GatewayConfig(
                    "http://127.0.0.1",
                    "learning-audit-test",
                    allowed_tools=("safe_read",),
                    policy_file=str(policy),
                    audit_log_path=str(audit),
                    enable_learning=True,
                )
            )
            gateway.in_process_forwarder = lambda payload: (
                200,
                json.dumps(
                    {"jsonrpc": "2.0", "id": 1, "result": {"content": ["ok"]}}
                ).encode(),
                "application/json",
            )
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "safe_read", "arguments": {}},
            }
            status, body, _ = gateway.handle(
                json.dumps(request).encode(), {"x-sentinel-session": "learning-client"}
            )
            self.assertEqual(status, 200)
            self.assertIn("result", json.loads(body))

            change = gateway.audit[-1].baseline_change
            self.assertIsNotNone(change)
            assert change is not None
            self.assertEqual(change["actor"], "learning-client")
            self.assertGreater(change["changed_at"], 0)
            self.assertEqual(change["version"], 2)
            self.assertIn("trusted", change["diff_summary"])
            valid, _ = verify_audit_log(audit)
            self.assertTrue(valid)
            record = json.loads(audit.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(record["baseline_change"]["actor"], "learning-client")
            self.assertEqual(record["baseline_change"]["version"], 2)
            self.assertTrue(record["baseline_change"]["diff_summary"])

    def test_frozen_by_default_and_operator_approval_export_rollback_are_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "state.json"
            export = root / "approved.json"
            audit = root / "audit.jsonl"
            gateway = SentinelGateway(GatewayConfig("http://127.0.0.1", "baseline-test"))
            self.assertFalse(gateway.learning_enabled)
            state = gateway.export_state()
            self.assertEqual(state["baseline"]["status"], "unapproved")
            gateway.save_state(original)

            manage_baseline("approve", original, actor="operator-a", audit_log=audit)
            approved = SentinelGateway(GatewayConfig("http://127.0.0.1", "baseline-test"))
            approved.load_state(original)
            self.assertEqual(approved.baseline_metadata["status"], "approved")
            self.assertEqual(approved.baseline_metadata["approved_by"], "operator-a")
            version = approved.baseline_metadata["version"]

            manage_baseline(
                "export", original, actor="operator-a", audit_log=audit, output=export
            )
            self.assertTrue(export.is_file())

            changed = SentinelGateway(GatewayConfig("http://127.0.0.1", "baseline-test"))
            changed.load_state(original)
            changed.baseline_metadata.update(
                {
                    "version": version + 1,
                    "status": "unapproved",
                    "approved_by": None,
                    "approved_at": None,
                    "changed_by": "operator-b",
                    "changed_at": 123.0,
                    "diff_summary": "test candidate mutation",
                }
            )
            changed.save_state(original)
            with self.assertRaisesRegex(ValueError, "only an approved baseline"):
                manage_baseline(
                    "export",
                    original,
                    actor="operator-a",
                    audit_log=audit,
                    output=root / "no.json",
                )
            changed.baseline_metadata.update(
                {
                    "status": "approved",
                    "approved_by": "operator-b",
                    "approved_at": 124.0,
                    "changed_by": "operator-b",
                    "changed_at": 124.0,
                    "diff_summary": "operator-approved test candidate",
                }
            )
            changed.save_state(original)
            with self.assertRaises(FileExistsError):
                manage_baseline(
                    "export", original, actor="operator-a", audit_log=audit, output=export
                )

            manage_baseline(
                "rollback",
                original,
                actor="operator-b",
                audit_log=audit,
                version_file=export,
            )
            rolled_back = SentinelGateway(GatewayConfig("http://127.0.0.1", "baseline-test"))
            rolled_back.load_state(original)
            self.assertEqual(rolled_back.baseline_metadata["status"], "approved")
            self.assertEqual(rolled_back.baseline_metadata["approved_by"], "operator-b")
            self.assertEqual(rolled_back.baseline_metadata["version"], version + 2)
            valid, _ = verify_audit_log(audit)
            self.assertTrue(valid)
            events = [json.loads(line) for line in audit.read_text().splitlines()]
            self.assertEqual(
                [event["action"] for event in events], ["approve", "export", "rollback"]
            )
            self.assertTrue(all(event["actor"] for event in events))
            self.assertTrue(all(event["diff_summary"] for event in events))

    def test_baseline_management_requires_actor_audit_and_rollback_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            SentinelGateway(GatewayConfig("http://127.0.0.1", "baseline-test")).save_state(path)
            with self.assertRaisesRegex(ValueError, "--actor"):
                manage_baseline("approve", path, actor=None, audit_log=path.with_suffix(".audit"))
            with self.assertRaisesRegex(ValueError, "--audit-log"):
                manage_baseline("approve", path, actor="operator", audit_log=None)
            with self.assertRaisesRegex(ValueError, "--version-file"):
                manage_baseline(
                    "rollback",
                    path,
                    actor="operator",
                    audit_log=path.with_suffix(".audit"),
                )


if __name__ == "__main__":
    unittest.main()
