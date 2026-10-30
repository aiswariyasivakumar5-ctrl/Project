from __future__ import annotations

import copy
import csv
import json
import statistics
from pathlib import Path
from typing import Any

import numpy as np

from .compare import calibrate_threshold
from .comparison_data import build_comparison_dataset
from .ml_features import simulated_response
from .models import Interaction
from .scenarios import PRIMARY, SECONDARY, build_scenarios
from .sequence_baselines import SEQUENCE_DETECTORS
from .sequence_features import SequencePreprocessor
from .statistics import bootstrap_mean_ci, exact_paired_sign_flip, paired_bootstrap_difference


def _prepare(event: Interaction) -> Interaction:
    value = copy.deepcopy(event)
    value.response = simulated_response(value)
    value.capability_digest = "cap-v1"
    return value


def _cases() -> dict[str, list[Interaction]]:
    return {
        "normal_within_session": [
            Interaction(
                PRIMARY,
                "safe_read",
                {"record_id": "record-1001"},
                None,
                18,
                "Read record 1001",
                session_id="known",
            ),
            Interaction(
                PRIMARY,
                "safe_read",
                {"record_id": "record-1002"},
                None,
                18,
                "Read record 1002",
                session_id="known",
            ),
        ],
        "abnormal_known_session": [
            Interaction(
                PRIMARY,
                "safe_read",
                {"record_id": "record-1001"},
                None,
                18,
                "Read record 1001",
                session_id="known",
            ),
            Interaction(
                PRIMARY,
                "export_data",
                {"scope": "all"},
                None,
                25,
                "Read record 1001",
                session_id="known",
            ),
        ],
        "abnormal_new_session": [
            Interaction(
                PRIMARY,
                "export_data",
                {"scope": "all"},
                None,
                25,
                "Read record 1001",
                session_id="new",
            )
        ],
        "cross_server_transition": [
            Interaction(
                PRIMARY,
                "safe_read",
                {"record_id": "canary-token"},
                None,
                18,
                "Read canary",
                session_id="cross",
            ),
            Interaction(
                SECONDARY,
                "export_data",
                {"payload": "canary-token"},
                None,
                25,
                "Read canary",
                session_id="cross",
            ),
        ],
    }


def auxiliary_sequence_evaluation(
    seed: int, model_name: str, train_size: int = 5000, validation_size: int = 1000
) -> dict[str, Any]:
    dataset = build_comparison_dataset(seed, train_size, validation_size, 120)
    detector = SEQUENCE_DETECTORS[model_name](seed=seed)
    prep = SequencePreprocessor(detector.sequence_length)
    train = prep.fit([copy.deepcopy(x.interaction) for x in dataset.train])
    detector.fit(train)
    validation = prep.transform([copy.deepcopy(x.interaction) for x in dataset.validation])
    threshold = calibrate_threshold(detector.score(validation), 0.01)
    scenario = build_scenarios(seed + 3, 200)["legitimate_drift"]
    drift_events = [_prepare(case.interaction) for case in scenario.cases]
    drift_scores = detector.score(prep.transform(drift_events))
    probes = {}
    for name, events in _cases().items():
        values = detector.score(prep.transform([_prepare(x) for x in events]))
        probes[name] = {
            "event_scores": [float(x) for x in values],
            "final_score": float(values[-1]),
            "intervened": bool(values[-1] > threshold),
            "threshold": threshold,
        }
    return {
        "seed": seed,
        "model": model_name,
        "threshold": threshold,
        "legitimate_drift": {
            "events": len(drift_scores),
            "intervention_rate": float(np.mean(drift_scores > threshold)),
            "mean_score": float(np.mean(drift_scores)),
            "scores": [float(x) for x in drift_scores],
        },
        "session_analysis": probes,
    }


def generate_sequence_report(
    sequence_root: str,
    approved_root: str,
    output: str,
    seeds: tuple[int, ...] = (42, 123, 456, 789, 1001),
) -> dict[str, Any]:
    sequence = Path(sequence_root)
    approved = Path(approved_root)
    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)
    models = (
        "sentinel",
        "isolation_forest",
        "one_class_svm",
        "dense_autoencoder",
        "lstm",
        "transformer",
    )
    roots = {name: (sequence if name in SEQUENCE_DETECTORS else approved) for name in models}
    loaded = {
        name: [
            json.loads(
                (roots[name] / name / "per_seed" / f"seed-{seed}.json").read_text(encoding="utf-8")
            )
            for seed in seeds
        ]
        for name in models
    }
    metrics = ("f1", "false_positive_rate", "recall", "precision", "auroc", "auprc")
    comparison = {
        name: {
            metric: {
                "mean": statistics.mean(x["metrics"][metric] for x in values),
                "std": statistics.stdev(x["metrics"][metric] for x in values),
            }
            for metric in metrics
        }
        for name, values in loaded.items()
    }
    auxiliary = {
        name: {str(seed): auxiliary_sequence_evaluation(seed, name) for seed in seeds}
        for name in SEQUENCE_DETECTORS
    }
    statistics_result = {}
    sentinel = loaded["sentinel"]
    for name in SEQUENCE_DETECTORS:
        statistics_result[name] = {}
        for metric in metrics:
            a = [x["metrics"][metric] for x in sentinel]
            b = [x["metrics"][metric] for x in loaded[name]]
            statistics_result[name][metric] = {
                "sentinel_minus_sequence": exact_paired_sign_flip(a, b),
                "difference_ci": paired_bootstrap_difference(a, b, resamples=20000).to_dict(),
                "sequence_ci": bootstrap_mean_ci(b, resamples=20000).to_dict(),
            }
    result = {
        "comparison": comparison,
        "auxiliary": auxiliary,
        "statistics": statistics_result,
        "note": "Seed is the paired independent unit; with five seeds, exact two-sided tests have low power. Auxiliary probes were not used for fitting or selection.",
    }
    (target / "sequence_analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with (target / "comparison.md").open("w", encoding="utf-8") as handle:
        handle.write(
            "| Model | F1 | FPR | Recall | Precision | AUROC | AUPRC |\n|---|---:|---:|---:|---:|---:|---:|\n"
        )
        for name in models:
            cells = [
                f"{comparison[name][m]['mean']:.4f} ± {comparison[name][m]['std']:.4f}"
                for m in metrics
            ]
            handle.write("| " + " | ".join([name, *cells]) + " |\n")
    rows = []
    for name, values in loaded.items():
        for value in values:
            for scenario, metrics_value in value["per_scenario"].items():
                rows.append(
                    {
                        "seed": value["seed"],
                        "model": name,
                        "scenario": scenario,
                        "recall": metrics_value["recall"],
                        "f1": metrics_value["f1"],
                        "fpr": metrics_value["false_positive_rate"],
                    }
                )
    for name, seeds_data in auxiliary.items():
        for seed, value in seeds_data.items():
            rows.append(
                {
                    "seed": seed,
                    "model": name,
                    "scenario": "legitimate_drift",
                    "recall": "",
                    "f1": "",
                    "fpr": value["legitimate_drift"]["intervention_rate"],
                }
            )
    with (target / "per_scenario.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return result
