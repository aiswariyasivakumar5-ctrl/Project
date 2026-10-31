from __future__ import annotations

import copy
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .compare import aggregate_results, calibrate_threshold, evaluate_model, percentile_scores
from .comparison_data import build_comparison_dataset
from sentinel.engine import EngineConfig, SentinelEngine
from .ml_features import simulated_response
from .scenarios import build_scenarios
from .statistics import (
    bootstrap_mean_ci,
    exact_paired_sign_flip,
    holm_adjust,
    paired_bootstrap_difference,
    wilcoxon_signed_rank,
)

ABLATIONS = {
    "full": EngineConfig(),
    "without_intent": EngineConfig(intent=False),
    "without_causal": EngineConfig(causal=False),
    "without_attestation": EngineConfig(attestation=False),
    "without_uncertainty": EngineConfig(uncertainty=False),
    "without_quarantine": EngineConfig(quarantine=False),
}
MAJOR_METRICS = [
    "f1",
    "precision",
    "recall",
    "false_positive_rate",
    "auroc",
    "auprc",
    "detection_delay_events",
]


@dataclass(frozen=True)
class AblationConfig:
    seeds: tuple[int, ...] = (42, 123, 456, 789, 1001)
    train_size: int = 5000
    validation_size: int = 1000
    test_size: int = 3000
    validation_fpr: float = 0.01
    output: str = "results/ablations_publication"
    bootstrap_resamples: int = 20_000


def _statistics(results: list[dict[str, Any]], resamples: int) -> dict[str, Any]:
    by_variant = {
        variant: sorted(
            [item for item in results if item["model"] == variant], key=lambda x: x["seed"]
        )
        for variant in ABLATIONS
    }
    confidence_intervals, comparisons = {}, {}
    for variant, selected in by_variant.items():
        confidence_intervals[variant] = {}
        for metric in MAJOR_METRICS:
            values = [
                item["metrics"][metric] for item in selected if item["metrics"][metric] is not None
            ]
            ci = bootstrap_mean_ci(values, seed=2026, resamples=resamples)
            confidence_intervals[variant][metric] = ci.to_dict() if ci else None
    full = by_variant["full"]
    raw_p = {}
    wilcoxon_raw_p = {}
    for variant, selected in by_variant.items():
        if variant == "full":
            continue
        comparisons[variant] = {}
        for metric in MAJOR_METRICS:
            pairs = [
                (a["metrics"][metric], b["metrics"][metric])
                for a, b in zip(full, selected, strict=False)
                if a["metrics"][metric] is not None and b["metrics"][metric] is not None
            ]
            a_values, b_values = [p[0] for p in pairs], [p[1] for p in pairs]
            test = exact_paired_sign_flip(a_values, b_values)
            wilcoxon = wilcoxon_signed_rank(a_values, b_values)
            ci = paired_bootstrap_difference(a_values, b_values, seed=2026, resamples=resamples)
            comparisons[variant][metric] = {
                "test": test,
                "wilcoxon": wilcoxon,
                "difference_ci": ci.to_dict() if ci else None,
            }
            if metric == "f1":
                if test:
                    raw_p[variant] = float(test["p_value_two_sided"])
                if wilcoxon:
                    wilcoxon_raw_p[variant] = float(wilcoxon["p_value_two_sided"])
    adjusted = holm_adjust(raw_p)
    wilcoxon_adjusted = holm_adjust(wilcoxon_raw_p)
    for variant, value in adjusted.items():
        comparisons[variant]["f1"]["holm_adjusted_p"] = value
    for variant, value in wilcoxon_adjusted.items():
        comparisons[variant]["f1"]["wilcoxon_holm_p"] = value
    return {
        "confidence_intervals": confidence_intervals,
        "paired_full_minus_ablation": comparisons,
        "inference_note": "Seed is the independent pairing unit. Includes exact sign-flip and exact Wilcoxon signed-rank tests with Holm correction.",
    }


def _adaptive_curve(
    seed: int,
    config: EngineConfig,
    train_size: int,
    validation_size: int,
    scenario_name: str,
    events: int = 200,
) -> list[dict[str, Any]]:
    dataset = build_comparison_dataset(seed, train_size, validation_size, 120)
    engine = SentinelEngine(20, config)
    for row in dataset.train:
        engine.evaluate(row.interaction, learn=True, trusted_enrollment=True)
    trained = copy.deepcopy(engine)
    validation_scores = np.asarray(
        [engine.evaluate(row.interaction, learn=False).anomaly_score for row in dataset.validation]
    )
    threshold = calibrate_threshold(validation_scores, 0.01)
    engine = trained
    scenario = build_scenarios(seed, events)[scenario_name]
    curve = []
    for index, case in enumerate(scenario.cases):
        event = copy.deepcopy(case.interaction)
        event.response = simulated_response(event)
        event.capability_digest = "cap-v1"
        verdict = engine.evaluate(event, learn=True)
        percentile = float(
            percentile_scores(validation_scores, np.asarray([verdict.anomaly_score]))[0]
        )
        curve.append(
            {
                "index": index,
                "malicious": case.malicious,
                "risk_percentile": percentile,
                "intervened": verdict.anomaly_score > threshold,
                "trust": verdict.trust_score,
                "baseline_updated": verdict.baseline_updated,
                "quarantined_total": sum(p.quarantined_count for p in engine.profiles.values()),
            }
        )
    return curve


def run_ablation_matrix(config: AblationConfig) -> dict[str, Any]:
    root = Path(config.output)
    results = []
    for seed in config.seeds:
        dataset = build_comparison_dataset(
            seed, config.train_size, config.validation_size, config.test_size
        )
        for variant, engine_config in ABLATIONS.items():
            result = evaluate_model("sentinel", dataset, seed, config.validation_fpr, engine_config)
            result["model"] = variant
            result["architecture"] = "sentinel_ablation"
            results.append(result)
            folder = root / variant / "per_seed"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"seed-{seed}.json").write_text(
                json.dumps(result, indent=2), encoding="utf-8"
            )
    aggregate = aggregate_results(results)
    statistics = _statistics(results, config.bootstrap_resamples)
    aggregate_dir = root / "aggregate"
    aggregate_dir.mkdir(parents=True, exist_ok=True)
    (aggregate_dir / "metrics.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    (aggregate_dir / "statistics.json").write_text(
        json.dumps(statistics, indent=2), encoding="utf-8"
    )
    scenario_rows = []
    for result in results:
        for scenario, metrics in result["per_scenario"].items():
            scenario_rows.append(
                {
                    "seed": result["seed"],
                    "variant": result["model"],
                    "scenario": scenario,
                    **{metric: metrics[metric] for metric in MAJOR_METRICS},
                }
            )
    with (root / "per_scenario.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(scenario_rows[0]))
        writer.writeheader()
        writer.writerows(scenario_rows)
    adaptive: dict[str, Any] = {}
    adaptive_train = min(config.train_size, 1000)
    adaptive_validation = min(config.validation_size, 250)
    for variant, engine_config in ABLATIONS.items():
        adaptive[variant] = {}
        for scenario in ("legitimate_drift", "gradual_poisoning"):
            adaptive[variant][scenario] = {
                str(seed): _adaptive_curve(
                    seed, engine_config, adaptive_train, adaptive_validation, scenario
                )
                for seed in config.seeds
            }
    (aggregate_dir / "adaptive_curves.json").write_text(
        json.dumps(adaptive, indent=2), encoding="utf-8"
    )
    adaptive_stats = analyze_adaptive_curves(adaptive, config.bootstrap_resamples)
    (aggregate_dir / "adaptive_statistics.json").write_text(
        json.dumps(adaptive_stats, indent=2), encoding="utf-8"
    )
    return {
        "configuration": asdict(config),
        "aggregate": aggregate,
        "statistics": statistics,
        "adaptive_curves": adaptive,
        "adaptive_statistics": adaptive_stats,
        "results": results,
    }


def analyze_adaptive_curves(adaptive: dict[str, Any], resamples: int = 20_000) -> dict[str, Any]:
    def rates(variant: str, scenario: str, field: str, malicious_only: bool = False) -> list[float]:
        result = []
        for seed in sorted(adaptive[variant][scenario], key=int):
            events = adaptive[variant][scenario][seed]
            if malicious_only:
                events = [event for event in events if event["malicious"]]
            result.append(sum(bool(event[field]) for event in events) / len(events))
        return result

    comparisons = {
        "quarantine_poison_baseline_update_full_minus_without_quarantine": (
            rates("full", "gradual_poisoning", "baseline_updated", True),
            rates("without_quarantine", "gradual_poisoning", "baseline_updated", True),
        ),
        "intent_poison_baseline_update_full_minus_without_intent": (
            rates("full", "gradual_poisoning", "baseline_updated", True),
            rates("without_intent", "gradual_poisoning", "baseline_updated", True),
        ),
        "causal_drift_intervention_full_minus_without_causal": (
            rates("full", "legitimate_drift", "intervened"),
            rates("without_causal", "legitimate_drift", "intervened"),
        ),
    }
    result = {}
    for name, (a, b) in comparisons.items():
        test = exact_paired_sign_flip(a, b)
        ci = paired_bootstrap_difference(a, b, resamples=resamples)
        result[name] = {
            "full_rates": a,
            "comparison_rates": b,
            "test": test,
            "difference_ci": ci.to_dict() if ci else None,
        }
    return {
        "comparisons": result,
        "note": "Adaptive phase is separate from held-out TEST. Seed is the paired unit; no test threshold was changed.",
    }


def analyze_existing_baselines(
    results_root: str, output: str, resamples: int = 20_000
) -> dict[str, Any]:
    root = Path(results_root)
    models = [path.name for path in root.iterdir() if (path / "per_seed").is_dir()]
    loaded = {
        model: [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((root / model / "per_seed").glob("seed-*.json"))
        ]
        for model in models
    }
    confidence, comparisons = {}, {}
    for model, results in loaded.items():
        confidence[model] = {}
        for metric in MAJOR_METRICS:
            values = [
                item["metrics"][metric] for item in results if item["metrics"][metric] is not None
            ]
            ci = bootstrap_mean_ci(values, resamples=resamples)
            confidence[model][metric] = ci.to_dict() if ci else None
    sentinel = loaded["sentinel"]
    raw_p = {}
    wilcoxon_raw_p = {}
    for model, results in loaded.items():
        if model == "sentinel":
            continue
        comparisons[model] = {}
        for metric in MAJOR_METRICS:
            pairs = [
                (a["metrics"][metric], b["metrics"][metric])
                for a, b in zip(sentinel, results, strict=False)
                if a["metrics"][metric] is not None and b["metrics"][metric] is not None
            ]
            a, b = [p[0] for p in pairs], [p[1] for p in pairs]
            test = exact_paired_sign_flip(a, b)
            wilcoxon = wilcoxon_signed_rank(a, b)
            ci = paired_bootstrap_difference(a, b, resamples=resamples)
            comparisons[model][metric] = {
                "test": test,
                "wilcoxon": wilcoxon,
                "difference_ci": ci.to_dict() if ci else None,
            }
            if metric == "f1":
                if test:
                    raw_p[model] = float(test["p_value_two_sided"])
                if wilcoxon:
                    wilcoxon_raw_p[model] = float(wilcoxon["p_value_two_sided"])
    adjusted = holm_adjust(raw_p)
    wilcoxon_adjusted = holm_adjust(wilcoxon_raw_p)
    for model, value in adjusted.items():
        comparisons[model]["f1"]["holm_adjusted_p"] = value
    for model, value in wilcoxon_adjusted.items():
        comparisons[model]["f1"]["wilcoxon_holm_p"] = value
    result = {
        "confidence_intervals": confidence,
        "paired_sentinel_minus_baseline": comparisons,
        "note": "Exact paired sign-flip and Wilcoxon signed-rank tests use matched seeds; Holm correction is applied to F1 baseline comparisons.",
    }
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
