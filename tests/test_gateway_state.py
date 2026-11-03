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
