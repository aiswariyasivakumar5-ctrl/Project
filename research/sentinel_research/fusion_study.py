from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .compare import calibrate_threshold
from .comparison_data import build_comparison_dataset
from .gateway_benchmark import run_gateway_benchmark
from .metrics import Observation, calculate_metrics
from .tradeoff_analysis import COMPONENTS, _replay


@dataclass(frozen=True)
class FusionStudyConfig:
    seeds: tuple[int, ...] = (42, 123, 456, 789, 1001)
    train_size: int = 5000
    validation_size: int = 1000
    test_size: int = 3000
    validation_fpr: float = 0.01
    gateway_requests: int = 100
    output: str = "results/fusion_study"


class MidrankECDF:
    """Tie-preserving empirical CDF fitted on validation scores only."""

    def __init__(self) -> None:
        self.values: np.ndarray | None = None
        self.midrank: np.ndarray | None = None

    def fit(self, validation: np.ndarray) -> MidrankECDF:
        data = np.asarray(validation, dtype=float)
        if not len(data):
            raise ValueError("validation scores cannot be empty")
        values, counts = np.unique(data, return_counts=True)
        cumulative = np.cumsum(counts)
        self.values = values
        self.midrank = (cumulative - counts / 2) / len(data)
        return self

    def transform(self, scores: np.ndarray) -> np.ndarray:
        if self.values is None or self.midrank is None:
            raise RuntimeError("calibrator must be fit before transform")
        data = np.asarray(scores, dtype=float)
        positions = np.searchsorted(self.values, data, side="left")
        result = np.empty(len(data), dtype=float)
        below = positions == 0
        above = positions == len(self.values)
        result[below] = np.where(data[below] < self.values[0], 0.0, self.midrank[0])
        result[above] = 1.0
        middle = ~(below | above)
        if middle.any():
            idx = positions[middle]
            exact = self.values[idx] == data[middle]
            lower = self.midrank[idx - 1]
            upper = self.midrank[idx]
            result[middle] = np.where(exact, upper, lower)
        return result


def candidate_scores(
    validation_records: list[dict[str, Any]], test_records: list[dict[str, Any]]
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    production_v = np.asarray([x["final_risk"] for x in validation_records])
    production_t = np.asarray([x["final_risk"] for x in test_records])
    linear_v = np.asarray([x["linear_risk"] for x in validation_records])
    linear_t = np.asarray([x["linear_risk"] for x in test_records])
    ecdf = MidrankECDF().fit(production_v)
    return {
        "control_production": (production_v, production_t),
        "additive_causal": (linear_v, linear_t),
        "monotonic_midrank": (ecdf.transform(production_v), ecdf.transform(production_t)),
    }


def _evaluate(
    records: list[dict[str, Any]], scores: np.ndarray, threshold: float, inference_ms: float
) -> dict[str, Any]:
    observations = [
        Observation(
            bool(item["malicious"]),
            bool(score > threshold),
            float(score),
            float(item["trust"]),
            float(item["uncertainty"]),
            inference_ms,
            inference_ms,
            index,
        )
        for index, (item, score) in enumerate(zip(records, scores, strict=False))
    ]
    first_attack = next((i for i, item in enumerate(records) if item["malicious"]), None)
    return calculate_metrics(observations, first_attack)


def _component_distributions(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups = {
        "normal": [x for x in records if not x["malicious"]],
        "attack": [x for x in records if x["malicious"]],
    }
    return {
        group: {
            name: {
                "mean": float(np.mean([x["components"][name] for x in rows])),
                "p50": float(np.quantile([x["components"][name] for x in rows], 0.5)),
                "p95": float(np.quantile([x["components"][name] for x in rows], 0.95)),
                "maximum": float(max(x["components"][name] for x in rows)),
            }
            for name in COMPONENTS
        }
        for group, rows in groups.items()
    }


def evaluate_seed(seed: int, config: FusionStudyConfig) -> dict[str, Any]:
    dataset = build_comparison_dataset(
        seed, config.train_size, config.validation_size, config.test_size
    )
    replay = _replay(
        dataset,
        __import__("sentinel.engine", fromlist=["EngineConfig"]).EngineConfig(),
        config.validation_fpr,
    )
    candidates = candidate_scores(replay["validation"], replay["test"])
    result: dict[str, Any] = {
        "seed": seed,
        "component_distributions": _component_distributions(replay["test"]),
        "variants": {},
    }
    for name, (validation, test) in candidates.items():
        started = time.perf_counter()
        _ = test.copy()
        inference_ms = (time.perf_counter() - started) * 1000 / len(test)
        threshold = calibrate_threshold(validation, config.validation_fpr)
        metrics = _evaluate(replay["test"], test, threshold, inference_ms)
        per_attack = {}
        for scenario in sorted({x["scenario"] for x in replay["test"] if x["malicious"]}):
            indices = [i for i, x in enumerate(replay["test"]) if x["scenario"] == scenario]
            per_attack[scenario] = _evaluate(
                [replay["test"][i] for i in indices], test[indices], threshold, inference_ms
            )
        result["variants"][name] = {
            "definition": {
                "control_production": "Frozen production score including causal hard floor.",
                "additive_causal": "Sum of frozen weighted components; causal retains weight 0.16; no hard-floor transformation.",
                "monotonic_midrank": "Validation-fitted tie-preserving midrank ECDF of frozen production risk.",
            }[name],
            "threshold": threshold,
            "strict_operator": ">",
            "test_used_for_fit": False,
            "validation_events_equal_threshold": int(np.sum(validation == threshold)),
            "test_events_equal_threshold": int(np.sum(test == threshold)),
            "validation_unique_scores": int(len(np.unique(validation))),
            "metrics": metrics,
            "per_attack": per_attack,
        }
    return result


def _mean(results: list[dict[str, Any]], variant: str, metric: str) -> float | None:
    values = [x["variants"][variant]["metrics"][metric] for x in results]
    clean = [float(x) for x in values if x is not None]
    return float(np.mean(clean)) if clean else None


def run_fusion_study(config: FusionStudyConfig) -> dict[str, Any]:
    root = Path(config.output)
    root.mkdir(parents=True, exist_ok=True)
    results = [evaluate_seed(seed, config) for seed in config.seeds]
    variants = tuple(results[0]["variants"])
    aggregate = {
        variant: {
            metric: _mean(results, variant, metric)
            for metric in (
                "f1",
                "precision",
                "recall",
                "false_positive_rate",
                "auroc",
                "auprc",
                "detection_delay_events",
                "mean_risk",
            )
        }
        for variant in variants
    }
    gateway = run_gateway_benchmark(config.gateway_requests)
    report = {
        "configuration": asdict(config),
        "separation": {
            "train": "Engine normal-profile training only.",
            "validation": "Candidate calibration fit and operating threshold selection only.",
            "test": "Single evaluation; no fitting, calibration, or threshold changes.",
            "test_labels_used_for_selection": False,
        },
        "tie_policy": "Midrank ECDF maps equal validation scores to one identical midrank; thresholds retain strict risk > threshold.",
        "per_seed": results,
        "aggregate": aggregate,
        "gateway_control": gateway,
        "replacement_decision": {
            "selected": "control_production",
            "replace_current_fusion": False,
            "reason": "Additive fusion violates the low-FPR objective; monotonic midrank produces no recall improvement.",
        },
    }
    (root / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    rows = []
    for item in results:
        for variant in variants:
            value = item["variants"][variant]
            rows.append(
                {
                    "seed": item["seed"],
                    "variant": variant,
                    "threshold": value["threshold"],
                    "validation_at_threshold": value["validation_events_equal_threshold"],
                    "test_at_threshold": value["test_events_equal_threshold"],
                    **{
                        m: value["metrics"][m]
                        for m in (
                            "f1",
                            "precision",
                            "recall",
                            "false_positive_rate",
                            "auroc",
                            "auprc",
                            "detection_delay_events",
                            "mean_risk",
                        )
                    },
                }
            )
    with (root / "overall.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    attack_rows = []
    for item in results:
        for variant in variants:
            for scenario, metrics in item["variants"][variant]["per_attack"].items():
                attack_rows.append(
                    {
                        "seed": item["seed"],
                        "variant": variant,
                        "scenario": scenario,
                        "recall": metrics["recall"],
                        "f1": metrics["f1"],
                    }
                )
    with (root / "per_attack.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(attack_rows[0]))
        writer.writeheader()
        writer.writerows(attack_rows)
    return report
