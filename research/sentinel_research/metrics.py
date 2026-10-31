from __future__ import annotations

import math
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    malicious: bool
    intervened: bool
    risk: float
    trust: float
    uncertainty: float
    latency_ms: float
    analysis_latency_ms: float
    index: int


def _auc(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 2:
        return None
    ordered = sorted(points)
    return sum(
        (x2 - x1) * (y1 + y2) / 2 for (x1, y1), (x2, y2) in zip(ordered, ordered[1:], strict=False)
    )


def score_curves(
    observations: list[Observation],
) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    positives = sum(item.malicious for item in observations)
    negatives = len(observations) - positives
    if not positives or not negatives:
        return [], []
    thresholds = sorted({0.0, 1.0, *(item.risk for item in observations)}, reverse=True)
    # An explicit empty-selection endpoint is needed when maximum scores tie
    # at 1.0. Keep thresholds finite so result files remain valid JSON.
    roc = [{"threshold": math.nextafter(max(thresholds), math.inf), "fpr": 0.0, "tpr": 0.0}]
    pr = [{"threshold": roc[0]["threshold"], "recall": 0.0, "precision": 1.0}]
    for threshold in thresholds:
        tp = sum(item.malicious and item.risk >= threshold for item in observations)
        fp = sum(not item.malicious and item.risk >= threshold for item in observations)
        roc.append({"threshold": threshold, "fpr": fp / negatives, "tpr": tp / positives})
        pr.append(
            {
                "threshold": threshold,
                "recall": tp / positives,
                "precision": tp / (tp + fp) if tp + fp else 1.0,
            }
        )
    return roc, pr


def _average_precision(points: list[dict[str, float]]) -> float | None:
    if not points:
        return None
    previous_recall = 0.0
    area = 0.0
    for point in points:
        recall = point["recall"]
        if recall > previous_recall:
            area += (recall - previous_recall) * point["precision"]
            previous_recall = recall
    return area


def calculate_metrics(
    observations: list[Observation], attack_start: int | None = None
) -> dict[str, object]:
    tp = sum(item.malicious and item.intervened for item in observations)
    tn = sum(not item.malicious and not item.intervened for item in observations)
    fp = sum(not item.malicious and item.intervened for item in observations)
    fn = sum(item.malicious and not item.intervened for item in observations)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    roc, pr = score_curves(observations)
    roc_points = [(item["fpr"], item["tpr"]) for item in roc]
    first_detection = next(
        (item.index for item in observations if item.malicious and item.intervened), None
    )
    delay = (
        None
        if attack_start is None or first_detection is None
        else max(0, first_detection - attack_start)
    )
    latencies = [item.latency_ms for item in observations] or [0.0]
    analysis = [item.analysis_latency_ms for item in observations] or [0.0]
    sorted_latency = sorted(latencies)

    def percentile(p):
        return sorted_latency[min(len(sorted_latency) - 1, math.ceil(p * len(sorted_latency)) - 1)]

    ece = 0.0
    for lower in [index / 10 for index in range(10)]:
        bucket = [
            item
            for item in observations
            if lower <= item.risk < lower + 0.1 or (lower == 0.9 and item.risk == 1.0)
        ]
        if bucket:
            ece += (
                len(bucket)
                / len(observations)
                * abs(
                    statistics.mean(item.risk for item in bucket)
                    - statistics.mean(item.malicious for item in bucket)
                )
            )
    return {
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0,
        "attack_detection_rate": recall,
        "detection_delay_events": delay,
        "mean_risk": statistics.mean(item.risk for item in observations),
        "mean_trust": statistics.mean(item.trust for item in observations),
        "intervention_rate": statistics.mean(item.intervened for item in observations),
        "latency_ms": {
            "mean": statistics.mean(latencies),
            "median": statistics.median(latencies),
            "p95": percentile(0.95),
            "p99": percentile(0.99),
        },
        "sentinel_evaluation_mean_ms": statistics.mean(analysis),
        "throughput_rps_sequential": 1000 / statistics.mean(latencies)
        if statistics.mean(latencies)
        else None,
        "auroc": _auc(roc_points),
        "auprc": _average_precision(pr),
        "risk_ece": ece,
        "roc_curve": roc,
        "precision_recall_curve": pr,
        "risk_distribution": [item.risk for item in observations],
        "trust_distribution": [item.trust for item in observations],
    }
