import json
from pathlib import Path
import tempfile
import unittest

from sentinel.matched_poisoning_stats import analyze_matched_poisoning, render_markdown_table


class MatchedPoisoningStatsTests(unittest.TestCase):
    def test_analyze_and_render_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            summary_file = Path(tmpdir) / "summary.json"
            sample_data = [
                {
                    "seed": 31001,
                    "policy": "gated",
                    "stream": "clean",
                    "model_updates": 12,
                    "malicious_learning_updates": 0,
                    "benign_learning_delay": 2,
                    "benign_learning_applicable": True,
                    "benign_learning_censored": False,
                    "benign_intervention_rate": 0.0,
                    "malicious_intervention_rate": None,
                },
                {
                    "seed": 31002,
                    "policy": "gated",
                    "stream": "clean",
                    "model_updates": 12,
                    "malicious_learning_updates": 0,
                    "benign_learning_delay": 2,
                    "benign_learning_applicable": True,
                    "benign_learning_censored": False,
                    "benign_intervention_rate": 0.0,
                    "malicious_intervention_rate": None,
                },
                {
                    "seed": 31001,
                    "policy": "gated",
                    "stream": "colluding",
                    "model_updates": 12,
                    "malicious_learning_updates": 12,
                    "benign_learning_delay": None,
                    "benign_learning_applicable": False,
                    "benign_learning_censored": False,
                    "benign_intervention_rate": None,
                    "malicious_intervention_rate": 0.0,
                },
                {
                    "seed": 31002,
                    "policy": "gated",
                    "stream": "colluding",
                    "model_updates": 12,
                    "malicious_learning_updates": 12,
                    "benign_learning_delay": None,
                    "benign_learning_applicable": False,
                    "benign_learning_censored": False,
                    "benign_intervention_rate": None,
                    "malicious_intervention_rate": 0.0,
                },
            ]
            summary_file.write_text(json.dumps(sample_data), encoding="utf-8")
            
            analysis = analyze_matched_poisoning(summary_file)
            self.assertEqual(analysis["n_seeds"], 2)
            self.assertEqual(analysis["cells"], 2)
            
            clean_cell = next(c for c in analysis["statistics"] if c["stream"] == "clean")
            self.assertEqual(clean_cell["total_updates"]["mean"], 12.0)
            self.assertEqual(clean_cell["malicious_updates"]["mean"], 0.0)
            self.assertEqual(clean_cell["contamination_rate"]["mean"], 0.0)
            self.assertEqual(clean_cell["benign_learning_delay"]["mean"], 2.0)
            
            colluding_cell = next(c for c in analysis["statistics"] if c["stream"] == "colluding")
            self.assertEqual(colluding_cell["total_updates"]["mean"], 12.0)
            self.assertEqual(colluding_cell["malicious_updates"]["mean"], 12.0)
            self.assertEqual(colluding_cell["contamination_rate"]["mean"], 1.0)
            self.assertFalse(colluding_cell["benign_learning_delay"]["applicable"])
            
            md = render_markdown_table(analysis)
            self.assertIn("clean", md)
            self.assertIn("colluding", md)
            self.assertIn("12.0", md)
