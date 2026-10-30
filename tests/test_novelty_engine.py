import unittest

from sentinel.models import Action, Interaction
from sentinel.novelty import NoveltySentinelEngine


def make(tool="safe_read", intent="Read record", session="s", side=False, cap="v1"):
    return Interaction("crm", tool, {"record_id": "1001"}, {"status": "ok"}, 10,
                       intent, True, side, session, capability_digest=cap)


class NoveltyTests(unittest.TestCase):
    def engine(self):
        engine = NoveltySentinelEngine(minimum_sessions=3)
        for i in range(25): engine.evaluate(make(session=f"e{i}"), trusted_enrollment=True, attested=True)
        return engine

    def test_capability_specific_restriction(self):
        engine = self.engine()
        verdict = engine.evaluate(make("delete_all", "Read record", "attack", True))
        self.assertIn(verdict.action, {Action.SANDBOX, Action.ISOLATE})
        self.assertLess(engine.capabilities.states[("crm", "delete_all")].trust, .75)
        self.assertGreater(engine.capabilities.states[("crm", "safe_read")].trust, .75)

    def test_promotion_needs_independent_sessions_and_attestation(self):
        engine = self.engine()
        call = lambda s: make("new_lookup", "Use new lookup", s, cap="v1")
        engine.approve_promotion(call('review'), reviewer='test operator', evidence_ref='test change review')
        self.assertEqual(engine.evaluate(call("one"), attested=True).memory_disposition, "candidate")
        self.assertEqual(engine.evaluate(call("one")).memory_disposition, "candidate")
        self.assertEqual(engine.evaluate(call("two")).memory_disposition, "candidate")
        promoted = engine.evaluate(call("three"), attested=True)
        self.assertEqual(promoted.memory_disposition, "promoted")
        self.assertGreaterEqual(promoted.promoted_events, 3)

    def test_high_risk_candidate_is_rejected(self):
        engine = self.engine(); bad = make("export_secrets", "Read record", "p", True, "v2")
        self.assertEqual(engine.evaluate(bad, attested=True).memory_disposition, "rejected")
        self.assertNotIn(engine.memory.fingerprint(bad), engine.memory.trusted[("crm", "export_secrets")])

    def test_hash_linked_claim_is_retrievable(self):
        engine = self.engine(); verdict = engine.evaluate(make("delete_all", "Read record", "t", True))
        self.assertEqual(engine.provenance.trace(verdict.claim_id)["claim_id"], verdict.claim_id)
        self.assertGreater(verdict.counterfactual_risk, .5)


if __name__ == "__main__": unittest.main()
