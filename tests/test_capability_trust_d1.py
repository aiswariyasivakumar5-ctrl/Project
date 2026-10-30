"""Unit and regression tests for Capability-Trust Design D1."""
from __future__ import annotations

import unittest

from sentinel.models import Action, Interaction
from sentinel.novelty import CapabilityTrustController


class CapabilityTrustD1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = CapabilityTrustController()
        self.event = Interaction(
            "local-test-mcp", "safe_read", {"record_id": "rec-1"}, None, 20.0,
            "Read record rec-1", side_effect=False, session_id="test-session",
        )

    def test_removed_hack_fallback_path(self) -> None:
        """Verify that when components is None, no causal_risk guess occurs."""
        # Previous hack guessed causal_risk = 0.60 when 0.48 <= risk <= 0.52
        # Now it falls back to conservative behavior: causal_risk = 0.0, other_signals = False
        action, state = self.controller.decide(self.event, risk=0.50, uncertainty=0.10, components=None)
        self.assertEqual(action, Action.CONFIRM)
        # Because causal_risk is 0.0 and other_signals is False, no causal history is recorded
        self.assertEqual(len(self.controller.causal_history[("local-test-mcp", "safe_read")]), 0)

    def test_sustained_causal_only_attack_does_not_autonomously_isolate(self) -> None:
        """Verify that sustained cross-server causal flow without corroboration caps at 0.55 trust.
        
        It produces per-event CONFIRM, but does not escalate to autonomous ISOLATE (<= 0.18)
        without human review or secondary detector corroboration.
        """
        for i in range(25):
            components = {"causal": 0.50}  # No behavior, intent, sequence, attestation, or provenance
            action, state = self.controller.decide(self.event, risk=0.50, uncertainty=0.10, components=components)
            self.assertEqual(action, Action.CONFIRM)
            # Trust must never drop below 0.55 on uncorroborated causal flags
            self.assertGreaterEqual(state.trust, 0.55)

        self.assertEqual(state.trust, 0.55)
        # Verify it has not isolated (isolation requires trust <= 0.18)
        self.assertFalse(state.trust <= 0.18)

    def test_benign_false_alarms_never_drive_capability_to_isolation(self) -> None:
        """Verify that false alarm rates of 5%, 10%, and 20% never drive trust to isolation."""
        for rate in [0.05, 0.10, 0.20]:
            ctrl = CapabilityTrustController()
            interval = int(1.0 / rate)
            for i in range(100):
                is_false_alarm = (i % interval == 0)
                risk = 0.50 if is_false_alarm else 0.05
                components = {"causal": 0.50 if is_false_alarm else 0.0}
                action, state = ctrl.decide(self.event, risk=risk, uncertainty=0.10, components=components)
                # In every step, trust must remain strictly above the isolation floor (0.18)
                self.assertGreater(state.trust, 0.20, f"Trust dropped to {state.trust} at rate {rate} on step {i}")

            self.assertGreater(state.trust, 0.50)


if __name__ == "__main__":
    unittest.main()
