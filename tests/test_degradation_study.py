from dataclasses import replace
import tempfile
from pathlib import Path
import json
import unittest
from unittest.mock import patch

from sentinel_research.degradation_study import fixtures, response, probe_profiles, model_digest, run_study
from sentinel.features import extract_features
from sentinel_research.experiment import ExperimentConfig
from sentinel_research.novelty_experiment import NoveltyLiveExperiment


class DegradationStudyTests(unittest.TestCase):
    def test_attacks_change_features_and_preserve_matched_calls(self):
        train, streams, probes = fixtures(31001)
        self.assertEqual((train, streams, probes), fixtures(31001))
        self.assertEqual(sum(c.malicious for c in probes), 4)
        for name, cases in streams.items():
            for clean, case in zip(streams['clean'], cases):
                self.assertEqual(clean.interaction, case.interaction)
                if case.malicious:
                    a = replace(case.interaction, response=response('3.0'))
                    b = replace(case.interaction, response=case.response_override)
                    self.assertFalse((extract_features(a) == extract_features(b)).all())
        self.assertEqual(sum(c.malicious for c in streams['gradual_after_promotion']), 9)

    def test_live_probes_are_repeatable_and_do_not_train_source_model(self):
        train, _, probes = fixtures(31001)
        with NoveltyLiveExperiment(ExperimentConfig(training_events=100), 'full') as live:
            live.run_phase(train, True, 1000, True)
            checkpoint = live.checkpoint()
            profiles = checkpoint[0].profiles
            before = model_digest(profiles)
            first = probe_profiles(live, checkpoint, profiles, probes)
            second = probe_profiles(live, checkpoint, profiles, probes)
            self.assertEqual(first, second)
            self.assertEqual(before, model_digest(profiles))
            self.assertTrue(all(r['model_sha256'] == before for r in first))

    def test_failed_run_retains_status_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'study'
            with patch('sentinel_research.degradation_study.NoveltyLiveExperiment.__enter__', side_effect=TimeoutError('fixture')):
                with self.assertRaises(TimeoutError):
                    run_study(output, (31001,))
            self.assertEqual(json.loads((output / 'execution.json').read_text())['status'], 'failed')
            self.assertFalse((output / 'summary.json').exists())
            with self.assertRaises(FileExistsError):
                run_study(output, (31001,))
