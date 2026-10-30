"""Regression test verifying reconciliation between decision-rule and score-sweep operating points."""
from __future__ import annotations

import json
from pathlib import Path
import unittest


class TestMatchedFPRReconciliation(unittest.TestCase):
    def setUp(self):
        self.base_dir = Path("results/baselines_20seed")
        self.recon_dir = Path("results/matched_fpr_v2")

    @unittest.skipUnless(Path("results/baselines_20seed").is_dir(), "Requires generated research results")
    def test_decision_rule_matches_raw_sweep_for_sentinel(self):
        """Verify that Sentinel's decision rule strictly matches raw score evaluation at threshold > 0.50."""
        for s in range(20001, 20021):
            p = self.base_dir / "sentinel" / "per_seed" / f"seed-{s}.json"
            d = json.loads(p.read_text(encoding="utf-8"))

            m = d["metrics"]
            dec_rec = m["recall"]
            dec_fpr = m["false_positive_rate"]

            outcomes = d["event_outcomes"]
            mal = [e for e in outcomes if e["malicious"]]
            benign = [e for e in outcomes if not e["malicious"]]

            # Raw score evaluation with strict inequality raw > 0.50
            th = 0.50
            tp = sum(e["raw_score"] > th for e in mal)
            fp = sum(e["raw_score"] > th for e in benign)
            raw_rec = tp / len(mal)
            raw_fpr = fp / len(benign)

            self.assertAlmostEqual(dec_rec, raw_rec, places=6, msg=f"Recall mismatch on seed {s}")
            self.assertAlmostEqual(dec_fpr, raw_fpr, places=6, msg=f"FPR mismatch on seed {s}")

    @unittest.skipUnless(Path("results/baselines_20seed").is_dir(), "Requires generated research results")
    def test_sentinel_tie_counts_and_percentile_clamping(self):
        """Verify the exact tie counts on seed 20001 explaining the percentile sweep artifact."""
        p = self.base_dir / "sentinel" / "per_seed" / "seed-20001.json"
        d = json.loads(p.read_text(encoding="utf-8"))

        outcomes = d["event_outcomes"]
        benign = [e for e in outcomes if not e["malicious"]]
        mal = [e for e in outcomes if e["malicious"]]

        # 1. Exactly 175 benign events have raw_score == 0.50
        benign_ties = sum(1 for e in benign if e["raw_score"] == 0.50)
        self.assertEqual(benign_ties, 175)

        # 2. Both 175 benign events and 1,000 detected attacks get score_percentile == 1.0
        benign_pct_1 = sum(1 for e in benign if e["score_percentile"] >= 1.0)
        mal_pct_1 = sum(1 for e in mal if e["score_percentile"] >= 1.0)
        self.assertEqual(benign_pct_1, 175)
        self.assertEqual(mal_pct_1, 1000)

        # 3. Under weak inequality (score >= 1.0), FPR jumps to 175 / 1750 = 10%
        self.assertAlmostEqual(benign_pct_1 / len(benign), 0.10, places=6)

    @unittest.skipUnless(Path("results/matched_fpr_v2").is_dir(), "Requires generated research results")
    def test_reconciliation_files_exist_and_contain_valid_cis(self):
        """Verify that results/matched_fpr_v2/ contains valid summary files with 95% CIs."""
        dec_file = self.recon_dir / "decision_rule_operating_points.json"
        raw_file = self.recon_dir / "raw_score_matched_fpr.json"

        self.assertTrue(dec_file.exists())
        self.assertTrue(raw_file.exists())

        dec_data = json.loads(dec_file.read_text(encoding="utf-8"))
        raw_data = json.loads(raw_file.read_text(encoding="utf-8"))

        self.assertIn("sentinel", dec_data)
        self.assertIn("dense_autoencoder", dec_data)

        sentinel_rec_ci = dec_data["sentinel"]["recall"]["ci_95"]
        self.assertAlmostEqual(sentinel_rec_ci[0], 0.6667, places=3)
        self.assertAlmostEqual(sentinel_rec_ci[1], 0.6667, places=3)

        sentinel_raw_rec = raw_data["sentinel"]["0.01"]["mean_recall"]
        self.assertAlmostEqual(sentinel_raw_rec, 0.6667, places=3)


if __name__ == "__main__":
    unittest.main()
