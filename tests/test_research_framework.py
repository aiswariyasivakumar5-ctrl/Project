import tempfile
import unittest
from pathlib import Path

from sentinel.engine import EngineConfig, SentinelEngine
from sentinel.experiment import ExperimentConfig, run_experiment
from sentinel.metrics import Observation, calculate_metrics
from sentinel.scenarios import build_scenarios
from sentinel.workload import normal_workload


class WorkloadTests(unittest.TestCase):
    def test_seed_is_deterministic(self):
        first = normal_workload(20, 42)
        second = normal_workload(20, 42)
        self.assertEqual(
            [(item.interaction.server_id, item.interaction.tool_name, item.interaction.arguments) for item in first],
            [(item.interaction.server_id, item.interaction.tool_name, item.interaction.arguments) for item in second],
        )

    def test_all_required_scenarios_exist(self):
        scenarios = build_scenarios(42, 12)
        expected = {"intent_mismatch", "abnormal_sequence", "tool_poisoning", "policy_injection",
                    "data_exfiltration", "schema_mutation", "capability_drift",
                    "destructive_operation", "cross_server", "delayed_malicious",
                    "low_and_slow", "gradual_poisoning", "legitimate_drift", "normal"}
        self.assertTrue(expected.issubset(scenarios))
        self.assertTrue(all(item.cases for item in scenarios.values()))

    def test_ablation_configuration_is_real(self):
        engine = SentinelEngine(config=EngineConfig(intent=False, causal=False, attestation=False,
                                                    uncertainty=False, quarantine=False))
        self.assertFalse(engine.config.intent)
        self.assertFalse(engine.config.quarantine)


class MetricTests(unittest.TestCase):
    def test_confusion_metrics(self):
        observations = [
            Observation(True, True, .9, .8, .1, 2, .1, 0),
            Observation(True, False, .2, .7, .2, 2, .1, 1),
            Observation(False, True, .7, .6, .3, 2, .1, 2),
            Observation(False, False, .1, .9, .1, 2, .1, 3),
        ]
        metrics = calculate_metrics(observations, 0)
        self.assertEqual((metrics["tp"], metrics["tn"], metrics["fp"], metrics["fn"]), (1, 1, 1, 1))
        self.assertAlmostEqual(metrics["precision"], 0.5)
        self.assertAlmostEqual(metrics["recall"], 0.5)
        self.assertIsNotNone(metrics["auroc"])
        self.assertIsNotNone(metrics["auprc"])


class ExperimentTests(unittest.TestCase):
    def test_real_gateway_experiment_is_reproducible_and_test_does_not_learn(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = run_experiment(ExperimentConfig(7, "intent_mismatch", 12, 4, 6, "sentinel", first_dir))[0]
            second = run_experiment(ExperimentConfig(7, "intent_mismatch", 12, 4, 6, "sentinel", second_dir))[0]
            self.assertEqual(first["experiment_id"], second["experiment_id"])
            self.assertEqual(first["metrics"]["risk_distribution"], second["metrics"]["risk_distribution"])
            self.assertEqual(first["baseline_state"]["trusted_before_test"],
                             first["baseline_state"]["trusted_after_test"])
            self.assertTrue(Path(first_dir, "summary.json").exists())
            self.assertTrue(any(item["trace_id"] for item in first["decisions"] if item["forwarded"]))

    def test_poisoning_adaptive_phase_tracks_quarantine(self):
        with tempfile.TemporaryDirectory() as output:
            result = run_experiment(ExperimentConfig(9, "gradual_poisoning", 20, 4, 10,
                                                      "sentinel", output))[0]
            state = result["baseline_state"]
            self.assertGreaterEqual(state["quarantined_after_test"], state["quarantined_before_test"])
            self.assertTrue(result["phase_policy"]["test_learns"])


if __name__ == "__main__":
    unittest.main()

