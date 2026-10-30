"""Tests locking in the capability trust recovery requirements and verifying the absorbing-state failure."""
from __future__ import annotations

import random
import unittest

from sentinel.models import Action, Interaction
from sentinel.novelty import CapabilityState, CapabilityTrustController


class CapabilityTrustRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.controller = CapabilityTrustController()
        self.event = Interaction(
            server_id="secondary-test-mcp",
            tool_name="safe_read",
            arguments={"record_id": "record-1005"},
            response=None,
            latency_ms=18.0,
            user_intent="Read record record-1005",
            success=True,
            side_effect=False,
            session_id="test-session-1",
            timestamp=1_700_000_000,
        )

    def test_spurious_causal_alarms_do_not_collapse_trust(self):
        """1. A benign-only stream where ~9% of events carry a spurious risk of 0.5
        must NOT drive any capability's trust below the CONFIRM threshold (0.55)."""
        rng = random.Random(42)
        final_state = None
        for i in range(100):
            # ~9% spurious causal floor (risk=0.50), otherwise clean benign (risk=0.15)
            risk = 0.50 if rng.random() < 0.09 else 0.15
            action, final_state = self.controller.decide(self.event, risk=risk, uncertainty=0.10)

        # On the unfixed code, trust collapses to 0.0000 and enters the absorbing trap.
        # This requirement asserts that trust remains above the CONFIRM threshold (0.55).
        self.assertIsNotNone(final_state)
        self.assertGreater(
            final_state.trust,
            0.55,
            f"Spurious causal alarms collapsed trust to {final_state.trust:.4f} (expected > 0.55)",
        )

    def test_clean_benign_restores_trust_no_absorbing_state(self):
        """2. After trust is reduced by spurious alarms, a long run of clean benign
        evidence must be able to restore it (no absorbing state)."""
        # Artificially depress trust into the historical restriction zone (e.g. 0.40)
        state = self.controller.states.setdefault(
            (self.event.server_id, self.event.tool_name), CapabilityState(trust=0.40)
        )
        state.trust = 0.40

        # Feed 100 clean benign events (risk=0.10, no uncertainty)
        final_state = None
        for _ in range(100):
            action, final_state = self.controller.decide(self.event, risk=0.10, uncertainty=0.05)

        # On the unfixed code, 1 - 0.40 = 0.60 >= 0.45 triggers CONFIRM, preventing ALLOW.
        # Trust cannot increment, so trust remains at 0.40 or lower (absorbing state).
        self.assertIsNotNone(final_state)
        self.assertGreater(
            final_state.trust,
            0.55,
            f"Trust remained trapped in absorbing state at {final_state.trust:.4f} (expected recovery > 0.55)",
        )

    def test_genuinely_malicious_capability_loses_trust(self):
        """3. A genuinely malicious capability (sustained high risk) must still lose
        trust and stay restricted (the fix must not disable isolation)."""
        final_state = None
        final_action = None
        for _ in range(20):
            final_action, final_state = self.controller.decide(self.event, risk=0.85, uncertainty=0.20)

        self.assertIsNotNone(final_state)
        self.assertLess(final_state.trust, 0.30, f"Malicious capability retained high trust: {final_state.trust}")
        self.assertIn(final_action, (Action.CONFIRM, Action.SANDBOX, Action.ISOLATE))

    def test_legacy_mode_selectable_and_reproduces_absorbing_state(self):
        """4. Verify that legacy_mode=True remains selectable and reproduces the absorbing state."""
        legacy_controller = CapabilityTrustController(legacy_mode=True)
        state = legacy_controller.states.setdefault(
            (self.event.server_id, self.event.tool_name), CapabilityState(trust=0.40)
        )
        state.trust = 0.40

        # Feed 100 clean benign events under legacy mode
        for _ in range(100):
            action, final_state = legacy_controller.decide(self.event, risk=0.10, uncertainty=0.05)

        # In legacy mode, trust is permanently stuck at 0.40 (absorbing state)
        self.assertLessEqual(final_state.trust, 0.40)


if __name__ == "__main__":
    unittest.main()
