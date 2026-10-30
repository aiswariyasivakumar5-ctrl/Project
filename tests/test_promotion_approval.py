import unittest
from dataclasses import replace

from sentinel.approvals import ReviewApprovals
from sentinel.models import Interaction
from sentinel.novelty import NoveltySentinelEngine
from sentinel.provenance import ScenarioClock


class PromotionApprovalTests(unittest.TestCase):
    def setUp(self):
        self.engine = NoveltySentinelEngine()
        self.engine.base.attestation.enroll('srv', 'manifest')
        self.event = Interaction('srv', 'safe_read', {'record_id': '1', 'format': 'compact'},
            {}, 10, 'Read record 1', capability_digest='manifest')

    def run_sessions(self, count=3):
        for i in range(count):
            verdict = self.engine.evaluate(replace(self.event, session_id=str(i)),
                attested=True, independent_session=f'actor-{i}')
        return verdict

    def approve(self, event=None):
        self.engine.approve_promotion(event or self.event, reviewer='operator', evidence_ref='change-17')

    def test_compromised_independent_actors_do_not_promote_without_review(self):
        verdict = self.run_sessions(8)
        self.assertEqual(verdict.memory_disposition, 'awaiting-approval')
        self.assertEqual(self.engine.base.profiles['srv'].trusted_count, 0)
        self.assertEqual(len(next(iter(self.engine.memory.candidates.values())).sessions), 3)

    def test_reviewed_upgrade_promotes_and_records_single_use_evidence(self):
        self.approve()
        verdict = self.run_sessions()
        self.assertEqual(verdict.memory_disposition, 'promoted')
        self.assertEqual(verdict.promoted_events, 3)
        self.assertEqual(verdict.base.provenance['promotion_review']['evidence_ref'], 'change-17')
        self.assertEqual(self.engine.approvals.entries, {})

    def test_approval_does_not_replace_independence_or_attestation(self):
        self.approve()
        for _ in range(5):
            verdict = self.engine.evaluate(self.event, attested=True, independent_session='same')
        self.assertEqual(verdict.memory_disposition, 'candidate')
        self.assertEqual(self.engine.base.profiles['srv'].trusted_count, 0)

    def test_review_scope_is_bound_to_intent_shape_and_manifest(self):
        self.approve(replace(self.event, user_intent='Read record 2'))
        self.assertEqual(self.run_sessions().memory_disposition, 'awaiting-approval')
        with self.assertRaises(ValueError):
            self.approve(replace(self.event, capability_digest='changed'))

    def test_expired_review_cannot_promote(self):
        clock = ScenarioClock()
        self.engine.approvals = ReviewApprovals(clock=clock)
        self.approve()
        clock.value += 300
        self.assertEqual(self.run_sessions().memory_disposition, 'awaiting-approval')

    def test_revocation_removes_learning_authority(self):
        self.approve()
        self.run_sessions()
        self.engine.revoke_promotion(self.event)
        before = self.engine.base.profiles['srv'].trusted_count
        self.assertEqual(self.run_sessions().memory_disposition, 'rejected')
        self.assertEqual(self.engine.base.profiles['srv'].trusted_count, before)

    def test_clock_rollback_fails_closed(self):
        clock = ScenarioClock()
        registry = ReviewApprovals(clock=clock)
        registry.grant('key', reviewer='operator', evidence_ref='change')
        clock.value -= 1
        self.assertIsNone(registry.get('key'))
        clock.value += 1
        self.assertIsNone(registry.get('key'))

    def test_old_attestation_does_not_authorize_current_promotion(self):
        self.approve()
        self.engine.evaluate(self.event, attested=True, independent_session='one')
        self.engine.evaluate(self.event, attested=False, independent_session='two')
        verdict = self.engine.evaluate(self.event, attested=False, independent_session='three')
        self.assertEqual(verdict.memory_disposition, 'awaiting-attestation')
        self.assertEqual(self.engine.base.profiles['srv'].trusted_count, 0)
        verdict = self.engine.evaluate(self.event, attested=True, independent_session='four')
        self.assertEqual(verdict.memory_disposition, 'promoted')

    def test_failed_manifest_check_never_trains_even_in_enrollment(self):
        bad = replace(self.event, capability_digest='different')
        verdict = self.engine.evaluate(bad, trusted_enrollment=True, attested=True)
        self.assertEqual(verdict.memory_disposition, 'rejected')
        self.assertEqual(self.engine.base.profiles['srv'].trusted_count, 0)

    def test_incident_revokes_review_and_records_evidence(self):
        self.approve()
        verdict = self.engine.evaluate(replace(self.event, success=False), learn=False)
        self.assertEqual(self.engine.approvals.entries, {})
        self.assertEqual(verdict.base.provenance['review_invalidation']['revoked']['promotion'], 1)


if __name__ == '__main__':
    unittest.main()
