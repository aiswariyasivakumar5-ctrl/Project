import unittest
from unittest.mock import patch

from sentinel_research.experiment import ExperimentConfig
from sentinel_research.novelty_experiment import NoveltyLiveExperiment
from sentinel_research.novelty_scenarios import build_novelty_scenarios


class DeniedOriginTests(unittest.TestCase):
    def test_denied_origin_is_recorded_without_minting_claim(self):
        cases = build_novelty_scenarios(42, 3)['provenance_replay'].scenario.cases
        with NoveltyLiveExperiment(ExperimentConfig(), 'full') as live:
            gateway = live.gateways[cases[0].interaction.server_id]
            with patch.object(gateway, '_preflight_block', return_value='fixture denial'):
                _, details = live.run_phase(cases, False, 20000)
            self.assertEqual(len(details), len(cases))
            self.assertIsNone(details[0]['provenance']['issued'])
            self.assertEqual(details[0]['provenance']['issuance_error'],
                             'provenance origin must be an accepted engine event')
            self.assertFalse(live.engine.provenance.claims)
            for row in details[1:]:
                self.assertTrue(row['provenance']['claim_id'].startswith('unissued-fixture-'))
                self.assertFalse(row['provenance']['claim_available_before_use'])
                self.assertFalse(row['forwarded'])

    def test_unissued_claim_is_sent_and_rejected_without_preflight_override(self):
        cases = build_novelty_scenarios(42, 3)['provenance_replay'].scenario.cases
        with NoveltyLiveExperiment(ExperimentConfig(), 'baseline') as live:
            with patch.object(live.engine, 'issue_provenance', side_effect=ValueError(
                    'provenance origin must be an accepted engine event')):
                _, details = live.run_phase(cases, False, 20000)
            self.assertFalse(details[1]['forwarded'])
            self.assertFalse(details[1]['provenance']['validation']['valid'])
            self.assertIsNone(details[1]['provenance']['before'])

    def test_other_issuer_errors_still_fail_the_run(self):
        cases = build_novelty_scenarios(42, 3)['provenance_replay'].scenario.cases
        with NoveltyLiveExperiment(ExperimentConfig(), 'baseline') as live:
            with patch.object(live.engine, 'issue_provenance', side_effect=ValueError('unexpected bug')):
                with self.assertRaisesRegex(ValueError, 'unexpected bug'):
                    live.run_phase(cases, False, 20000)
