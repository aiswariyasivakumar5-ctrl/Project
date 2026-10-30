"""Tests for seed-driven genuine randomization in novelty scenarios."""
from __future__ import annotations

import unittest

from sentinel.novelty_experiment import _workload_digest
from sentinel.novelty_scenarios import build_novelty_scenarios


class NoveltyRandomizationTests(unittest.TestCase):
    def test_two_seeds_produce_different_workloads_and_identical_semantics(self) -> None:
        seed1 = 30001
        seed2 = 30002
        scenarios1 = build_novelty_scenarios(seed1, 12)
        scenarios2 = build_novelty_scenarios(seed2, 12)

        self.assertEqual(set(scenarios1.keys()), set(scenarios2.keys()))
        self.assertEqual(len(scenarios1), 8)

        for name in scenarios1:
            scen1 = scenarios1[name].scenario
            scen2 = scenarios2[name].scenario

            # 1. Semantics must match exactly
            self.assertEqual(len(scen1.cases), len(scen2.cases), f"Length mismatch in {name}")
            self.assertEqual(scen1.attack_start, scen2.attack_start, f"Attack start mismatch in {name}")

            for idx, (c1, c2) in enumerate(zip(scen1.cases, scen2.cases)):
                self.assertEqual(c1.malicious, c2.malicious, f"Malicious flag mismatch in {name} at {idx}")
                self.assertEqual(c1.interaction.tool_name, c2.interaction.tool_name, f"Tool mismatch in {name} at {idx}")
                self.assertEqual(c1.interaction.server_id, c2.interaction.server_id, f"Server mismatch in {name} at {idx}")
                self.assertEqual(c1.interaction.side_effect, c2.interaction.side_effect, f"Side effect mismatch in {name} at {idx}")

            # 2. Workload sha256 must differ between different seeds
            digest1 = _workload_digest(scen1.cases)
            digest2 = _workload_digest(scen2.cases)
            self.assertNotEqual(digest1, digest2, f"Workload digests must differ for seed {seed1} vs {seed2} in {name}")

    def test_single_actor_vs_multi_actor_semantics_preserved(self) -> None:
        scenarios = build_novelty_scenarios(30005, 12)

        dist = scenarios["distributed_poisoning"].scenario.cases
        # All events have the same identity
        self.assertEqual(len({c.independent_identity for c in dist}), 1)
        # All events have different session IDs
        self.assertEqual(len({c.interaction.session_id for c in dist}), 12)

        multi = scenarios["multi_actor_poisoning"].scenario.cases
        # Each event has a distinct identity
        self.assertEqual(len({c.independent_identity for c in multi}), 12)

        upgrade = scenarios["legitimate_upgrade"].scenario.cases
        # Each event has a distinct identity and is non-malicious
        self.assertEqual(len({c.independent_identity for c in upgrade}), 12)
        self.assertTrue(all(not c.malicious for c in upgrade))


if __name__ == "__main__":
    unittest.main()
