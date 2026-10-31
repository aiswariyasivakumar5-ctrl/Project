import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sentinel_research.matched_poisoning import build_matched, learning_delays, review_index, run_study
from sentinel.features import extract_features


class MatchedPoisoningTests(unittest.TestCase):
    def test_matched_actual_wrong_answers_preserve_response_shape(self):
        train, streams = build_matched(31001)
        self.assertEqual((train, streams), build_matched(31001))
        self.assertEqual(len(train), 100)
        for rows in streams.values():
            for benign, case in zip(streams['clean'], rows):
                self.assertEqual(benign.interaction, case.interaction)
                if case.malicious:
                    content = case.response_override['content'][0]['text']
                    self.assertNotEqual(float(content), sum(case.interaction.arguments.values()))
                    self.assertEqual(len(content), len('3.0'))
                    correct = replace(case.interaction, response={'content': [{'type': 'text', 'text': '3.0'}]})
                    wrong = replace(case.interaction, response=case.response_override)
                    self.assertTrue((extract_features(correct) == extract_features(wrong)).all())
                else:
                    self.assertIsNone(case.response_override)
        self.assertEqual(sum(c.malicious for c in streams['mixed']), 4)
        self.assertEqual(sum(c.malicious for c in streams['late_sparse']), 3)
        self.assertEqual(len({c.independent_identity for c in streams['single_identity']}), 1)
        self.assertEqual(len({c.independent_identity for c in streams['colluding']}), 12)

    def test_seeds_change_enrollment_order_not_inventory(self):
        a, _ = build_matched(31001)
        b, _ = build_matched(31002)
        self.assertNotEqual(a, b)
        self.assertEqual(sorted(c.interaction.session_id for c in a), sorted(c.interaction.session_id for c in b))

    def test_review_schedule_is_fixed_and_explicitly_oracle(self):
        self.assertEqual(review_index('oracle_review', 'clean'), 0)
        self.assertEqual(review_index('delayed_oracle', 'clean'), 3)
        self.assertIsNone(review_index('oracle_review', 'mixed'))
        self.assertEqual(review_index('mistaken_review', 'colluding'), 0)
        self.assertIsNone(review_index('withheld', 'clean'))

    def test_delays_follow_learning_source_not_current_call_label(self):
        rows = [{'index': 0, 'fixture_malicious': False, 'learned_events': []},
                {'index': 1, 'fixture_malicious': True, 'learned_events': [
                    {'fixture_malicious': False}, {'fixture_malicious': True}]}]
        result = learning_delays(rows)
        self.assertEqual(result['benign_learning_delay'], 1)
        self.assertEqual(result['first_malicious_learning_index'], 1)
        self.assertFalse(result['benign_learning_censored'])
        rows[1]['learned_events'] = []
        self.assertTrue(learning_delays(rows)['benign_learning_censored'])

    def test_failure_retained_and_output_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'run'
            with patch('sentinel_research.matched_poisoning.NoveltyLiveExperiment.__enter__', side_effect=TimeoutError('fixture')):
                with self.assertRaises(TimeoutError):
                    run_study(output, (31001,))
            state = json.loads((output / 'execution.json').read_text())
            self.assertEqual(state['status'], 'failed')
            self.assertEqual(state['completed'], 0)
            self.assertFalse((output / 'summary.json').exists())
            with self.assertRaises(FileExistsError):
                run_study(output, (31001,))

    def test_invalid_seeds_rejected(self):
        for seeds in ((), (1, 1), (True,)):
            with self.assertRaises(ValueError):
                run_study('must-not-create-matched-test', seeds)
