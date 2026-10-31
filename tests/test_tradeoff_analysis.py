import tempfile
import unittest
from pathlib import Path

from sentinel_research.tradeoff_analysis import (TradeoffConfig, _contributions, run_tradeoff_analysis,
                                         sequence_locality_probe)


class TradeoffAnalysisTests(unittest.TestCase):
    def test_weighted_decomposition_uses_frozen_weights(self):
        components = {"behavior": 1, "intent": 1, "sequence": 1, "causal": 1,
                      "impact": 1, "failure": 1, "attestation": 1}
        self.assertAlmostEqual(sum(_contributions(components).values()), 1.0)

    def test_sequence_probe_exposes_session_local_cold_start(self):
        result = sequence_locality_probe()
        self.assertGreater(result["learned_session_score"], 0)
        self.assertEqual(result["new_session_score"], 0)

    def test_small_run_is_isolated_and_validation_calibrated(self):
        with tempfile.TemporaryDirectory() as folder:
            result = run_tradeoff_analysis(TradeoffConfig((42,), 40, 20, 48, .01, folder))
            self.assertFalse(result["guardrails"]["production_logic_changed"])
            self.assertFalse(result["guardrails"]["test_used_for_threshold"])
            self.assertTrue((Path(folder) / "summary.json").exists())
            alternatives = result["seeds"][0]["full"]["offline_alternatives"]
            self.assertTrue(all(not item["test_used_for_threshold"] for item in alternatives.values()))


if __name__ == "__main__":
    unittest.main()
