import copy
import unittest
from sentinel.engine import SentinelEngine
from sentinel.verification_budget_study import workload, run_cell, analyze, feedback_function


class BudgetStudyTests(unittest.TestCase):
    def enrollment(self):
        training, rows = workload(51001, 'clean_drift')
        engine = SentinelEngine()
        for event in training:
            engine.evaluate(event, learn=True, trusted_enrollment=True)
        return engine, rows

    def test_never_learns_and_budget_is_bounded(self):
        engine, rows = self.enrollment()
        before = {k: p.trusted_count for k, p in engine.profiles.items()}
        for policy in ('never', 'first', 'periodic', 'random', 'uncertainty'):
            result, events = run_cell(engine, rows, policy, 'exact', 51001)
            self.assertLessEqual(result['queries'], 24)
            self.assertEqual(result['malicious_updates'], 0)
            if policy == 'never':
                self.assertEqual(result['benign_updates'], 0)
            accepted = [d['source_index'] for e in events for d in e['deliveries'] if d['status'] == 'accepted']
            self.assertEqual(len(accepted), len(set(accepted)))
        self.assertEqual(before, {k: p.trusted_count for k, p in engine.profiles.items()})

    def test_labels_cannot_change_choices_or_learning(self):
        engine, rows = self.enrollment()
        left, details_left = run_cell(engine, rows[:16], 'uncertainty', 'delayed', 51001)
        right, details_right = run_cell(engine, [(e, not flag) for e, flag in rows[:16]], 'uncertainty', 'delayed', 51001)
        for a, b in zip(details_left, details_right):
            for key in ('risk', 'uncertainty', 'eligible', 'selections', 'deliveries'):
                self.assertEqual(a[key], b[key])
        self.assertEqual(left['probe_after'], right['probe_after'])

    def test_incomplete_matrix_is_not_reported(self):
        with self.assertRaisesRegex(ValueError, 'complete unique'):
            analyze([])

    def test_feedback_is_repeatable_and_does_not_mutate(self):
        _, rows = workload(51001, 'mixed')
        for mode in ('exact', 'flipped', 'unavailable'):
            verifier = feedback_function(51001, mode)
            event = rows[2][0]
            snapshot = copy.deepcopy(event)
            self.assertEqual(verifier(event, 2), verifier(event, 2))
            self.assertEqual(event, snapshot)
