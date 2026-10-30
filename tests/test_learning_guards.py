import unittest
from dataclasses import replace

from sentinel.engine import EngineConfig, SentinelEngine
from sentinel.models import Interaction
from sentinel.novelty import NoveltySentinelEngine
from sentinel.retention import RetentionConfig


def event(**changes):
    return replace(Interaction('srv', 'safe_read', {'record_id': '1'}, {}, 10,
        'Read record 1', capability_digest='enrolled'), **changes)


class LearningGuardTests(unittest.TestCase):
    def test_failed_attestation_cannot_train_through_any_enrollment_path(self):
        for enrollment in (False, True):
            for quarantine in (False, True):
                with self.subTest(enrollment=enrollment, quarantine=quarantine):
                    engine = SentinelEngine(config=EngineConfig(quarantine=quarantine))
                    engine.attestation.enroll('srv', 'enrolled')
                    verdict = engine.evaluate(event(attestation_challenge_id='unknown',
                        attestation_echo='invalid'), trusted_enrollment=enrollment)
                    self.assertEqual(verdict.components['attestation'], 1)
                    self.assertFalse(verdict.baseline_updated)
                    self.assertEqual(engine.profiles['srv'].trusted_count, 0)
                    self.assertEqual(engine.profiles['srv'].scaler.count, 0)
                    self.assertEqual(engine.sequence.previous, {})
                    self.assertEqual(len(engine.quarantine['srv']), 1)

    def test_changed_manifest_is_quarantined_without_reenrollment(self):
        engine = SentinelEngine()
        engine.evaluate(event(), trusted_enrollment=True)
        before = engine.profiles['srv'].trusted_count
        verdict = engine.evaluate(event(capability_digest='changed'), trusted_enrollment=True)
        self.assertFalse(verdict.baseline_updated)
        self.assertEqual(engine.profiles['srv'].trusted_count, before)
        self.assertEqual(engine.attestation.enrolled['srv'], 'enrolled')
        self.assertEqual(engine.profiles['srv'].quarantined_count, 1)

    def test_attestation_ablation_keeps_existing_learning_behavior(self):
        engine = SentinelEngine(config=EngineConfig(attestation=False))
        engine.attestation.enroll('srv', 'enrolled')
        verdict = engine.evaluate(event(capability_digest='changed', attestation_challenge_id='unknown'))
        self.assertEqual(verdict.components['attestation'], 0)
        self.assertTrue(verdict.baseline_updated)

    def test_novelty_capacity_cannot_train_unrecorded_enrollment(self):
        engine = NoveltySentinelEngine(SentinelEngine(retention=RetentionConfig(memory_entries=1)))
        engine.evaluate(event(), trusted_enrollment=True)
        profile = engine.base.profiles['srv']
        before = (profile.trusted_count, profile.scaler.count)
        verdict = engine.evaluate(event(arguments={'record_id': '1', 'format': 'compact'}),
                                  trusted_enrollment=True)
        self.assertEqual(verdict.memory_disposition, 'capacity')
        self.assertFalse(verdict.base.baseline_updated)
        self.assertEqual((profile.trusted_count, profile.scaler.count), before)

    def test_existing_enrolled_shape_still_learns_at_capacity(self):
        engine = NoveltySentinelEngine(SentinelEngine(retention=RetentionConfig(memory_entries=1)))
        engine.evaluate(event(), trusted_enrollment=True)
        verdict = engine.evaluate(event(), trusted_enrollment=True)
        self.assertEqual(verdict.memory_disposition, 'trusted-enrollment')
        self.assertTrue(verdict.base.baseline_updated)
        self.assertEqual(engine.base.profiles['srv'].trusted_count, 2)


if __name__ == '__main__':
    unittest.main()
