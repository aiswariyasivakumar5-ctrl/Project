"""Deterministic admission counterexamples; run with python -m sentinel_research.learning_admission_demo.

No dataset/threshold changes. Latency is a single local measurement, not a
benchmark. Expected outcomes are fixture oracles, never supplied to the gate.
"""

import json
import time
from dataclasses import replace

from .learning_admission import POLICIES, LearningAdmission
from sentinel.models import Interaction
from .verified_learning import verify_calculation

SCENARIOS = (
    "unchanged",
    "revoked",
    "relevant_change",
    "unrelated_change",
    "expiry",
    "replay",
    "change_back",
    "event_substitution",
)


def run_case(policy, scenario):
    if scenario not in SCENARIOS:
        raise ValueError("unknown scenario")
    now = [0.0]
    gate = LearningAdmission(policy=policy, clock=lambda: now[0], verifier=verify_calculation)
    scope = ("calculator", "calculate")
    gate.set_permission(scope, True)
    gate.set_capability(scope, "v1")
    item = Interaction(
        *scope,
        {"a": 1, "b": 2},
        {"content": [{"type": "text", "text": "3"}]},
        20,
        "Calculate sum",
        capability_digest="v1",
    )
    ticket = gate.approve("update-1", item, ttl=10, evidence_ref="local-arithmetic-verifier")
    if scenario == "revoked":
        gate.set_permission(scope, False)
    elif scenario in ("relevant_change", "change_back"):
        gate.set_capability(scope, "v2")
        if scenario == "change_back":
            gate.set_capability(scope, "v1")
    elif scenario == "unrelated_change":
        gate.set_capability(("calculator", "other"), "v2")
    elif scenario == "expiry":
        now[0] = 10.0
    elif scenario == "replay":
        assert gate.commit(ticket, item) == "committed"
    elif scenario == "event_substitution":
        item = replace(item, session_id="different-event")
    before = gate.snapshot()[1]
    start = time.perf_counter_ns()
    decision = gate.commit(ticket, item)
    elapsed = (time.perf_counter_ns() - start) / 1e6
    after = gate.snapshot()[1]
    eligible = scenario in ("unchanged", "unrelated_change")
    return {
        "policy": policy,
        "scenario": scenario,
        "decision": decision,
        "expected_eligible": eligible,
        "model_updates": after - before,
        "unsafe_admission": not eligible and decision == "committed",
        "eligible_withheld": eligible and decision != "committed",
        "commit_ms_single_observation": elapsed,
    }


def run_matrix():
    return [run_case(policy, scenario) for policy in POLICIES for scenario in SCENARIOS]


if __name__ == "__main__":
    print(
        json.dumps(
            {
                "scope": "synthetic deterministic functional counterexamples; no inference",
                "rows": run_matrix(),
            },
            indent=2,
        )
    )
