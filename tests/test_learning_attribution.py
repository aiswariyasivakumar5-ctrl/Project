import unittest
from dataclasses import replace
from sentinel.engine import SentinelEngine
from sentinel.models import Interaction
from sentinel.novelty import DualMemoryAdapter
from sentinel.workload import WorkloadCase
from sentinel.learning_attribution import LearningAttribution, contamination


class AttributionTests(unittest.TestCase):
    def cases(self):
        return [WorkloadCase(Interaction('s', 'read', {'id': 'record-1'}, {}, 10,
            'Read record', session_id=f'session-{i}'), i == 0, 'fixture', i == 0) for i in range(3)]

    def test_buffered_malicious_event_attributed_on_benign_promotion(self):
        engine, memory, cases = SentinelEngine(), DualMemoryAdapter(), self.cases()
        with LearningAttribution(engine, cases) as observer:
            for index, case in enumerate(cases):
                observer.step = index
                _, promoted = memory.observe(case.interaction, .1, True, False,
                    independent_session=str(index))
                for event in promoted:
                    engine.learn_approved(event, update_sequence=False)
            self.assertEqual([r['source_event_index'] for r in observer.records], [0, 1, 2])
            self.assertTrue(all(r['learning_step'] == 2 for r in observer.records))
            result = contamination([{'model_updates': 3, 'learned_events': observer.records}])
            self.assertEqual(result['contamination_rate'], 1 / 3)
        self.assertEqual(engine.profiles['s'].trusted_count, 3)

    def test_duplicate_sources_rejected(self):
        case = self.cases()[0]
        with self.assertRaises(ValueError):
            LearningAttribution(SentinelEngine(), [case, case])

    def test_failed_learning_not_recorded_and_method_restored(self):
        engine, cases = SentinelEngine(), self.cases()
        original = engine.learn_approved
        with LearningAttribution(engine, cases) as observer:
            with self.assertRaises(ValueError):
                engine.learn_approved(replace(cases[0].interaction, success=False))
            self.assertEqual(observer.records, [])
        self.assertEqual(engine.learn_approved, original)

    def test_missing_or_zero_updates_undefined(self):
        self.assertIsNone(contamination([{'model_updates': 0, 'learned_events': []}])['contamination_rate'])
        self.assertFalse(contamination([{'model_updates': 1, 'learned_events': []}])['attribution_complete'])

    def test_observer_preserves_model_state(self):
        import numpy as np
        observed, control, cases = SentinelEngine(), SentinelEngine(), self.cases()
        with LearningAttribution(observed, cases):
            for case in cases:
                observed.learn_approved(case.interaction)
                control.learn_approved(case.interaction)
        np.testing.assert_array_equal(observed.profiles['s'].autoencoder.w1,
                                      control.profiles['s'].autoencoder.w1)
