"""Read-only analysis of a complete novelty study; never fits thresholds."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .statistics import (
    bootstrap_mean_ci,
    exact_paired_sign_flip,
    holm_adjust,
    paired_bootstrap_difference,
)

PRIMARY = (
    (
        "capability_isolation",
        "full",
        "without_capability_trust",
        "capability_laundering",
        "test",
        "false_positive_rate",
    ),
    (
        "single_actor_poisoning",
        "full",
        "without_dual_memory",
        "distributed_poisoning",
        "adaptive",
        "model_updates",
    ),
    (
        "intent_consistency",
        "full",
        "without_intent_provenance",
        "coordinated_servers",
        "test",
        "recall",
    ),
    (
        "review_requirement",
        "approval_required",
        "full",
        "multi_actor_poisoning",
        "adaptive",
        "model_updates",
    ),
)


def provenance_outcomes(decisions):
    """Separate denied setup from attacks against an issued claim."""
    items = [d["provenance"] for d in decisions if d.get("provenance")]
    return {
        "issue_attempts": sum(p["operation"] == "issue" for p in items),
        "issued_claims": sum(p.get("issued") is not None for p in items),
        "denied_issuance": sum(p.get("issuance_error") is not None for p in items),
        "use_attempts": sum(p["operation"] == "use" for p in items),
        "uses_without_retained_claim": sum(
            p["operation"] == "use" and p.get("before") is None for p in items
        ),
    }


def value(row, metric):
    m = row["metrics"]
    if metric == "model_updates":
        return row["learning_after"]["model_updates"] - row["learning_before"]["model_updates"]
    if metric == "latency_mean_ms":
        return m["latency_ms"]["mean"]
    if metric in ("recall", "f1") and not m["tp"] + m["fn"]:
        return None
    if metric == "precision" and not m["tp"] + m["fp"]:
        return None
    if metric == "false_positive_rate" and not m["tn"] + m["fp"]:
        return None
    return m[metric]


def analyze(rows, config):
    """Reject missing/duplicate pairs rather than quietly selecting seed subsets."""
    from .novelty_scenarios import build_novelty_scenarios

    scenarios = build_novelty_scenarios(events=config["test_events"])
    expected = {
        (v, s, p, seed)
        for v in config["variants"]
        for s in config["scenarios"]
        for p in (("test", "adaptive") if scenarios[s].adaptive else ("test",))
        for seed in config["seeds"]
    }
    indexed = {}
    for row in rows:
        key = tuple(row[k] for k in ("variant", "scenario", "phase", "seed"))
        if key in indexed:
            raise ValueError(f"duplicate row: {key}")
        indexed[key] = row
    if set(indexed) != expected:
        raise ValueError(
            f"incomplete matrix: missing {len(expected - set(indexed))}, unexpected {len(set(indexed) - expected)}"
        )
    seeds = sorted(config["seeds"])
    aggregate = []
    for variant, scenario, phase in sorted({key[:3] for key in expected}):
        group = [indexed[variant, scenario, phase, seed] for seed in seeds]
        metrics = {}
        for name in (
            "precision",
            "recall",
            "f1",
            "false_positive_rate",
            "auroc",
            "auprc",
            "detection_delay_events",
            "latency_mean_ms",
            "sentinel_evaluation_mean_ms",
            "model_updates",
        ):
            values = [value(r, name) for r in group]
            valid = [v for v in values if v is not None]
            ci = bootstrap_mean_ci(valid)
            metrics[name] = {
                "per_seed": dict(zip(map(str, seeds), values, strict=False)),
                "defined_seeds": len(valid),
                "ci": ci.to_dict() if ci else None,
            }
        aggregate.append(dict(variant=variant, scenario=scenario, phase=phase, metrics=metrics))
    comparisons = []
    for name, a, b, scenario, phase, metric in PRIMARY:
        left = [indexed[a, scenario, phase, s] for s in seeds]
        right = [indexed[b, scenario, phase, s] for s in seeds]
        if any(
            x["workload_sha256"] != y["workload_sha256"] for x, y in zip(left, right, strict=False)
        ):
            raise ValueError(f"unmatched workloads: {name}")
        av, bv = [value(r, metric) for r in left], [value(r, metric) for r in right]
        if None in av or None in bv:
            raise ValueError(f"undefined primary endpoint: {name}")
        comparisons.append(
            dict(
                name=name,
                a=a,
                b=b,
                scenario=scenario,
                phase=phase,
                metric=metric,
                seeds=seeds,
                a_values=av,
                b_values=bv,
                difference_ci=paired_bootstrap_difference(av, bv).to_dict(),
                test=exact_paired_sign_flip(av, bv),
            )
        )
    adjusted = holm_adjust({r["name"]: r["test"]["p_value_two_sided"] for r in comparisons})
    for row in comparisons:
        row["holm_p"] = adjusted[row["name"]]
        row["significant_0_05"] = row["holm_p"] < 0.05
    return dict(
        aggregate=aggregate,
        primary_comparisons=comparisons,
        inference="Exploratory synthetic evidence; seed is the paired unit. No external preregistration.",
        delay_note="Delay intervals condition on detection; undefined seeds are reported, not imputed.",
    )


def generate(source, output):
    source, output = Path(source), Path(output)
    if not (source / "summary.json").is_file():
        raise ValueError("study has not completed: summary.json missing")
    protocol = json.loads((source / "protocol.json").read_text(encoding="utf-8"))
    files = [p for p in sorted(source.glob("*/*/seed-*.json")) if "calibration" not in p.parts]
    rows = []
    provenance = []
    for path in files:
        row = json.loads(path.read_text(encoding="utf-8"))
        # Event evidence stays in its immutable source file. Holding the complete
        # event matrix in memory is unnecessary for seed-level inference.
        decisions = row.pop("decisions", [])
        outcomes = provenance_outcomes(decisions)
        if outcomes["issue_attempts"] or outcomes["use_attempts"]:
            provenance.append(
                {**{k: row[k] for k in ("variant", "scenario", "phase", "seed")}, **outcomes}
            )
        for field in (
            "roc_curve",
            "precision_recall_curve",
            "risk_distribution",
            "trust_distribution",
        ):
            row["metrics"].pop(field, None)
        row.pop("score_metrics", None)
        rows.append(row)
    report = analyze(rows, protocol["configuration"])
    report["provenance_outcomes"] = provenance
    report["source_hashes"] = {
        str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "statistics.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    lines = [
        "# Novelty evaluation evidence",
        "",
        report["inference"],
        "",
        report["delay_note"],
        "",
        "Intervals: 95% seed bootstrap, 20,000 resamples, RNG 2026.",
        "",
        "| Variant | Scenario | Phase | F1 [95% CI] | FPR [95% CI] | Updates [95% CI] |",
        "|---|---|---|---|---|---|",
    ]

    def fmt(item):
        ci = item["ci"]
        return (
            "N/A" if ci is None else f"{ci['estimate']:.4f} [{ci['lower']:.4f}, {ci['upper']:.4f}]"
        )

    for row in report["aggregate"]:
        lines.append(
            f"| {row['variant']} | {row['scenario']} | {row['phase']} | "
            + " | ".join(
                fmt(row["metrics"][m]) for m in ("f1", "false_positive_rate", "model_updates")
            )
            + " |"
        )
    lines += [
        "",
        "## Planned primary comparisons (exploratory execution)",
        "",
        "| Comparison | A minus B | Two-sided p | Holm p |",
        "|---|---:|---:|---:|",
    ]
    for row in report["primary_comparisons"]:
        lines.append(
            f"| {row['name']} | {row['difference_ci']['estimate']:.6f} | {row['test']['p_value_two_sided']:.6f} | {row['holm_p']:.6f} |"
        )
    pair_note = (
        f"{len(protocol['configuration']['seeds'])} pairs cannot establish p < 0.05 with this exact two-sided test."
        if len(protocol["configuration"]["seeds"]) < 6
        else f"{len(protocol['configuration']['seeds'])} paired seeds evaluate statistical significance under exact two-sided sign-flip permutation tests."
    )
    lines += [
        "",
        pair_note,
        "Model-update prevention does not establish attack denial. Latency is local sequential measurement; no direct-server overhead is inferred.",
    ]
    if provenance:
        lines += [
            "",
            "## Provenance setup eligibility",
            "",
            "Blocked origins and unknown claims are not successful stale/replay challenges. Counts below do not change the outcome denominators.",
            "",
            "| Variant | Scenario | Phase | Seed | Issue attempts | Issued | Denied issuance | Use attempts | Uses without retained claim |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        for r in provenance:
            lines.append(
                "| "
                + " | ".join(
                    str(r[k])
                    for k in (
                        "variant",
                        "scenario",
                        "phase",
                        "seed",
                        "issue_attempts",
                        "issued_claims",
                        "denied_issuance",
                        "use_attempts",
                        "uses_without_retained_claim",
                    )
                )
                + " |"
            )
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    generate(args.source, args.output)
