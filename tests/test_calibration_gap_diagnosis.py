"""Regression and consistency tests for baseline validation-to-test calibration gap."""
from __future__ import annotations

import unittest
from pathlib import Path

from scripts.diagnose_calibration_gap import diagnose_gap


class BaselineCalibrationGapTest(unittest.TestCase):
    @unittest.skipUnless(Path("results/baselines_20seed").is_dir(), "Requires generated research results")
    def test_diagnosis_summary_consistency(self) -> None:
        report = diagnose_gap()
        self.assertIn("dense_autoencoder", report)
        self.assertIn("lstm", report)
        self.assertIn("transformer", report)
        self.assertIn("sentinel", report)

        # Confirm deep baselines have ~7.7% FPR overall
        dae = report["dense_autoencoder"]
        self.assertAlmostEqual(dae["mean_overall_fpr"], 0.0771, delta=0.005)
        # Confirm cross_server benign FPR is 1.0 (125/125)
        self.assertEqual(dae["scenarios"]["cross_server"]["mean_fp"], 125.0)
        self.assertEqual(dae["scenarios"]["cross_server"]["mean_fpr"], 1.0)
        # Confirm normal test FPR respects ~1% calibration budget
        self.assertLess(dae["scenarios"]["normal"]["mean_fpr"], 0.01)

        # Confirm Sentinel has 0.0 FPR on cross_server and abnormal_sequence
        sentinel = report["sentinel"]
        self.assertEqual(sentinel["scenarios"]["cross_server"]["mean_fp"], 0.0)
        self.assertEqual(sentinel["scenarios"]["abnormal_sequence"]["mean_fp"], 0.0)
        self.assertLess(sentinel["mean_overall_fpr"], 0.0001)

    def test_doc_exists(self) -> None:
        doc = Path("docs/baseline_calibration_gap.md")
        self.assertTrue(doc.exists())
        content = doc.read_text(encoding="utf-8")
        self.assertIn("7.14%", content)
        self.assertIn("cross_server", content)
        self.assertIn("sensitive_argument", content)


if __name__ == "__main__":
    unittest.main()
