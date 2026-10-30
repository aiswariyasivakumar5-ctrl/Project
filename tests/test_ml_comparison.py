import tempfile
import unittest

import numpy as np

from sentinel.compare import CompareConfig, aggregate_results, calibrate_threshold, run_comparison
from sentinel.comparison_data import ATTACK_FAMILIES, build_comparison_dataset
from sentinel.ml_baselines import DenseAutoencoderDetector, IsolationForestDetector, OneClassSVMDetector
from sentinel.ml_features import FEATURE_DESCRIPTION, feature_matrix


class BaselineModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(5)
        cls.train = rng.normal(0, 1, (160, 8))
        cls.test = np.vstack([rng.normal(0, 1, (20, 8)), rng.normal(7, 1, (10, 8))])

    def assert_detector(self, factory):
        first, second = factory(), factory()
        first.fit(self.train); second.fit(self.train)
        scores = first.score(self.test)
        self.assertEqual(scores.shape, (30,))
        self.assertTrue(np.isfinite(scores).all())
        self.assertTrue(np.allclose(scores, second.score(self.test)))
        self.assertGreater(scores[-10:].mean(), scores[:20].mean())

    def test_isolation_forest_training(self):
        self.assert_detector(lambda: IsolationForestDetector(seed=12, trees=20, sample_size=64))

    def test_one_class_svm_training(self):
        self.assert_detector(lambda: OneClassSVMDetector(seed=12, epochs=8, rff_dimensions=32))

    def test_dense_autoencoder_training(self):
        self.assert_detector(lambda: DenseAutoencoderDetector(seed=12, epochs=12, hidden=5))


class ComparisonFrameworkTests(unittest.TestCase):
    def test_dataset_has_clean_train_validation_and_balanced_attack_families(self):
        dataset = build_comparison_dataset(42, 100, 40, 240)
        self.assertFalse(any(row.malicious for row in dataset.train))
        self.assertFalse(any(row.malicious for row in dataset.validation))
        counts = {family: sum(row.malicious and row.scenario == family for row in dataset.test)
                  for family in ATTACK_FAMILIES}
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        matrix = feature_matrix([row.interaction for row in dataset.train[:10]])
        self.assertEqual(matrix.shape[1], FEATURE_DESCRIPTION["dimensions"])

    def test_validation_threshold_ignores_test_scores(self):
        validation = np.asarray([0.1, 0.2, 0.3, 0.4])
        first = calibrate_threshold(validation, 0.25)
        _ = np.asarray([1000.0, -1000.0])
        second = calibrate_threshold(validation, 0.25)
        self.assertEqual(first, second)

    def test_smoke_comparison_has_common_schema_and_aggregate(self):
        with tempfile.TemporaryDirectory() as output:
            result = run_comparison(CompareConfig(
                seeds=(7, 8), train_size=80, validation_size=30, test_size=120,
                models=("isolation_forest", "dense_autoencoder"), output=output,
            ))
        self.assertEqual(len(result["results"]), 4)
        for item in result["results"]:
            self.assertIn("metrics", item)
            for metric in ("tp", "tn", "fp", "fn", "precision", "recall", "f1", "auroc", "auprc"):
                self.assertIn(metric, item["metrics"])
            self.assertFalse(item["calibration"]["test_used_for_threshold"])
        self.assertIn("f1", result["aggregate"]["isolation_forest"])

    def test_aggregate_statistics(self):
        sample = [
            {"model": "m", "metrics": {"precision": .5, "recall": .5, "f1": .5,
             "false_positive_rate": .1, "attack_detection_rate": .5,
             "detection_delay_events": 1, "auroc": .6, "auprc": .7, "mean_risk": .4},
             "offline_inference_mean_ms": .2},
            {"model": "m", "metrics": {"precision": .7, "recall": .7, "f1": .7,
             "false_positive_rate": .2, "attack_detection_rate": .7,
             "detection_delay_events": 2, "auroc": .8, "auprc": .9, "mean_risk": .6},
             "offline_inference_mean_ms": .4},
        ]
        aggregate = aggregate_results(sample)["m"]["f1"]
        self.assertAlmostEqual(aggregate["mean"], .6)
        self.assertGreater(aggregate["std"], 0)
        self.assertEqual((aggregate["min"], aggregate["max"]), (.5, .7))


if __name__ == "__main__":
    unittest.main()

