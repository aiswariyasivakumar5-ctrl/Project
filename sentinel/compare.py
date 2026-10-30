from __future__ import annotations

import copy
import csv
import json
import platform
import statistics
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .comparison_data import ComparisonDataset, DatasetRow, build_comparison_dataset
from .engine import EngineConfig, SentinelEngine
from .metrics import Observation, calculate_metrics
from .ml_baselines import DETECTORS
from .ml_features import FEATURE_DESCRIPTION, feature_matrix
from .sequence_baselines import SEQUENCE_DETECTORS
from .sequence_features import SEQUENCE_FEATURE_DESCRIPTION, SequencePreprocessor

MODEL_NAMES = [
    "sentinel",
    "isolation_forest",
    "one_class_svm",
    "dense_autoencoder",
    "lstm",
    "transformer",
]


@dataclass(frozen=True)
class CompareConfig:
    seeds: tuple[int, ...] = (42, 123, 456, 789, 1001)
    train_size: int = 5000
    validation_size: int = 1000
    test_size: int = 3000
    models: tuple[str, ...] = tuple(MODEL_NAMES)
    validation_fpr: float = 0.01
    output: str = "results/baselines"
    engine: EngineConfig = EngineConfig()


def calibrate_threshold(validation_scores: np.ndarray, false_positive_rate: float = 0.01) -> float:
    """Calibrate decision threshold on validation scores targeting false_positive_rate.

    Deterministic Tie-Handling Rule:
    When score distributions contain tied values (such as discrete causal or policy floors),
    standard quantile interpolation is ambiguous. Under the strict decision rule (score > threshold),
    this function selects the threshold T using the right-continuous upper quantile (method='higher').

    If multiple scores are tied at T (e.g. the causal floor at 0.50):
      1. Strict comparison (score > T) is enforced, guaranteeing that the empirical validation
         false positive rate strictly respects the budget: P(score > T) <= false_positive_rate.
      2. If non-strict comparison (score >= T) were used, the tie mass would cause an FPR spike.
         Therefore, threshold semantics are strictly defined as score > T.
    """
    if not 0 < false_positive_rate < 1:
        raise ValueError("validation false-positive rate must be between zero and one")
    scores_arr = np.asarray(validation_scores, dtype=float)
    if len(scores_arr) == 0:
        raise ValueError("validation scores must be nonempty")
    return float(np.quantile(scores_arr, 1 - false_positive_rate, method="higher"))


def percentile_scores(validation_scores: np.ndarray, values: np.ndarray) -> np.ndarray:
    ordered = np.sort(validation_scores)
    return np.searchsorted(ordered, values, side="right") / len(ordered)


def _sentinel_scores(
    dataset: ComparisonDataset, seed: int, config: EngineConfig
) -> tuple[np.ndarray, np.ndarray, dict[str, Any], float, float]:
    engine = SentinelEngine(warmup_events=20, config=config)
    train_started = time.perf_counter()
    for row in dataset.train:
        engine.evaluate(row.interaction, learn=True, trusted_enrollment=True)
    fit_seconds = time.perf_counter() - train_started
    trained = copy.deepcopy(engine)
    validation = np.asarray(
        [engine.evaluate(row.interaction, learn=False).anomaly_score for row in dataset.validation]
    )
    engine = trained
    started = time.perf_counter()
    test = np.asarray(
        [engine.evaluate(row.interaction, learn=False).anomaly_score for row in dataset.test]
    )
    inference_ms = (time.perf_counter() - started) * 1000 / len(dataset.test)
    return validation, test, {"seed": seed, "engine": asdict(config)}, fit_seconds, inference_ms


def _baseline_scores(
    model_name: str, dataset: ComparisonDataset, seed: int
) -> tuple[np.ndarray, np.ndarray, dict[str, Any], float, float]:
    if model_name in SEQUENCE_DETECTORS:
        detector = SEQUENCE_DETECTORS[model_name](seed=seed)
        preprocessor = SequencePreprocessor(detector.sequence_length)
        train_x = preprocessor.fit([copy.deepcopy(row.interaction) for row in dataset.train])
        validation_x = preprocessor.transform(
            [copy.deepcopy(row.interaction) for row in dataset.validation]
        )
        test_x = preprocessor.transform([copy.deepcopy(row.interaction) for row in dataset.test])
        tracemalloc.start()
        started = time.perf_counter()
        detector.fit(train_x)
        fit_seconds = time.perf_counter() - started
        validation = detector.score(validation_x)
        started = time.perf_counter()
        test = detector.score(test_x)
        inference_ms = (time.perf_counter() - started) * 1000 / len(test_x)
        _, peak_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        configuration = {
            **detector.configuration,
            "preprocessing": SEQUENCE_FEATURE_DESCRIPTION,
            "preprocessing_fit": "TRAIN only",
            "peak_tracemalloc_bytes": peak_memory,
        }
        return validation, test, configuration, fit_seconds, inference_ms
    train_x = feature_matrix([copy.deepcopy(row.interaction) for row in dataset.train])
    validation_x = feature_matrix([copy.deepcopy(row.interaction) for row in dataset.validation])
    test_x = feature_matrix([copy.deepcopy(row.interaction) for row in dataset.test])
    detector = DETECTORS[model_name](seed=seed)
    started = time.perf_counter()
    detector.fit(train_x)
    fit_seconds = time.perf_counter() - started
    validation = detector.score(validation_x)
    started = time.perf_counter()
    test = detector.score(test_x)
    inference_ms = (time.perf_counter() - started) * 1000 / len(test_x)
    return validation, test, detector.configuration, fit_seconds, inference_ms


def _metrics(
    rows: list[DatasetRow],
    scores: np.ndarray,
    raw_scores: np.ndarray,
    threshold: float,
    inference_ms: float,
) -> dict[str, Any]:
    observations = [
        Observation(
            row.malicious,
            bool(raw > threshold),
            float(score),
            0.0,
            0.0,
            inference_ms,
            inference_ms,
            index,
        )
        for index, (row, score, raw) in enumerate(zip(rows, scores, raw_scores, strict=False))
    ]
    return calculate_metrics(
        observations, next((i for i, row in enumerate(rows) if row.malicious), None)
    )


def evaluate_model(
    model_name: str,
    dataset: ComparisonDataset,
    seed: int,
    validation_fpr: float,
    engine_config: EngineConfig,
) -> dict[str, Any]:
    if model_name == "sentinel":
        validation_raw, test_raw, model_config, fit_seconds, inference_ms = _sentinel_scores(
            dataset, seed, engine_config
        )
    else:
        validation_raw, test_raw, model_config, fit_seconds, inference_ms = _baseline_scores(
            model_name, dataset, seed
        )
    threshold = calibrate_threshold(validation_raw, validation_fpr)
    scores = percentile_scores(validation_raw, test_raw)
    overall = _metrics(dataset.test, scores, test_raw, threshold, inference_ms)
    per_scenario, per_server = {}, {}
    for scenario in sorted({row.scenario for row in dataset.test}):
        indices = [index for index, row in enumerate(dataset.test) if row.scenario == scenario]
        per_scenario[scenario] = _metrics(
            [dataset.test[i] for i in indices],
            scores[indices],
            test_raw[indices],
            threshold,
            inference_ms,
        )
    for server in sorted({row.interaction.server_id for row in dataset.test}):
        indices = [
            index for index, row in enumerate(dataset.test) if row.interaction.server_id == server
        ]
        per_server[server] = _metrics(
            [dataset.test[i] for i in indices],
            scores[indices],
            test_raw[indices],
            threshold,
            inference_ms,
        )
    outcomes = [
        {
            "index": index,
            "malicious": row.malicious,
            "scenario": row.scenario,
            "server_id": row.interaction.server_id,
            "session_id": row.interaction.session_id,
            "raw_score": float(raw),
            "score_percentile": float(score),
            "intervened": bool(raw > threshold),
        }
        for index, (row, raw, score) in enumerate(zip(dataset.test, test_raw, scores, strict=False))
    ]
    return {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seed": seed,
        "model": model_name,
        "dataset_sizes": {
            "train": len(dataset.train),
            "validation": len(dataset.validation),
            "test": len(dataset.test),
        },
        "model_configuration": model_config,
        "feature_representation": (
            "Sentinel raw interaction architecture"
            if model_name == "sentinel"
            else SEQUENCE_FEATURE_DESCRIPTION
            if model_name in SEQUENCE_DETECTORS
            else FEATURE_DESCRIPTION
        ),
        "sequence_length": model_config.get("sequence_length")
        if model_name in SEQUENCE_DETECTORS
        else None,
        "calibration": {
            "rule": f"global {(1 - validation_fpr) * 100:.1f}th percentile of normal validation anomaly scores",
            "validation_fpr_target": validation_fpr,
            "raw_threshold": threshold,
            "test_used_for_threshold": False,
        },
        "fit_seconds": fit_seconds,
        "offline_inference_mean_ms": inference_ms,
        "metrics": overall,
        "per_scenario": per_scenario,
        "per_server": per_server,
        "event_outcomes": outcomes,
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "platform": platform.platform(),
        },
    }


def _aggregate(values: list[float | int | None]) -> dict[str, float] | None:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return None
    return {
        "mean": statistics.mean(clean),
        "std": statistics.stdev(clean) if len(clean) > 1 else 0.0,
        "min": min(clean),
        "max": max(clean),
    }


def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    major = [
        "precision",
        "recall",
        "f1",
        "false_positive_rate",
        "attack_detection_rate",
        "detection_delay_events",
        "auroc",
        "auprc",
        "mean_risk",
    ]
    aggregate: dict[str, Any] = {}
    for model in sorted({result["model"] for result in results}):
        selected = [result for result in results if result["model"] == model]
        aggregate[model] = {
            metric: _aggregate([item["metrics"][metric] for item in selected]) for metric in major
        }
        aggregate[model]["offline_inference_mean_ms"] = _aggregate(
            [item["offline_inference_mean_ms"] for item in selected]
        )
    return aggregate


def run_comparison(config: CompareConfig) -> dict[str, Any]:
    invalid = set(config.models) - set(MODEL_NAMES)
    if invalid:
        raise ValueError(f"Unknown models: {sorted(invalid)}")
    results = []
    root = Path(config.output)
    for seed in config.seeds:
        dataset = build_comparison_dataset(
            seed, config.train_size, config.validation_size, config.test_size
        )
        for model in config.models:
            result = evaluate_model(model, dataset, seed, config.validation_fpr, config.engine)
            results.append(result)
            folder = root / model / "per_seed"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"seed-{seed}.json").write_text(
                json.dumps(result, indent=2), encoding="utf-8"
            )
    aggregate = aggregate_results(results)
    aggregate_folder = root / "aggregate"
    aggregate_folder.mkdir(parents=True, exist_ok=True)
    (aggregate_folder / "metrics.json").write_text(
        json.dumps(aggregate, indent=2), encoding="utf-8"
    )
    rows = []
    for result in results:
        rows.append(
            {
                "seed": result["seed"],
                "model": result["model"],
                **{
                    key: result["metrics"][key]
                    for key in [
                        "precision",
                        "recall",
                        "f1",
                        "false_positive_rate",
                        "auroc",
                        "auprc",
                    ]
                },
                "offline_inference_mean_ms": result["offline_inference_mean_ms"],
            }
        )
    with (root / "per_seed.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    scenario_rows = []
    for result in results:
        for scenario, metrics in result["per_scenario"].items():
            scenario_rows.append(
                {
                    "seed": result["seed"],
                    "model": result["model"],
                    "scenario": scenario,
                    **{
                        key: metrics[key]
                        for key in [
                            "precision",
                            "recall",
                            "f1",
                            "false_positive_rate",
                            "detection_delay_events",
                            "auroc",
                            "auprc",
                        ]
                    },
                }
            )
    scenario_folder = root / "per_scenario"
    scenario_folder.mkdir(parents=True, exist_ok=True)
    with (scenario_folder / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(scenario_rows[0]))
        writer.writeheader()
        writer.writerows(scenario_rows)
    return {"configuration": asdict(config), "aggregate": aggregate, "results": results}


def generate_report(results_root: str, output: str | None = None) -> str:
    root = Path(results_root)
    aggregate = json.loads((root / "aggregate" / "metrics.json").read_text(encoding="utf-8"))
    headers = ["Model", "F1", "FPR", "Recall", "Precision", "Delay", "AUROC", "AUPRC", "Latency ms"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for model, metrics in aggregate.items():

        def cell(name: str, metrics=metrics) -> str:
            value = metrics.get(name)
            return "-" if value is None else f"{value['mean']:.4f} +/- {value['std']:.4f}"

        lines.append(
            "| "
            + " | ".join(
                [
                    model,
                    cell("f1"),
                    cell("false_positive_rate"),
                    cell("recall"),
                    cell("precision"),
                    cell("detection_delay_events"),
                    cell("auroc"),
                    cell("auprc"),
                    cell("offline_inference_mean_ms"),
                ]
            )
            + " |"
        )
    table = "\n".join(lines)
    target = Path(output) if output else root / "aggregate" / "conference-table.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(table + "\n", encoding="utf-8")
    return table
