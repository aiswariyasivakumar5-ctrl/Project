import hashlib
import unittest

from sentinel import Action, Interaction, SentinelEngine
from sentinel.simulator import cross_server_attack, normal_events


class SentinelEngineTests(unittest.TestCase):
    def trained_engine(self) -> SentinelEngine:
        engine = SentinelEngine(warmup_events=12)
        for event in normal_events(80):
            engine.evaluate(event)
        return engine

    def test_normal_event_is_allowed(self):
        verdict = self.trained_engine().evaluate(next(normal_events(1, seed=99)), learn=False)
        self.assertIn(verdict.action, {Action.ALLOW, Action.CONFIRM})
        self.assertLess(verdict.anomaly_score, 0.65)

    def test_exfiltration_is_not_learned(self):
        engine = self.trained_engine()
        quarantined_before = len(engine.quarantine["crm-server"])
        event = Interaction("crm-server", "export_secrets", {"include_tokens": True},
                            {"secret_tokens": ["x"] * 1000}, 900,
                            "Find customer 1001", True, True, "attack")
        verdict = engine.evaluate(event)
        self.assertFalse(verdict.baseline_updated)
        self.assertIn(verdict.action, {Action.CONFIRM, Action.SANDBOX, Action.ISOLATE})
        self.assertEqual(len(engine.quarantine["crm-server"]), quarantined_before + 1)

    def test_trust_decreases_on_suspicious_activity(self):
        engine = self.trained_engine()
        before = engine.server_status("crm-server")["trust_score"]
        event = Interaction("crm-server", "delete_all", {"scope": "global"}, {}, 500,
                            "Read customer 1001", False, True, "attack")
        verdict = engine.evaluate(event)
        self.assertLess(verdict.trust_score, before)

    def test_cross_server_flow_produces_causal_evidence(self):
        engine = SentinelEngine(warmup_events=1)
        first, second = cross_server_attack()
        engine.evaluate(first)
        verdict = engine.evaluate(second, learn=False)
        self.assertGreaterEqual(verdict.components["causal"], 0.6)
        trace = engine.causal_graph.trace(verdict.trace_id)
        self.assertTrue(any(edge["relation"] == "cross_server_data_flow" for edge in trace["incoming"]))

    def test_valid_attestation_challenge_is_verified(self):
        engine = self.trained_engine()
        suspicious = Interaction(
            "crm-server", "export_secrets", {"scope": "all"}, {"secret": "x" * 1000},
            500, "Find customer 1001", True, True, "attest",
            capability_digest="crm-v1-tools-find-customer",
        )
        first_verdict = engine.evaluate(suspicious)
        self.assertIsNotNone(first_verdict.challenge)
        challenge = first_verdict.challenge
        echo = hashlib.sha256(
            f"{challenge['nonce']}:{challenge['expected_capability_digest']}".encode()
        ).hexdigest()
        response = Interaction(
            "crm-server", "find_customer", {"customer_id": 1001}, {"id": 1001}, 42,
            "Find customer 1001", True, False, "attest",
            capability_digest=challenge["expected_capability_digest"],
            attestation_challenge_id=challenge["challenge_id"], attestation_echo=echo,
        )
        verdict = engine.evaluate(response, learn=False)
        self.assertEqual(verdict.components["attestation"], 0.0)

    def test_changed_capability_fingerprint_is_flagged(self):
        engine = self.trained_engine()
        event = next(normal_events(1))
        event.capability_digest = "unexpected-capability-set"
        verdict = engine.evaluate(event, learn=False)
        self.assertEqual(verdict.components["attestation"], 1.0)
        self.assertIn("behavioral attestation failed", verdict.reasons)


if __name__ == "__main__":
    unittest.main()
