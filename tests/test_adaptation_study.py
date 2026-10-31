import unittest
from sentinel_research.adaptation_study import build_streams, summarize_events


class AdaptationStudyTests(unittest.TestCase):
    def test_matched_streams_and_hidden_attack_intent(self):
        streams = build_streams(17, 30)
        self.assertEqual(streams, build_streams(17, 30))
        self.assertFalse(any(row.malicious for row in streams['clean_drift']))
        for index, attack in enumerate(streams['mixed']):
            clean = streams['clean_drift'][index]
            self.assertEqual(attack.interaction, clean.interaction)
        single = {row.independent_identity for row in streams['mixed'] if row.malicious}
        colluding = {row.independent_identity for row in streams['mixed_colluding'] if row.malicious}
        self.assertEqual(len(single), 1)
        self.assertGreater(len(colluding), 1)
        self.assertTrue(all(not row.malicious for row in streams['mixed'][:10]))

    def test_undefined_metrics_and_batch_update_attribution(self):
        rows = [{'fixture_malicious': False, 'intervened': False, 'model_updates': 3}]
        summary = summarize_events(rows)
        self.assertIsNone(summary['malicious_intervention_rate'])
        self.assertIsNone(summary['contamination_rate'])
        self.assertEqual(summary['model_updates'], 3)

    def test_reject_short_stream(self):
        with self.assertRaises(ValueError):
            build_streams(1, 3)
