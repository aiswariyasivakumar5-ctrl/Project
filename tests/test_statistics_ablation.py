import json
import tempfile
import unittest
from pathlib import Path

from sentinel.ablation import ABLATIONS, AblationConfig, run_ablation_matrix
from sentinel.statistics import (
    bootstrap_mean_ci,
    exact_paired_sign_flip,
    holm_adjust,
    wilcoxon_signed_rank,
)
from sentinel.plots import bar_chart, line_chart


class StatisticalTests(unittest.TestCase):
    def test_bootstrap_is_deterministic_and_contains_mean(self):
        first = bootstrap_mean_ci([0.5, 0.6, 0.7, 0.8, 0.9], seed=7, resamples=2000)
        second = bootstrap_mean_ci([0.5, 0.6, 0.7, 0.8, 0.9], seed=7, resamples=2000)
        self.assertEqual(first, second)
        self.assertLessEqual(first.lower, first.estimate)
        self.assertGreaterEqual(first.upper, first.estimate)

    def test_exact_paired_sign_flip(self):
        result = exact_paired_sign_flip([3, 4, 5], [1, 2, 3])
        self.assertAlmostEqual(result["mean_difference"], 2.0)
        self.assertAlmostEqual(result["p_value_two_sided"], 0.25)

    def test_wilcoxon_signed_rank_exact_and_effect_size(self):
        # 5 strictly positive pairs: p = 2 / 2^5 = 0.0625, effect size r = 1.0
        res = wilcoxon_signed_rank([1, 2, 3, 4, 5], [0, 0, 0, 0, 0])
        self.assertEqual(res["statistic"], 0.0)
        self.assertEqual(res["w_plus"], 15.0)
        self.assertEqual(res["effect_size_r"], 1.0)
        self.assertAlmostEqual(res["p_value_two_sided"], 0.0625)

        # 6 pairs with mixed signs
        res2 = wilcoxon_signed_rank([5, 4, 3, 2, 1, 0], [0, 1, 2, 3, 4, 5])
        self.assertEqual(res2["effect_size_r"], 0.0)
        self.assertAlmostEqual(res2["p_value_two_sided"], 1.0)

        # 20 strictly positive pairs: p = 2 / 2^20 = 1.9073e-6 < 0.001
        res20 = wilcoxon_signed_rank(list(range(1, 21)), [0] * 20)
        self.assertEqual(res20["effect_size_r"], 1.0)
        self.assertAlmostEqual(res20["p_value_two_sided"], 2.0 / (2 ** 20))
        self.assertLess(res20["p_value_two_sided"], 0.0001)

    def test_holm_adjustment_is_monotone_and_bounded(self):
        adjusted = holm_adjust({"a": .01, "b": .03, "c": .2})
        self.assertTrue(all(0 <= value <= 1 for value in adjusted.values()))
        self.assertLessEqual(adjusted["a"], adjusted["b"])

    def test_dependency_free_svg_charts_are_valid_artifacts(self):
        line = line_chart("ROC", {"model": [(0, 0), (1, 1)]}, "FPR", "TPR")
        bars = bar_chart("F1", {"full": .8, "ablated": .6}, "F1", 1.0)
        self.assertTrue(line.startswith("<svg"))
        self.assertIn("polyline", line)
        self.assertTrue(bars.endswith("</svg>"))


class AblationTests(unittest.TestCase):
    def test_all_real_ablation_variants_exist(self):
        self.assertEqual(set(ABLATIONS), {"full", "without_intent", "without_causal",
                                         "without_attestation", "without_uncertainty",
                                         "without_quarantine"})

    def test_small_matrix_has_common_results_statistics_and_adaptive_curves(self):
        with tempfile.TemporaryDirectory() as output:
            result = run_ablation_matrix(AblationConfig(
                seeds=(17,), train_size=40, validation_size=20, test_size=60,
                output=output, bootstrap_resamples=500,
            ))
            self.assertEqual(set(result["aggregate"]), set(ABLATIONS))
            self.assertIn("confidence_intervals", result["statistics"])
            self.assertIn("gradual_poisoning", result["adaptive_curves"]["without_quarantine"])
            self.assertTrue(Path(output, "aggregate", "statistics.json").exists())
            stored = json.loads(Path(output, "aggregate", "statistics.json").read_text())
            self.assertIn("paired_full_minus_ablation", stored)


if __name__ == "__main__":
    unittest.main()
