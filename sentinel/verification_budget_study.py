"""Offline development pilot; no production gateway or historical result changes."""

import argparse
import copy
import hashlib
import json
import random
import time
from dataclasses import asdict, replace
from pathlib import Path

from .engine import SentinelEngine
from .models import Action
from .promotion_control import fixtures
from .statistics import (
    bootstrap_mean_ci,
    exact_paired_sign_flip,
    holm_adjust,
    paired_bootstrap_difference,
)
from .verification_budget import POLICIES, VerificationBudget
from .verified_learning import verify_calculation

SEEDS = (51001, 51002, 51003, 51004, 51005)
STREAMS = ("clean_drift", "coordinated", "mixed", "gradual")
FEEDBACK = ("exact", "delayed", "flipped", "unavailable")


def response(number):
    return {"content": [{"type": "text", "text": str(number)}]}


def workload(seed, stream):
    train, initial = fixtures(varied_enrollment=True)
    random.Random(seed).shuffle(train)
    training = [
        replace(
            c.interaction,
            response=response(sum(c.interaction.arguments.values())),
            capability_digest="calculator-v1",
        )
        for c in train
    ]
    rows = []
    for i in range(96):
        scale = (1, 10, 100, 1000)[(i // 24) % 4]
        malicious = (
            stream == "coordinated"
            or stream == "mixed"
            and i % 3 == 2
            or stream == "gradual"
            and i >= 48
            and i % 2 == 0
        )
        correct = 3.0 * scale
        value = (
            "9" * (4 + (i - 48) // 8)
            if stream == "gradual" and malicious
            else correct + 0.1
            if malicious
            else correct
        )
        event = replace(
            initial[0].interaction,
            arguments={"a": float(scale), "b": 2.0 * scale},
            response=response(value),
            capability_digest="calculator-v1",
            session_id=f"budget-{seed}-{i}",
            timestamp=1_700_200_000 + i,
        )
        rows.append((event, malicious))
    return training, rows


def feedback_function(seed, mode):
    def verify(event, index):
        answer = verify_calculation(event)
        draw = random.Random(f"feedback:{seed}:{index}").random()
        if mode == "unavailable" and draw < 0.25:
            return None
        if mode == "flipped" and draw < 0.10 and type(answer) is bool:
            return not answer
        return answer

    return verify


def probes(enrollment, adapted):
    """Independent-history probes; transfer fitted quantities, not runtime trust."""
    values = []
    _, initial = fixtures()
    for i, text in enumerate(("3.0", "300.0", "3.1", "9999", "9" * 12, "9" * 32)):
        engine = copy.deepcopy(enrollment)
        for key, source in adapted.profiles.items():
            target = engine.profiles[key]
            for field in ("scaler", "autoencoder", "trusted_count", "error_mean", "error_m2"):
                setattr(target, field, copy.deepcopy(getattr(source, field)))
        scale = 100 if i == 1 else 1
        event = replace(
            initial[0].interaction,
            arguments={"a": float(scale), "b": 2.0 * scale},
            response=response(text),
            session_id=f"probe-{i}",
            capability_digest="calculator-v1",
        )
        verdict = engine.evaluate(event, learn=False)
        values.append(
            {
                "malicious": i >= 2,
                "risk": verdict.anomaly_score,
                "intervened": verdict.action not in (Action.ALLOW, Action.OBSERVE),
            }
        )
    return {
        "attack_recall": sum(r["intervened"] for r in values[2:]) / 4,
        "benign_fpr": sum(r["intervened"] for r in values[:2]) / 2,
        "mean_attack_risk": sum(r["risk"] for r in values[2:]) / 4,
    }


def run_cell(enrollment, rows, policy, mode, seed):
    engine = copy.deepcopy(enrollment)
    scheduler = VerificationBudget(policy, seed=seed, delay=4 if mode == "delayed" else 0)
    events, learned = [], []
    scopes = {}
    started = time.perf_counter()
    verify = feedback_function(seed, mode)
    for index, (event, malicious) in enumerate(rows):
        scopes[event.server_id, event.tool_name] = event.capability_digest
        # Deliver older feedback before observing the new event. No future labels.
        deliveries = scheduler.deliver(
            index, scopes, lambda e: engine.learn_approved(e, update_sequence=False)
        )
        verdict = engine.evaluate(event, learn=False)
        eligible = (
            event.success
            and not event.side_effect
            and verdict.anomaly_score < 0.42
            and not verdict.components["provenance"]
            and not verdict.components["attestation"]
        )
        scheduler.observe(index, event, verdict.uncertainty, eligible)
        selections = scheduler.select(verify)
        deliveries += scheduler.deliver(
            index, scopes, lambda e: engine.learn_approved(e, update_sequence=False)
        )
        learned += [d for d in deliveries if d["status"] == "accepted"]
        events.append(
            {
                "index": index,
                "fixture_malicious": malicious,
                "risk": verdict.anomaly_score,
                "uncertainty": verdict.uncertainty,
                "eligible": eligible,
                "intervened": verdict.action not in (Action.ALLOW, Action.OBSERVE),
                "selections": selections,
                "deliveries": deliveries,
            }
        )
    benign = [d for d in learned if not rows[d["source_index"]][1]]
    malicious_count = sum(rows[d["source_index"]][1] for d in learned)
    benign_count = sum(not flag for _, flag in rows)
    result = {
        "seed": seed,
        "policy": policy,
        "stream": None,
        "feedback": mode,
        "queries": scheduler.queries,
        "malicious_updates": malicious_count,
        "benign_updates": len(benign),
        "benign_events": benign_count,
        "benign_coverage": len(benign) / benign_count if benign_count else None,
        "benign_delay_mean": sum(d["delay"] for d in benign) / len(benign) if benign else None,
        "benign_learning_censored": bool(benign_count and not benign),
        "pending": len(scheduler.pending),
        "prequential_fpr": sum(r["intervened"] for r in events if not r["fixture_malicious"])
        / benign_count
        if benign_count
        else None,
        "offline_compute_ms": (time.perf_counter() - started) * 1000,
        "probe_before": probes(enrollment, enrollment),
        "probe_after": probes(enrollment, engine),
    }
    return result, events


def analyze(rows):
    expected = {(s, p, st, f) for s in SEEDS for p in POLICIES for st in STREAMS for f in FEEDBACK}
    keys = [(r["seed"], r["policy"], r["stream"], r["feedback"]) for r in rows]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("complete unique 480-cell matrix required")
    for seed in SEEDS:
        for stream in STREAMS:
            matched = [r for r in rows if r["seed"] == seed and r["stream"] == stream]
            if len({r["workload_sha256"] for r in matched}) != 1:
                raise ValueError("unmatched workloads")
    totals, comparisons = {}, []
    for policy in POLICIES:
        totals[policy] = {}
        for metric in ("malicious_updates", "benign_updates", "queries"):
            values = [
                sum(r[metric] for r in rows if r["seed"] == seed and r["policy"] == policy) / 16
                for seed in SEEDS
            ]
            totals[policy][metric] = {"per_seed": values, "ci": bootstrap_mean_ci(values).to_dict()}
    for baseline in ("first", "periodic", "random"):
        for metric in ("malicious_updates", "benign_updates"):
            a, b = totals["uncertainty"][metric]["per_seed"], totals[baseline][metric]["per_seed"]
            comparisons.append(
                {
                    "name": f"uncertainty_minus_{baseline}_{metric}",
                    "difference_ci": paired_bootstrap_difference(a, b).to_dict(),
                    "test": exact_paired_sign_flip(a, b),
                }
            )
    adjusted = holm_adjust({r["name"]: r["test"]["p_value_two_sided"] for r in comparisons})
    for row in comparisons:
        row["holm_p"] = adjusted[row["name"]]
        row["significant_0_05"] = row["holm_p"] < 0.05
    return {
        "equal_cell_mean_per_seed": totals,
        "comparisons": comparisons,
        "limitation": "Exploratory synthetic pilot; five seeds, not independent real tasks. No network overhead inference.",
    }


def render_report(rows, statistics):
    lines = [
        "# Verification-budget exploratory pilot",
        "",
        statistics["limitation"],
        "",
        "Each mean equally weights four streams and four feedback conditions within each seed.",
        "95% seed bootstrap intervals: 20,000 resamples, RNG 2026. Lower malicious updates and higher benign updates are desirable.",
        "",
        "| Policy | Malicious updates [95% CI] | Benign updates [95% CI] | Queries [95% CI] |",
        "|---|---:|---:|---:|",
    ]
    for policy, metrics in statistics["equal_cell_mean_per_seed"].items():
        values = []
        for metric in ("malicious_updates", "benign_updates", "queries"):
            ci = metrics[metric]["ci"]
            values.append(f"{ci['estimate']:.4f} [{ci['lower']:.4f}, {ci['upper']:.4f}]")
        lines.append("| " + policy + " | " + " | ".join(values) + " |")
    lines += [
        "",
        "## Six planned paired comparisons",
        "",
        "| Comparison | Difference [95% CI] | Exact two-sided p | Holm p |",
        "|---|---:|---:|---:|",
    ]
    for row in statistics["comparisons"]:
        ci = row["difference_ci"]
        lines.append(
            f"| {row['name']} | {ci['estimate']:.4f} [{ci['lower']:.4f}, {ci['upper']:.4f}] | {row['test']['p_value_two_sided']:.6f} | {row['holm_p']:.6f} |"
        )
    lines += [
        "",
        "No five-pair two-sided exact test can reach p < 0.05. Degenerate intervals reflect repeated synthetic outcomes, not certainty.",
        "",
        "## Complete per-cell matrix",
        "",
        "NA delay means no benign learning occurred; NA FPR means no benign events. Delay is conditional on learning, not time to complete adaptation.",
        "",
        "| Seed | Stream | Feedback | Policy | Queries | Bad updates | Good updates | Good coverage | Mean delay | Pending | Prequential FPR | Probe recall before/after | Probe FPR before/after |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        values = [
            row[k]
            for k in (
                "seed",
                "stream",
                "feedback",
                "policy",
                "queries",
                "malicious_updates",
                "benign_updates",
                "benign_coverage",
                "benign_delay_mean",
                "pending",
                "prequential_fpr",
            )
        ]
        values += [
            f"{row['probe_before'][m]:.4f}/{row['probe_after'][m]:.4f}"
            for m in ("attack_recall", "benign_fpr")
        ]
        lines.append(
            "| "
            + " | ".join(
                "NA" if v is None else f"{v:.4f}" if isinstance(v, float) else str(v)
                for v in values
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def run(output):
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        (root / name).write_text(
            json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )

    protocol = Path(__file__).resolve().parent.parent / "docs/verification_budget_protocol.md"
    save(
        "protocol.json",
        {
            "design": protocol.read_text(encoding="utf-8"),
            "design_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest(),
            "source_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in Path(__file__).parent.glob("*.py")
            },
        },
    )
    state = {"status": "running", "completed": 0, "planned": 480}
    results = []
    save("execution.json", state)
    try:
        for seed in SEEDS:
            training, _ = workload(seed, "clean_drift")
            enrollment = SentinelEngine()
            for event in training:
                enrollment.evaluate(event, learn=True, trusted_enrollment=True)
            for stream in STREAMS:
                _, rows = workload(seed, stream)
                digest = hashlib.sha256(
                    json.dumps([(asdict(e), label) for e, label in rows], sort_keys=True).encode()
                ).hexdigest()
                for mode in FEEDBACK:
                    for policy in POLICIES:
                        result, events = run_cell(enrollment, rows, policy, mode, seed)
                        result.update(stream=stream, workload_sha256=digest)
                        results.append(result)
                        save(
                            f"{seed}-{stream}-{mode}-{policy}.json",
                            {"summary": result, "events": events},
                        )
                        state.update(
                            completed=len(results),
                            seed=seed,
                            stream=stream,
                            feedback=mode,
                            policy=policy,
                        )
                        save("execution.json", state)
                print(f"Completed seed={seed} stream={stream}", flush=True)
        save("summary.json", results)
        statistics = analyze(results)
        save("statistics.json", statistics)
        (root / "REPORT.md").write_text(render_report(results, statistics), encoding="utf-8")
        state["status"] = "complete"
    except Exception as exc:
        state.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        save("execution.json", state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    run(parser.parse_args().output)
