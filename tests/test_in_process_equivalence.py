"""Tests verifying exact pipeline equivalence between in-process dispatch and live HTTP transport."""
from __future__ import annotations

import unittest

from sentinel.experiment import ExperimentConfig, LiveExperiment
from sentinel.novelty_experiment import NoveltyLiveExperiment
from sentinel.novelty_scenarios import build_novelty_scenarios
from sentinel.workload import normal_workload


class TestPipelineEquivalence(unittest.TestCase):
    def test_base_live_experiment_in_process_equals_http(self):
        cases = normal_workload(12, 42, "test-equivalence")

        with LiveExperiment(ExperimentConfig(training_events=5), in_process=True) as exp_inproc:
            obs_inproc, det_inproc = exp_inproc.run_phase(cases, False, 1000)

        with LiveExperiment(ExperimentConfig(training_events=5), in_process=False) as exp_http:
            obs_http, det_http = exp_http.run_phase(cases, False, 1000)

        self.assertEqual(len(det_inproc), len(det_http))
        self.assertEqual(len(obs_inproc), len(obs_http))

        for idx, (d_inproc, d_http) in enumerate(zip(det_inproc, det_http)):
            self.assertEqual(d_inproc["decision"], d_http["decision"], f"Decision mismatch at event {idx}")
            self.assertAlmostEqual(d_inproc["risk"], d_http["risk"], places=6, msg=f"Risk mismatch at event {idx}")
            self.assertAlmostEqual(d_inproc["trust"], d_http["trust"], places=6, msg=f"Trust mismatch at event {idx}")
            self.assertEqual(d_inproc.get("reasons"), d_http.get("reasons"), f"Reasons mismatch at event {idx}")

        for idx, (o_inproc, o_http) in enumerate(zip(obs_inproc, obs_http)):
            self.assertEqual(o_inproc.intervened, o_http.intervened, f"Intervention mismatch at event {idx}")
            self.assertAlmostEqual(o_inproc.risk, o_http.risk, places=6, msg=f"Risk mismatch at event {idx}")

    def test_novelty_live_experiment_in_process_equals_http(self):
        scenarios = build_novelty_scenarios(42, 6)
        cases = scenarios["distributed_poisoning"].scenario.cases[:6]

        with NoveltyLiveExperiment(ExperimentConfig(training_events=5), "full", in_process=True) as exp_inproc:
            obs_inproc, det_inproc = exp_inproc.run_phase(cases, False, 1000)

        with NoveltyLiveExperiment(ExperimentConfig(training_events=5), "full", in_process=False) as exp_http:
            obs_http, det_http = exp_http.run_phase(cases, False, 1000)

        self.assertEqual(len(det_inproc), len(det_http))

        for idx, (d_inproc, d_http) in enumerate(zip(det_inproc, det_http)):
            self.assertEqual(d_inproc["decision"], d_http["decision"], f"Novelty decision mismatch at event {idx}")
            self.assertAlmostEqual(d_inproc["risk"], d_http["risk"], places=6, msg=f"Novelty risk mismatch at event {idx}")
            self.assertAlmostEqual(d_inproc["trust"], d_http["trust"], places=6, msg=f"Novelty trust mismatch at event {idx}")


if __name__ == "__main__":
    unittest.main()
