from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from sentinel.engine import SentinelEngine
from sentinel.gateway import GatewayConfig, SentinelGateway
from sentinel.models import Action
from sentinel.novelty import CapabilityState
from sentinel.retention import StateCapacityError


class GatewayStateTests(unittest.TestCase):
    def make_gateway(self, **overrides) -> SentinelGateway:
        values = {
            "upstream_url": "http://127.0.0.1:8765",
            "server_id": "state-test",
            "allowed_tools": ("read",),
        }
        values.update(overrides)
        return SentinelGateway(GatewayConfig(**values), SentinelEngine())

    def add_action(self, gateway: SentinelGateway, **overrides):
        values = {
            "trace_id": "trace",
            "session_id": "session",
            "tool": "read",
            "arguments": {},
            "upstream_response": b'{"result":{}}',
        }
        values.update(overrides)
        return gateway.create_pending_action(**values)

    def test_pending_capacity_evicts_resolved_first(self):
        gateway = self.make_gateway(max_pending_actions=2)
        resolved = self.add_action(gateway)
        gateway.deny_action(resolved.action_id)
        pending = self.add_action(gateway, trace_id="pending")

        added = self.add_action(gateway, trace_id="added")

        self.assertNotIn(resolved.action_id, gateway.pending_actions)
        self.assertIn(pending.action_id, gateway.pending_actions)
        self.assertIn(added.action_id, gateway.pending_actions)
        self.assertEqual(len(gateway.pending_actions), 2)

    def test_pending_capacity_fails_closed_when_all_actions_are_pending(self):
        gateway = self.make_gateway(max_pending_actions=1)
        first = self.add_action(gateway)

        with self.assertRaisesRegex(StateCapacityError, "capacity exhausted"):
            self.add_action(gateway, trace_id="overflow")

        self.assertEqual(list(gateway.pending_actions), [first.action_id])

    def test_expired_pending_action_is_cleared_and_evicted_before_insert(self):
        gateway = self.make_gateway(max_pending_actions=1)
        expired = self.add_action(gateway)
        expired.expires_at = time.time() - 1

        replacement = self.add_action(gateway, trace_id="replacement")

        self.assertNotIn(expired.action_id, gateway.pending_actions)
        self.assertIn(replacement.action_id, gateway.pending_actions)
        self.assertIsNone(expired.upstream_response)

    def test_resolved_actions_expire_after_retention_ttl(self):
        gateway = self.make_gateway(resolved_action_ttl_seconds=0.02)
        action = self.add_action(gateway)
        gateway.deny_action(action.action_id)
        time.sleep(0.03)

        self.assertIsNone(gateway.get_action(action.action_id))

    def test_pending_and_reviewed_actions_roundtrip_with_gateway_state(self):
        source = self.make_gateway()
        pending = self.add_action(source)
        approved = self.add_action(source, trace_id="approved")
        source.approve_action(approved.action_id)

        restored = self.make_gateway()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            source.save_state(path)
            restored.load_state(path)

        self.assertEqual(restored.pending_actions[pending.action_id].status, "pending")
        self.assertEqual(
            restored.pending_actions[pending.action_id].upstream_response, b'{"result":{}}'
        )
        self.assertEqual(restored.pending_actions[approved.action_id].status, "approved")
        self.assertEqual(restored.pending_actions[approved.action_id].reviewed_by, "operator")

    def test_queue_overflow_returns_isolate_decision_from_gateway(self):
        gateway = self.make_gateway(max_pending_actions=1)
        self.add_action(gateway)

        class ConfirmVerdict:
            action = Action.CONFIRM
            trace_id = "confirm-trace"
            reasons = ["requires review"]
            challenge = None
            anomaly_score = 0.7
            uncertainty = 0.1
            components = {}
            trust_score = 0.4
            provenance = None

        gateway.in_process_forwarder = lambda request: (
            200,
            json.dumps(
                {"jsonrpc": "2.0", "id": request["id"], "result": {"private": True}}
            ).encode(),
            "application/json",
        )
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "read", "arguments": {}},
            }
        ).encode()
        with patch.object(gateway.engine, "evaluate", return_value=ConfirmVerdict()):
            status, response, headers = gateway.handle(body, {"x-sentinel-intent": "read"})

        decoded = json.loads(response)
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Sentinel-Decision"], "isolate")
        self.assertEqual(decoded["error"]["data"]["decision"], "isolate")
        self.assertEqual(len(gateway.pending_actions), 1)

    def test_state_schema_roundtrip_and_malformed_arrays_do_not_mutate(self):
        source = self.make_gateway()
        profile = source.engine._profile("stored-server", 12)
        profile.trusted_count = 9
        state = source.export_state()
        self.assertEqual(state["schema_version"], 1)

        target = self.make_gateway()
        target.import_state(state)
        self.assertEqual(target.engine.profiles["stored-server"].trusted_count, 9)

        malformed = json.loads(json.dumps(state))
        malformed["engine"]["profiles"]["stored-server"]["scaler"]["mean"].pop()
        untouched = self.make_gateway()
        with self.assertRaisesRegex(ValueError, "invalid shape"):
            untouched.import_state(malformed)
        self.assertEqual(untouched.engine.profiles, {})

    def test_schema_version_is_required_and_checked(self):
        gateway = self.make_gateway()
        state = gateway.export_state()
        state["schema_version"] = 999
        target = self.make_gateway()
        with self.assertRaisesRegex(ValueError, "unsupported schema version"):
            target.import_state(state)
        self.assertEqual(target.engine.profiles, {})

    def test_novelty_capability_counters_roundtrip(self):
        source = self.make_gateway(novelty=True)
        source.novelty.capabilities.states[("state-test", "read")] = CapabilityState(
            trust=0.8, accepted=4, restricted=2
        )
        target = self.make_gateway(novelty=True)

        target.import_state(source.export_state())

        restored = target.novelty.capabilities.states[("state-test", "read")]
        self.assertEqual(restored.trust, 0.8)
        self.assertEqual(restored.accepted, 4)
        self.assertEqual(restored.restricted, 2)

    def test_atomic_save_failure_preserves_existing_state(self):
        gateway = self.make_gateway()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gateway-state.json"
            path.write_bytes(b"previous-good-state")
            with patch("sentinel.gateway.os.replace", side_effect=OSError("simulated crash")):
                with self.assertRaisesRegex(OSError, "simulated crash"):
                    gateway.save_state(path)
            self.assertEqual(path.read_bytes(), b"previous-good-state")
            self.assertEqual(list(Path(directory).iterdir()), [path])
        def test_state_mac_is_independent_of_dictionary_key_order(self):
        key = "test-state-integrity-key"
        first = {"server_id": "state-test", "version": 1}
        second = {"version": 1, "server_id": "state-test"}

        self.assertEqual(
            SentinelGateway._state_mac(first, key),
            SentinelGateway._state_mac(second, key),
        )

    def test_state_mac_uses_compact_canonical_json(self):
        import hashlib
        import hmac

        key = "test-state-integrity-key"
        state = {"server_id": "state-test", "version": 1}
        canonical = json.dumps(
            state, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        expected = hmac.digest(key.encode("utf-8"), canonical, "sha256").hex()

        self.assertEqual(SentinelGateway._state_mac(state, key), expected)

    def test_state_mac_rejects_non_finite_numbers(self):
        key = "test-state-integrity-key"

        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    SentinelGateway._state_mac({"value": value}, key)
                    
    def test_hmac_state_rejects_unsigned_and_tampered_files(self):
        gateway = self.make_gateway()
        key = "test-state-integrity-key-with-sufficient-entropy"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gateway-state.json"
            with patch.dict(os.environ, {"MCP_SENTINEL_STATE_KEY": key}):
                gateway.save_state(path)
                valid = json.loads(path.read_text(encoding="utf-8"))
                self.make_gateway().load_state(path)

                valid["server_id"] = "modified-after-signing"
                path.write_text(json.dumps(valid), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "HMAC verification failed"):
                    self.make_gateway().load_state(path)

                del valid["hmac_sha256"]
                path.write_text(json.dumps(valid), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "unsigned"):
                    self.make_gateway().load_state(path)

    def test_oversized_state_file_is_rejected_before_import(self):
        target = self.make_gateway()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.json"
            path.write_bytes(b"x" * 33)
            with patch("sentinel.gateway.MAX_STATE_FILE_BYTES", 32):
                with self.assertRaisesRegex(ValueError, "exceeds maximum size"):
                    target.load_state(path)
        self.assertEqual(target.engine.profiles, {})


if __name__ == "__main__":
    unittest.main()
