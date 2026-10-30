import unittest
from sentinel.adaptation_study import recovery_metrics


class RecoveryMetricsTests(unittest.TestCase):
    def rows(self):
        return [dict(index=i, fixture_malicious=False, intervened=False, learned_events=[])
                for i in range(10)]

    def test_admission_is_not_learning(self):
        result = recovery_metrics(self.rows(), 3)
        self.assertEqual(result['benign_admission_recovery_delay'], 4)
        self.assertTrue(result['learning_recovery_censored'])

    def test_intervention_resets_window(self):
        rows = self.rows()
        rows[6]['intervened'] = True
        self.assertTrue(recovery_metrics(rows, 3)['recovery_censored'])

    def test_replay_uses_original_phase_and_label(self):
        rows = self.rows()
        rows[4]['learned_events'] = [{'fixture_malicious': False, 'source_event_index': 0},
                                   {'fixture_malicious': True, 'source_event_index': 3}]
        self.assertTrue(recovery_metrics(rows, 3)['learning_recovery_censored'])
        rows[8]['learned_events'] = [{'fixture_malicious': False, 'source_event_index': 3}]
        self.assertEqual(recovery_metrics(rows, 3)['first_post_drift_benign_learning_delay'], 5)
