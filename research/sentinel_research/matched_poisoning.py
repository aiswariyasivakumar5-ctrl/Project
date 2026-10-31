"""Matched live development controls for legitimate learning and poisoning."""

import argparse
import hashlib
import json
import random
from dataclasses import replace
from pathlib import Path

from .adaptation_study import summarize_events
from .experiment import ExperimentConfig
from .learning_attribution import LearningAttribution
from .novelty_experiment import NoveltyLiveExperiment, _workload_digest
from .promotion_control import fixtures

SEEDS = (31001, 31002, 31003)
STREAMS = ("clean", "single_identity", "colluding", "mixed", "late_sparse")
POLICIES = {
    "frozen": "approval_required",
    "immediate": "without_dual_memory",
    "gated": "full",
    "oracle_review": "approval_required",
    "delayed_oracle": "approval_required",
    "mistaken_review": "approval_required",
    "withheld": "approval_required",
}


def build_matched(seed):
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    train, initial = fixtures(varied_enrollment=True)
    random.Random(seed).shuffle(train)
    cases = []
    for index in range(12):
        event = replace(
            initial[0].interaction,
            session_id=f"matched-{seed}-{index}",
            timestamp=1_700_100_000 + index,
        )
        cases.append(
            replace(initial[0], interaction=event, independent_identity=f"principal-{index}")
        )
    streams = {}
    for name in STREAMS:
        rows = []
        for index, case in enumerate(cases):
            malicious = (
                name in ("single_identity", "colluding")
                or name == "mixed"
                and index % 3 == 2
                or name == "late_sparse"
                and index >= 6
                and index % 2 == 0
            )
            # Actual incorrect arithmetic, not a hidden-label-only change. Each
            # response remains a three-character number with identical JSON shape.
            delta = 1 + (index - 6) // 2 if name == "late_sparse" and malicious else 1
            override = {"content": [{"type": "text", "text": f"3.{delta}"}]} if malicious else None
            rows.append(
                replace(
                    case,
                    scenario=name,
                    malicious=malicious,
                    expected_intervention=malicious,
                    response_override=override,
                    independent_identity="same-principal"
                    if name == "single_identity"
                    else case.independent_identity,
                )
            )
        streams[name] = rows
    return train, streams


def review_index(policy, stream):
    if policy == "mistaken_review":
        return 0
    if stream == "clean" and policy in ("oracle_review", "delayed_oracle"):
        return 3 if policy == "delayed_oracle" else 0
    return None


def learning_delays(rows):
    benign_onset = next((r["index"] for r in rows if not r["fixture_malicious"]), None)
    first_benign = next(
        (
            r["index"]
            for r in rows
            if any(item["fixture_malicious"] is False for item in r["learned_events"])
        ),
        None,
    )
    first_malicious = next(
        (
            r["index"]
            for r in rows
            if any(item["fixture_malicious"] is True for item in r["learned_events"])
        ),
        None,
    )
    return {
        "benign_learning_delay": None if first_benign is None else first_benign - benign_onset,
        "benign_learning_censored": benign_onset is not None and first_benign is None,
        "benign_learning_applicable": benign_onset is not None,
        "first_malicious_learning_index": first_malicious,
    }


def run_study(output, seeds=SEEDS, *, policies=None, experiment_factory=None, in_process=True):
    policies = dict(POLICIES if policies is None else policies)
    experiment_factory = experiment_factory or NoveltyLiveExperiment
    if not policies:
        raise ValueError("nonempty policies required")
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("unique nonempty seeds required")
    workloads = {seed: build_matched(seed) for seed in seeds}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        (output / name).write_text(
            json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )

    save(
        "protocol.json",
        {
            "purpose": "development-only matched poisoning diagnostic",
            "seeds": seeds,
            "seed_role": "shuffle the same balanced integer enrollment; not independent real workloads",
            "streams": STREAMS,
            "policies": policies,
            "events_per_stream": 12,
            "reviews": "oracle approves only clean; delayed oracle at index 3; mistaken approves every stream at index 0; others no grants",
            "review_limit": "scenario-aware oracle and scripted mistakes, not an evaluated reviewer",
            "attacker": "mock server returns incorrect arithmetic with unchanged manifest and valid attestation",
            "phase": "adaptive development only; no historical train/validation/test changes",
            "threshold_selection": "none; unchanged production defaults",
            "inference": "descriptive only; no confidence intervals or significance claims",
            "source_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(Path(__file__).parent.glob("*.py"))
            },
            "workload_sha256": {
                str(seed): {
                    "train": _workload_digest(train),
                    **{name: _workload_digest(cases) for name, cases in streams.items()},
                }
                for seed, (train, streams) in workloads.items()
            },
        },
    )
    state = {
        "status": "running",
        "completed": 0,
        "planned": len(seeds) * len(policies) * len(STREAMS),
    }
    save("execution.json", state)
    results = []
    try:
        for seed, (train, streams) in workloads.items():
            for policy, variant in policies.items():
                state.update(seed=seed, policy=policy, stream="enrollment")
                save("execution.json", state)
                with experiment_factory(
                    ExperimentConfig(training_events=len(train), in_process=in_process), variant
                ) as live:
                    live.run_phase(train, True, 1000, True)
                    checkpoint = live.checkpoint()
                    for name, cases in streams.items():
                        state["stream"] = name
                        save("execution.json", state)
                        live.restore(checkpoint)
                        before = live.learning_state()
                        gateway = live.gateways["local-test-mcp"]
                        rows = []
                        path = output / f"{seed}-{policy}-{name}.jsonl"
                        with (
                            path.open("x", encoding="utf-8") as handle,
                            LearningAttribution(live.engine, cases) as attribution,
                        ):
                            for index, case in enumerate(cases):
                                grant = index == review_index(policy, name)
                                if grant:
                                    reviewed = replace(
                                        case.interaction,
                                        capability_digest=gateway.capability_digest,
                                    )
                                    gateway.novelty.approve_promotion(
                                        reviewed,
                                        reviewer=f"fixture-{policy}",
                                        evidence_ref=f"{seed}-{name}",
                                        ttl=3600,
                                    )
                                attribution.step = index
                                offset = len(attribution.records)
                                observation, detail = live.execute(
                                    case, 10000 + index, policy != "frozen"
                                )
                                detail.update(
                                    index=index,
                                    phase="adaptive",
                                    fixture_malicious=case.malicious,
                                    fixture_response_override=case.response_override,
                                    review_granted=grant,
                                    intervened=observation.intervened,
                                    learned_events=attribution.records[offset:],
                                )
                                handle.write(json.dumps(detail, allow_nan=False) + "\n")
                                handle.flush()
                                rows.append(detail)
                        results.append(
                            {
                                "seed": seed,
                                "policy": policy,
                                "stream": name,
                                "workload_sha256": _workload_digest(cases),
                                "before": before,
                                "after": live.learning_state(),
                                **summarize_events(rows),
                                **learning_delays(rows),
                                "promotion_indices": [
                                    r["index"]
                                    for r in rows
                                    if r["novelty"]["memory_disposition"] == "promoted"
                                ],
                                "review_grants": sum(r["review_granted"] for r in rows),
                                "attestation_verified_calls": sum(
                                    r["attestation_verified"] is True for r in rows
                                ),
                            }
                        )
                        state["completed"] += 1
                        save("execution.json", state)
        save("summary.json", results)
        state["status"] = "complete"
    except Exception as exc:
        state.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        save("execution.json", state)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=SEEDS)
    parser.add_argument("--no-in-process", dest="in_process", action="store_false", default=True)
    args = parser.parse_args()
    rows = run_study(args.output, tuple(args.seeds), in_process=args.in_process)
    print(json.dumps({"status": "complete", "cells": len(rows)}, indent=2))
