import hashlib
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

from sentinel.metrics import Observation
from sentinel.novelty_experiment import (NoveltyLiveExperiment, NoveltyStudyConfig,
    ValidationCalibration, run_novelty_study)


def observation(score, malicious=False):
    return Observation(malicious, False, score, .75, .2, 1, 1, 0)


class CalibrationTests(unittest.TestCase):
    def test_higher_quantile_and_strict_ties(self):
        calibration = ValidationCalibration.fit([observation(x) for x in (0, .2, .4, .6, 1)], .25)
        self.assertEqual(calibration.threshold, .6)
        self.assertEqual(calibration.artifact()['observed_validation_fpr'], .2)
        metrics = calibration.metrics([observation(.6), observation(.61, True)])
        self.assertEqual((metrics['tn'], metrics['tp']), (1, 1))

    def test_invalid_or_attack_labeled_validation_rejected(self):
        for rows in ([], [observation(.1, True)], [observation(float('nan'))],
                     [observation(float('inf'))], [observation(-.1)], [observation(1.1)],
                     [observation(True)]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                ValidationCalibration.fit(rows, .01)
        for target in (0, 1, -.1, float('nan'), True):
            with self.assertRaises(ValueError):
                ValidationCalibration.fit([observation(.1)], target)

    def test_threshold_immutable_and_independent_of_test_labels(self):
        calibration = ValidationCalibration.fit([observation(.1), observation(.2)], .01)
        before = calibration.artifact()
        calibration.metrics([observation(0), observation(1, True)])
        calibration.metrics([observation(0, True), observation(1)])
        self.assertEqual(before, calibration.artifact())
        with self.assertRaises(FrozenInstanceError):
            calibration.threshold = 0

    def test_invalid_config_does_not_reserve_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'invalid'
            with self.assertRaises(ValueError):
                run_novelty_study(NoveltyStudyConfig(output=str(root), validation_fpr=1))
            self.assertFalse(root.exists())

    def test_live_calibration_saved_before_test_and_does_not_change_gateway(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = NoveltyStudyConfig(variants=('full',), scenarios=('legitimate_upgrade',),
                training_events=20, validation_events=8, test_events=3, output=str(root / 'plain'))
            run_novelty_study(base)
            calibrated = replace(base, output=str(root / 'calibrated'), validation_fpr=.01)
            original = NoveltyLiveExperiment.run_phase
            checked = []

            def checked_phase(live, cases, learn, start_id, trusted_enrollment=False):
                if start_id == 20_000:
                    artifact = root / 'calibrated/calibration/full/seed-42-calibration.json'
                    self.assertTrue(artifact.exists())
                    checked.append(artifact.read_bytes())
                return original(live, cases, learn, start_id, trusted_enrollment)

            with patch.object(NoveltyLiveExperiment, 'run_phase', checked_phase):
                run_novelty_study(calibrated)
            self.assertEqual(len(checked), 2)
            self.assertEqual(checked[0], checked[1])
            artifact = json.loads(checked[0])
            encoded = json.dumps(artifact['validation_scores'], separators=(',', ':')).encode()
            self.assertEqual(hashlib.sha256(encoded).hexdigest(), artifact['validation_scores_sha256'])
            self.assertFalse(artifact['test_used_for_threshold'])
            for phase in ('test', 'adaptive'):
                relative = f'full/legitimate_upgrade/seed-42-{phase}.json'
                plain = json.loads((root / 'plain' / relative).read_text())
                row = json.loads((root / 'calibrated' / relative).read_text())
                self.assertEqual(row['score_threshold'], artifact['threshold'])
                self.assertEqual(row['learning_after'], plain['learning_after'])
                self.assertEqual([(e['risk'], e['decision'], e['model_updates']) for e in row['decisions']],
                                 [(e['risk'], e['decision'], e['model_updates']) for e in plain['decisions']])
                if phase == 'test':
                    self.assertEqual(row['learning_before'], row['learning_after'])
                threshold = row['score_threshold']
                self.assertEqual(row['score_metrics']['fp'], sum(not e['malicious'] and e['risk'] > threshold
                                                               for e in row['decisions']))


if __name__ == '__main__':
    unittest.main()
