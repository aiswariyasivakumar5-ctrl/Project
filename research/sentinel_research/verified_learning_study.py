"""Factorial development comparison: per-event verifier versus dual memory."""

import argparse
import json
from pathlib import Path

from .matched_poisoning import run_study
from .novelty_experiment import NoveltyLiveExperiment
from .verified_learning import VerifiedLearningEngine, verify_calculation

POLICIES = {
    "immediate": "without_dual_memory",
    "gated": "full",
    "verified_immediate": "verified_immediate",
    "verified_gated": "verified_gated",
}
SEEDS = (41001, 41002, 41003, 41004, 41005)


class VerifiedExperiment(NoveltyLiveExperiment):
    def __init__(self, config, variant):
        self.verify_results = variant.startswith("verified_")
        selected = {"verified_immediate": "without_dual_memory", "verified_gated": "full"}.get(
            variant, variant
        )
        super().__init__(config, selected)

    def __enter__(self):
        super().__enter__()
        if self.verify_results:
            for gateway in self.gateways.values():
                gateway.novelty = VerifiedLearningEngine(
                    self.engine, config=gateway.novelty.config, verifier=verify_calculation
                )
        return self


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = run_study(
        args.output, SEEDS, policies=POLICIES, experiment_factory=VerifiedExperiment
    )
    print(json.dumps({"completed": len(results)}))
