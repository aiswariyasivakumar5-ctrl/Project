"""Exploratory live diagnostics for legitimate drift and poisoning coexistence."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import replace
from pathlib import Path

from .experiment import ExperimentConfig
from .learning_attribution import LearningAttribution, contamination
from .novelty_experiment import NoveltyLiveExperiment, _workload_digest
from .novelty_scenarios import NoveltyCase
from .workload import normal_workload

STREAMS = ("clean_drift", "poisoning_only", "mixed", "mixed_colluding")
POLICIES = {
    "frozen": "full",
    "immediate_eligible": "without_dual_memory",
    "gated": "full",
    "approval_withheld": "approval_required",
}
REVIEW_POLICIES = {"correct_review": 0, "delayed_review": 5, "withheld_review": None}


def recovery_metrics(rows, onset, window=5):
    """First sustained benign admission window; censor instead of inventing delay."""
    run = 0
    first_learning = None
    recovered = None
    for row in rows:
        if row["index"] < onset:
            continue
        if first_learning is None and any(
            item["fixture_malicious"] is False
            and item["source_event_index"] is not None
            and item["source_event_index"] >= onset
            for item in row.get("learned_events", [])
        ):
            first_learning = row["index"] - onset
        run = run + 1 if not row["fixture_malicious"] and not row["intervened"] else 0
        if recovered is None and run >= window:
            recovered = row["index"] - onset
    return {
        "benign_admission_recovery_delay": recovered,
        "recovery_censored": recovered is None,
        "recovery_window": window,
        "first_post_drift_benign_learning_delay": first_learning,
        "learning_recovery_censored": first_learning is None,
    }


def build_streams(seed: int, events: int = 120):
    """Matched timelines; private fixture labels never enter the learner."""
    if type(seed) is not int or type(events) is not int or events < 12:
        raise ValueError("integer seed and at least 12 events required")
    rng = random.Random(seed)
    anchor = f"record-{rng.randint(1000, 1020)}"
    timeline = normal_workload(events, seed, "adaptation")
    result = {}
    for name in STREAMS:
        cases = []
        for index, row in enumerate(timeline):
            changed = index >= events // 3
            attack_slot = changed and index % 3 == 0
            malicious = attack_slot and name != "clean_drift"
            drift = changed and name != "poisoning_only" and not malicious
            event = replace(
                row.interaction, server_id="local-test-mcp", session_id=f"adapt-{seed}-{index}"
            )
            identity = f"benign-{index % 5}"
            if drift or malicious:
                # Intentionally observationally equivalent: attack intent is hidden.
                # This tests the limit of identity/shape evidence, not text injection.
                event = replace(
                    event,
                    tool_name="safe_read",
                    arguments={"record_id": anchor, "format": "compact"},
                    user_intent=f"Read record {anchor}",
                    side_effect=False,
                )
            if malicious:
                identity = f"compromised-{index}" if name == "mixed_colluding" else "same-attacker"
            cases.append(
                NoveltyCase(event, malicious, name, malicious, independent_identity=identity)
            )
        result[name] = cases
    return result


def summarize_events(details):
    benign = [row for row in details if not row["fixture_malicious"]]
    attacks = [row for row in details if row["fixture_malicious"]]

    def rate(rows, key):
        return sum(bool(row[key]) for row in rows) / len(rows) if rows else None

    return {
        "events": len(details),
        "benign_events": len(benign),
        "malicious_events": len(attacks),
        "benign_intervention_rate": rate(benign, "intervened"),
        "malicious_intervention_rate": rate(attacks, "intervened"),
        "model_updates": sum(row["model_updates"] for row in details),
        "updates_on_malicious_call_steps": sum(row["model_updates"] for row in attacks),
        **contamination(details),
    }


def run_study(
    output: Path,
    seeds=(20001,),
    events=60,
    training=100,
    authorize_reads=False,
    review_study=False,
    in_process=True,
):
    if not seeds or len(set(seeds)) != len(seeds) or type(training) is not int or training < 1:
        raise ValueError("unique seeds and positive training count required")
    for seed in seeds:
        build_streams(seed, events)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    policies = {name: "approval_required" for name in REVIEW_POLICIES} if review_study else POLICIES
    state = {"status": "running", "completed": 0, "seed": None, "policy": None, "stream": None}

    def save(name, value):
        (output / name).write_text(
            json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )

    save(
        "protocol.json",
        {
            "purpose": "exploratory mechanism diagnostic",
            "seeds": seeds,
            "events": events,
            "training": training,
            "policies": policies,
            "review_schedule": REVIEW_POLICIES if review_study else None,
            "review_information": "simulated oracle approves clean drift only; mixed streams withheld"
            if review_study
            else None,
            "authorized_enrollment_reads": authorize_reads,
            "threshold_selection": "none; existing fixed gateway policy",
            "phase": "adaptive; never frozen TEST",
            "source_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(Path(__file__).parent.glob("*.py"))
            },
        },
    )
    records = []
    try:
        for seed in seeds:
            streams = build_streams(seed, events)
            for policy, variant in policies.items():
                state.update(seed=seed, policy=policy, stream="enrollment")
                save("execution.json", state)
                with NoveltyLiveExperiment(
                    ExperimentConfig(training_events=training, in_process=in_process), variant
                ) as live:
                    enrollment = normal_workload(training, seed * 10, "train")
                    if authorize_reads:
                        # Trusted fixture policy: fixed read-only record inventory.
                        # No malicious labels, observed risk, or outcome selection.
                        for session in sorted({row.interaction.session_id for row in enrollment}):
                            for source, target in (
                                ("local-test-mcp", "secondary-test-mcp"),
                                ("secondary-test-mcp", "local-test-mcp"),
                            ):
                                for record in range(1000, 1021):
                                    live.engine.causal_graph.authorize_read(
                                        source_server=source,
                                        source_tool="safe_read",
                                        destination_server=target,
                                        destination_tool="safe_read",
                                        session_id=session,
                                        arguments={"record_id": f"record-{record}"},
                                        ttl=3600,
                                    )
                    live.run_phase(enrollment, True, 1000, True)
                    checkpoint = live.checkpoint()
                    for name, cases in streams.items():
                        state["stream"] = name
                        save("execution.json", state)
                        live.restore(checkpoint)
                        rows = []
                        reviews = []
                        path = output / f"{seed}-{policy}-{name}.jsonl"
                        with (
                            path.open("x", encoding="utf-8") as handle,
                            LearningAttribution(live.engine, cases) as attribution,
                        ):
                            for index, case in enumerate(cases):
                                if review_study and name == "clean_drift":
                                    delay = REVIEW_POLICIES[policy]
                                    if delay is not None and index == events // 3 + delay:
                                        gateway = live.gateways[case.interaction.server_id]
                                        reviewed = replace(
                                            case.interaction,
                                            capability_digest=gateway.capability_digest,
                                        )
                                        gateway.novelty.approve_promotion(
                                            reviewed,
                                            reviewer="simulated-oracle",
                                            evidence_ref=f"clean-drift-{seed}",
                                            ttl=3600,
                                        )
                                        reviews.append(
                                            {
                                                "index": index,
                                                "action": "grant",
                                                "reviewer": "simulated-oracle",
                                                "delay_events": delay,
                                            }
                                        )
                                attribution.step = index
                                offset = len(attribution.records)
                                observation, detail = live.execute(
                                    case, 10000 + index, learn=policy != "frozen"
                                )
                                detail["learned_events"] = attribution.records[offset:]
                                detail["review_actions"] = [
                                    review for review in reviews if review["index"] == index
                                ]
                                detail.update(
                                    fixture_malicious=case.malicious,
                                    intervened=observation.intervened,
                                    index=index,
                                    phase="adaptive",
                                )
                                handle.write(json.dumps(detail, allow_nan=False) + "\n")
                                handle.flush()
                                rows.append(detail)
                        records.append(
                            {
                                "seed": seed,
                                "policy": policy,
                                "stream": name,
                                "workload_sha256": _workload_digest(cases),
                                **summarize_events(rows),
                                "review_grants": len(reviews),
                                "review_grants_per_100_events": 100 * len(reviews) / len(cases),
                                **recovery_metrics(rows, events // 3),
                            }
                        )
                        state["completed"] += 1
                        save("execution.json", state)
        save("summary.json", records)
        state["status"] = "complete"
    except Exception as exc:
        state.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        save("execution.json", state)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[20001])
    parser.add_argument("--events", type=int, default=60)
    parser.add_argument("--training", type=int, default=100)
    parser.add_argument("--authorize-reads", action="store_true")
    parser.add_argument("--review-study", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run_study(
                args.output,
                tuple(args.seeds),
                args.events,
                args.training,
                args.authorize_reads,
                args.review_study,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
