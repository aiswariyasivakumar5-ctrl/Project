from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np

from .compare import _baseline_scores, calibrate_threshold
from .comparison_data import build_comparison_dataset
from .engine import EngineConfig, SentinelEngine

WEAK_SCENARIOS = ["capability_drift", "low_and_slow", "gradual_poisoning", "abnormal_sequence"]


def isolation_forest_diagnostic(
    seeds: tuple[int, ...], train_size: int, validation_size: int, test_size: int
) -> dict[str, Any]:
    results = {}
    for seed in seeds:
        dataset = build_comparison_dataset(seed, train_size, validation_size, test_size)
        validation, test, configuration, _, _ = _baseline_scores("isolation_forest", dataset, seed)
        threshold = calibrate_threshold(validation, 0.01)
        malicious = np.asarray([row.malicious for row in dataset.test])
        normal_scores, attack_scores = test[~malicious], test[malicious]
        per_scenario = {}
        for scenario in sorted({row.scenario for row in dataset.test if row.malicious}):
            values = np.asarray(
                [
                    score
                    for row, score in zip(dataset.test, test, strict=False)
                    if row.malicious and row.scenario == scenario
                ]
            )
            per_scenario[scenario] = {
                "mean_raw_score": float(values.mean()),
                "maximum_raw_score": float(values.max()),
                "fraction_above_threshold": float((values > threshold).mean()),
            }
        results[str(seed)] = {
            "configuration": configuration,
            "validation_threshold": threshold,
            "validation_quantiles": {
                str(q): float(np.quantile(validation, q)) for q in (0.95, 0.99, 1.0)
            },
            "normal_test_quantiles": {
                str(q): float(np.quantile(normal_scores, q)) for q in (0.5, 0.95, 0.99, 1.0)
            },
            "attack_test_quantiles": {
                str(q): float(np.quantile(attack_scores, q)) for q in (0.5, 0.95, 0.99, 1.0)
            },
            "attack_fraction_above_threshold": float((attack_scores > threshold).mean()),
            "per_scenario": per_scenario,
        }
    return {
        "method": "Raw-score diagnostic; threshold remains fixed from normal validation.",
        "interpretation": "High AUROC with low threshold recall means rankings separate groups but the predeclared operating threshold lies above attack scores.",
        "seeds": results,
    }


def sentinel_weakness_diagnostic(
    seed: int, train_size: int, validation_size: int, test_size: int
) -> dict[str, Any]:
    dataset = build_comparison_dataset(seed, train_size, validation_size, test_size)
    engine = SentinelEngine(20, EngineConfig())
    for row in dataset.train:
        engine.evaluate(row.interaction, learn=True, trusted_enrollment=True)
    trained = copy.deepcopy(engine)
    validation = np.asarray(
        [engine.evaluate(row.interaction, learn=False).anomaly_score for row in dataset.validation]
    )
    threshold = calibrate_threshold(validation, 0.01)
    engine = trained
    grouped = {name: [] for name in WEAK_SCENARIOS}
    for row in dataset.test:
        verdict = engine.evaluate(row.interaction, learn=False)
        if row.malicious and row.scenario in grouped:
            grouped[row.scenario].append(verdict)
    scenarios = {}
    for name, verdicts in grouped.items():
        scenarios[name] = {
            "samples": len(verdicts),
            "recall_at_global_threshold": sum(v.anomaly_score > threshold for v in verdicts)
            / len(verdicts),
            "mean_risk": sum(v.anomaly_score for v in verdicts) / len(verdicts),
            "threshold": threshold,
            "mean_components": {
                component: sum(v.components[component] for v in verdicts) / len(verdicts)
                for component in verdicts[0].components
            },
            "explanation": {
                "capability_drift": "Attestation contributes risk, but its current fusion weight may remain below the global operating threshold.",
                "low_and_slow": "Gradual parameter changes often remain close to the learned structural distribution event-by-event.",
                "gradual_poisoning": "Held-out evaluation disables learning; poisoning resistance must be interpreted with the separate adaptive curve.",
                "abnormal_sequence": "New-session transition evidence is weak because the current sequence model is session-local.",
            }[name],
        }
    return {"seed": seed, "scenarios": scenarios, "threshold_source": "normal validation only"}


def write_diagnostics(
    output: str,
    seeds: tuple[int, ...] = (42, 123, 456, 789, 1001),
    train_size: int = 5000,
    validation_size: int = 1000,
    test_size: int = 3000,
) -> dict[str, Any]:
    result = {
        "isolation_forest": isolation_forest_diagnostic(
            seeds, train_size, validation_size, test_size
        ),
        "sentinel_weaknesses": sentinel_weakness_diagnostic(
            seeds[0], train_size, validation_size, test_size
        ),
    }
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
