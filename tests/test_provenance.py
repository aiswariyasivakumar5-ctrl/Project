import hashlib
import unittest
import copy
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from sentinel import Action, Interaction, SentinelEngine
from sentinel.scenarios import run_provenance_scenario
from sentinel.engine import EngineConfig
from sentinel.experiment import ExperimentConfig, run_experiment
from sentinel.provenance import ProvenanceLedger, ScenarioClock


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.ledger = ProvenanceLedger(lambda: self.now)
        self.claim = self.ledger.issue("event-1", "Read record 1", "s1", "srv", "safe_read",
                                       {"record_id": "1"}, ttl=10)

    def valid(self, claim=None, **kwargs):
        claim = claim or self.claim
        values = {"intent": "Read record 1", "session_id": "s1", "server_id": "srv",
                  "tool_name": "safe_read", "arguments": {"record_id": "1"}}
        values.update(kwargs)
        return self.ledger.validate(claim.claim_id, **values)

    def test_valid_claim_is_single_use(self):
        self.assertTrue(self.valid().valid)
        self.assertEqual(self.valid().reason, "provenance replay")

    def test_intent_server_and_tool_mismatch(self):
        self.assertEqual(self.valid(intent="Delete record 1").reason, "provenance intent mismatch")
        self.assertEqual(self.valid(server_id="other").reason, "provenance context mismatch")
        self.assertEqual(self.valid(tool_name="simulated_delete").reason, "provenance context mismatch")

    def test_stale_and_exact_expiration_boundary(self):
        self.now = 110
        self.assertEqual(self.valid().reason, "stale provenance")

    def test_future_created_claim_and_clock_rollback(self):
        future = self.ledger.issue("future", "Read record 1", "s1", "srv", "safe_read",
                                   {"record_id": "1"}, created_at=200)
        self.assertEqual(self.valid(future, now=199).reason, "provenance clock rollback")

    def test_predecessor_validation(self):
        child = self.ledger.issue("event-2", "Read record 1", "s1", "srv", "safe_read",
                                  {"record_id": "1"}, predecessor=self.claim.claim_id)
        self.assertTrue(self.valid(child).valid)
        missing = self.ledger.issue("event-3", "Read record 1", "s1", "srv", "safe_read",
                                    {"record_id": "1"}, predecessor="missing")
        self.assertEqual(self.valid(missing).reason, "unknown causal predecessor")

    def test_malformed_and_argument_mismatch(self):
        self.assertFalse(self.ledger.validate("missing", intent="Read record 1", session_id="s1",
                         server_id="srv", tool_name="safe_read", arguments={}).valid)
        self.assertEqual(self.valid(arguments={"record_id": "2"}).reason, "provenance argument mismatch")

    def engine_event(self, claim_id, *, intent="Read record 1", server="srv", tool="safe_read", timestamp=100):
        return Interaction(server, tool, {"record_id": "1"}, None, 1, intent, True, False,
                           "s1", timestamp, provenance_id=claim_id)

    def test_engine_valid_stale_context_and_replay(self):
        clock = ScenarioClock()
        engine = SentinelEngine(warmup_events=0, provenance_clock=clock)
        origin = engine.evaluate(self.engine_event(None), learn=False).trace_id
        claim = engine.issue_provenance(origin, self.engine_event(None), ttl=10)
        self.assertEqual(engine.evaluate(self.engine_event(claim.claim_id), learn=False).components["provenance"], 0)
        replay = engine.evaluate(self.engine_event(claim.claim_id), learn=False)
        self.assertEqual(replay.action, Action.ISOLATE)
        self.assertIn("provenance replay", replay.reasons)
        stale = engine.issue_provenance(origin, self.engine_event(None), ttl=10)
        clock.value = 110
        stale_result = engine.evaluate(self.engine_event(stale.claim_id, timestamp=110), learn=False)
        self.assertEqual(stale_result.action, Action.ISOLATE)
        self.assertIn("stale provenance", stale_result.reasons)
        other = engine.issue_provenance(origin, self.engine_event(None), ttl=10)
        mismatch = engine.evaluate(self.engine_event(other.claim_id, server="other"), learn=False)
        self.assertEqual(mismatch.action, Action.ISOLATE)
        self.assertIn("provenance context mismatch", mismatch.reasons)

    def test_invalid_provenance_plus_successful_attestation_stays_isolated(self):
        engine = SentinelEngine(warmup_events=0)
        engine.attestation.enroll("srv", "v1")
        first = self.engine_event("missing")
        first.capability_digest = "v1"
        verdict = engine.evaluate(first, learn=False)
        self.assertIsNotNone(verdict.challenge)
        challenge = verdict.challenge
        echo = hashlib.sha256(f"{challenge['nonce']}:{challenge['expected_capability_digest']}".encode()).hexdigest()
        event = self.engine_event("missing")
        event.capability_digest = "v1"
        event.attestation_challenge_id = challenge["challenge_id"]
        event.attestation_echo = echo
        second = engine.evaluate(event, learn=False)
        self.assertEqual(second.action, Action.ISOLATE)
        self.assertEqual(second.components["attestation"], 0)
        self.assertFalse(second.baseline_updated)

    def test_executable_delayed_and_replay_scenarios(self):
        delayed = run_provenance_scenario("delayed_causal_misuse", SentinelEngine(warmup_events=0), [100.0])
        self.assertEqual(delayed[-1].action, Action.ISOLATE)
        self.assertIn("stale provenance", delayed[-1].reasons)
        self.assertNotIn("provenance replay", delayed[-1].reasons)
        self.assertIn(delayed[0].action, {Action.ALLOW, Action.OBSERVE})
        replay = run_provenance_scenario("provenance_replay", SentinelEngine(warmup_events=0), [100.0])
        self.assertEqual(replay[0].components["provenance"], 0)
        self.assertEqual(replay[1].action, Action.ISOLATE)
        self.assertIn("provenance replay", replay[1].reasons)

    def test_legacy_interaction_construction_and_from_dict(self):
        event = Interaction.from_dict({"server_id": "s", "tool_name": "t", "arguments": {},
                                       "response": None, "latency_ms": 1, "user_intent": "Read"})
        self.assertIsNone(event.provenance_id)


class ProvenanceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.clock = ScenarioClock()
        self.engine = SentinelEngine(provenance_clock=self.clock)
        self.target = Interaction("srv", "safe_read", {"record_id": "1"}, {}, 10,
                                  "Read record 1", session_id="session")
        self.prior = self.engine.evaluate(self.target, learn=False).trace_id
        self.origin = self.engine.evaluate(self.target, learn=False).trace_id
        self.claim = self.engine.issue_provenance(self.origin, self.target, ttl=10)

    def use(self, **changes):
        return self.engine.evaluate(replace(self.target, provenance_id=self.claim.claim_id, **changes))

    def check(self, **changes):
        values = dict(intent=self.target.user_intent, session_id=self.target.session_id,
                      server_id=self.target.server_id, tool_name=self.target.tool_name,
                      arguments=self.target.arguments, consume=False)
        values.update(changes)
        return self.engine.provenance.validate(self.claim.claim_id, **values)

    def test_valid_use_and_legacy_learning(self):
        verdict = self.use()
        self.assertIn(verdict.action, {Action.ALLOW, Action.OBSERVE})
        self.assertTrue(verdict.provenance["valid"])
        self.assertTrue(verdict.baseline_updated)
        self.assertTrue(self.engine.evaluate(self.target).baseline_updated)

    def test_all_context_bindings_reject_without_learning(self):
        for change, reason in [
            ({"user_intent": "Delete record 1"}, "provenance intent mismatch"),
            ({"session_id": "other"}, "provenance context mismatch"),
            ({"server_id": "other"}, "provenance context mismatch"),
            ({"tool_name": "calculate"}, "provenance context mismatch"),
            ({"arguments": {"record_id": "2"}}, "provenance argument mismatch"),
        ]:
            with self.subTest(change=change):
                verdict = self.use(**change)
                self.assertEqual(verdict.action, Action.ISOLATE)
                self.assertIn(reason, verdict.reasons)
                self.assertFalse(verdict.baseline_updated)
        self.assertEqual(self.engine.provenance.claims[self.claim.claim_id].uses, 0)

    def test_expiration_is_sticky_even_after_backdating(self):
        self.clock.value = 110
        self.assertIn("stale provenance", self.use(timestamp=100).reasons)
        self.clock.value = 105
        self.assertIn("stale provenance", self.use().reasons)
        self.assertEqual(self.engine.provenance.claims[self.claim.claim_id].uses, 0)

    def test_rollback_after_valid_peek_is_sticky(self):
        self.clock.value = 105
        self.assertTrue(self.check().valid)
        self.clock.value = 104
        self.assertEqual(self.check().reason, "provenance clock rollback")
        self.clock.value = 106
        self.assertEqual(self.check().reason, "provenance clock rollback")

    def test_future_created_claim_cannot_recover(self):
        self.clock.value = 99
        self.assertEqual(self.check().reason, "provenance clock rollback")
        self.clock.value = 101
        self.assertFalse(self.check().valid)

    def test_nonfinite_clock_rejected_and_sticky(self):
        for value in (float("nan"), float("inf"), float("-inf"), "100", True):
            with self.subTest(value=value):
                self.setUp()
                self.clock.value = value
                verdict = self.use()
                self.assertEqual(verdict.action, Action.ISOLATE)
                self.assertIn("invalid provenance timestamp", verdict.reasons)
                self.assertFalse(verdict.baseline_updated)
                self.clock.value = 101
                self.assertFalse(self.check().valid)

    def test_invalid_creation_time_and_ttl_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf"), True, "10"):
            with self.subTest(creation=value), self.assertRaises(ValueError):
                self.engine.provenance.issue(self.origin, "Read record 1", "session",
                                             "srv", "safe_read", {}, created_at=value)
        for ttl in (0, -1, float("nan"), float("inf"), True, "10"):
            with self.subTest(ttl=ttl), self.assertRaises(ValueError):
                self.engine.issue_provenance(self.origin, self.target, ttl=ttl)

    def test_nonfinite_interaction_timestamp_cannot_bypass_validation(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                self.setUp()
                verdict = self.use(timestamp=value)
                self.assertEqual(verdict.action, Action.ISOLATE)
                self.assertIn("invalid provenance timestamp", verdict.reasons)

    def test_current_event_must_descend_from_origin(self):
        self.engine.causal_graph.history[self.target.session_id].clear()
        verdict = self.use()
        self.assertEqual(verdict.action, Action.ISOLATE)
        self.assertIn("origin is not a causal ancestor of current event", verdict.reasons)

    def test_same_origin_issuance_has_distinct_identity(self):
        other = self.engine.issue_provenance(self.origin, self.target, ttl=10)
        self.assertNotEqual(self.claim.claim_id, other.claim_id)

    def test_actual_causal_predecessor_bound(self):
        self.assertEqual(self.claim.predecessor, self.prior)
        self.assertTrue(self.check().valid)
        with self.assertRaisesRegex(ValueError, "unknown originating"):
            self.engine.provenance.issue("missing", "Read record 1", "session",
                                         "srv", "safe_read", {})
        self.engine.causal_graph.edges = [
            edge for edge in self.engine.causal_graph.edges
            if not (edge.source == self.prior and edge.target == self.origin)]
        self.assertEqual(self.check().reason, "invalid causal predecessor relation")

    def test_causal_node_context_and_content_tampering(self):
        for field, value in (("session_id", "other"), ("server_id", "other"),
                             ("digest", "tampered")):
            with self.subTest(field=field):
                self.setUp()
                setattr(self.engine.causal_graph.nodes[self.prior], field, value)
                self.assertFalse(self.check().valid)
        self.setUp()
        del self.engine.causal_graph.nodes[self.origin]
        self.assertFalse(self.check().valid)

    def test_substituted_claim_predecessor_rejected(self):
        self.engine.provenance.claims[self.claim.claim_id] = replace(
            self.claim, predecessor=self.origin)
        self.assertEqual(self.check().reason, "provenance claim tampered")

    def test_unrelated_predecessor_not_accepted(self):
        unrelated = self.engine.evaluate(replace(self.target, session_id="other"), learn=False)
        with self.assertRaisesRegex(ValueError, "predecessor context"):
            self.engine.provenance.issue(self.origin, "Read record 1", "session", "srv",
                                         "safe_read", {}, predecessor=unrelated.trace_id)
        with self.assertRaisesRegex(ValueError, "predecessor relation"):
            self.engine.provenance.issue(self.origin, "Read record 1", "session", "srv",
                                         "safe_read", {}, predecessor=self.origin)

    def test_blocked_origin_cannot_issue_claim(self):
        rejected = self.engine.evaluate(replace(self.target, provenance_id="unknown"))
        with self.assertRaisesRegex(ValueError, "accepted engine event"):
            self.engine.issue_provenance(rejected.trace_id, self.target)

    def test_malformed_ids_and_arguments(self):
        for value in ("", [], {}, 123):
            with self.subTest(value=value):
                verdict = self.engine.evaluate(replace(self.target, provenance_id=value))
                self.assertEqual(verdict.action, Action.ISOLATE)
                self.assertIn("malformed provenance ID", verdict.reasons)
        self.assertFalse(self.check(arguments={"value": float("nan")}).valid)
        self.assertFalse(self.check(arguments={"value": object()}).valid)

    def test_replay_cannot_be_reset_by_editing_uses(self):
        self.use()
        self.engine.provenance.claims[self.claim.claim_id] = self.claim
        self.assertFalse(self.check().valid)

    def test_concurrent_single_use(self):
        values = dict(intent="Read record 1", session_id="session", server_id="srv",
                      tool_name="safe_read", arguments={"record_id": "1"})
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.engine.provenance.validate(
                self.claim.claim_id, **values), range(16)))
        self.assertEqual(sum(result.valid for result in results), 1)
        self.assertEqual(sum(result.reason == "provenance replay" for result in results), 15)

    def test_learning_override_and_attestation_do_not_trust_invalid_claim(self):
        for enrollment, quarantine in ((False, True), (True, True), (True, False)):
            with self.subTest(enrollment=enrollment, quarantine=quarantine):
                engine = SentinelEngine(config=EngineConfig(quarantine=quarantine))
                engine.attestation.enroll("srv", "v1")
                challenge = engine.attestation.issue("srv")
                echo = hashlib.sha256(f"{challenge.nonce}:v1".encode()).hexdigest()
                event = replace(self.target, provenance_id="missing", capability_digest="v1",
                                attestation_challenge_id=challenge.challenge_id, attestation_echo=echo)
                verdict = engine.evaluate(event, trusted_enrollment=enrollment)
                self.assertEqual(verdict.action, Action.ISOLATE)
                self.assertEqual(verdict.components["attestation"], 0)
                self.assertFalse(verdict.baseline_updated)
                self.assertEqual(engine.profiles["srv"].trusted_count, 0)
                self.assertEqual(engine.profiles["srv"].scaler.count, 0)
                self.assertLess(verdict.trust_score, .75)
                self.assertEqual(len(engine.quarantine["srv"]), 1)

    def test_checkpoint_copy_preserves_graph_and_replay(self):
        self.use()
        cloned = copy.deepcopy(self.engine)
        self.assertIs(cloned.provenance.graph, cloned.causal_graph)
        verdict = cloned.evaluate(replace(self.target, provenance_id=self.claim.claim_id))
        self.assertIn("provenance replay", verdict.reasons)

    def test_legacy_positional_interaction_roundtrip(self):
        legacy = Interaction("s", "t", {}, None, 1, "Read", True, False, "session", 100)
        self.assertIsNone(legacy.provenance_id)
        from dataclasses import asdict
        self.assertEqual(legacy, Interaction.from_dict(asdict(legacy)))


class ProvenanceExperimentTests(unittest.TestCase):
    def run_registered(self, name):
        with tempfile.TemporaryDirectory() as output, patch(
                "sentinel.scenarios.run_provenance_scenario",
                side_effect=AssertionError("experiment must not use helper")):
            result = run_experiment(ExperimentConfig(
                scenario=name, training_events=20, validation_events=4, output=output))[0]
            self.assertTrue(Path(output, name, result["experiment_id"] + ".json").exists())
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["baseline_state"]["trusted_before_test"],
                         result["baseline_state"]["trusted_after_test"])
        self.assertTrue(all(row["trace_id"] and row["forwarded"]
                            for row in result["decisions"] if not row["malicious"]))
        self.assertTrue(all(not row["forwarded"]
                            for row in result["decisions"] if row["malicious"]))
        return result

    def test_registered_delayed_misuse_is_stale_not_replay(self):
        result = self.run_registered("delayed_causal_misuse")
        issued, control_issued, control, attack = result["decisions"]
        for row in (issued, control_issued, control):
            self.assertIn(row["decision"], {"allow", "observe"})
        claim = issued["provenance"]["issued"]
        self.assertEqual(attack["provenance"]["claim_id"], claim["claim_id"])
        self.assertEqual(attack["provenance"]["before"]["uses"], 0)
        self.assertGreaterEqual(attack["provenance"]["time"], claim["expires_at"])
        self.assertEqual(attack["tool"], "simulated_delete")
        self.assertEqual(attack["decision"], "isolate")
        self.assertEqual(attack["provenance"]["validation"]["reason"], "stale provenance")
        self.assertNotIn("provenance replay", attack["reasons"])
        control_claim = control_issued["provenance"]["issued"]
        self.assertEqual(control["provenance"]["claim_id"], control_claim["claim_id"])
        self.assertLess(control_claim["created_at"], control["provenance"]["time"])
        self.assertLess(control["provenance"]["time"], control_claim["expires_at"])
        self.assertTrue(control["provenance"]["validation"]["valid"])
        self.assertEqual(result["metrics"]["fn"], 0)
        self.assertEqual(result["metrics"]["fp"], 0)

    def test_registered_replay_rejects_second_use_before_expiry(self):
        result = self.run_registered("provenance_replay")
        issued, first, replay = result["decisions"]
        claim = issued["provenance"]["issued"]
        self.assertIn(first["decision"], {"allow", "observe"})
        self.assertTrue(first["provenance"]["validation"]["valid"])
        self.assertEqual(first["provenance"]["before"]["uses"], 0)
        self.assertEqual(first["provenance"]["claim_id"], claim["claim_id"])
        self.assertEqual(replay["provenance"]["claim_id"], claim["claim_id"])
        self.assertEqual(replay["provenance"]["before"]["uses"], 1)
        self.assertLess(replay["provenance"]["time"], claim["expires_at"])
        self.assertEqual(replay["decision"], "isolate")
        self.assertEqual(replay["provenance"]["validation"]["reason"], "provenance replay")
        self.assertEqual(result["metrics"]["fn"], 0)
        self.assertEqual(result["metrics"]["fp"], 0)


if __name__ == "__main__":
    unittest.main()
