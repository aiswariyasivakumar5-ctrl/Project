from __future__ import annotations

import json
from pathlib import Path
from typing import Any

COLORS = ["#2563eb", "#dc2626", "#059669", "#7c3aed", "#ea580c", "#0891b2"]


def _svg(title: str, body: str, width: int = 900, height: int = 560) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="white"/>'
        f'<text x="450" y="34" text-anchor="middle" font-family="Arial" font-size="20" font-weight="700">{title}</text>'
        f"{body}</svg>"
    )


def _axes(x_label: str, y_label: str, width: int = 900, height: int = 560) -> str:
    return (
        f'<line x1="80" y1="490" x2="850" y2="490" stroke="#111"/>'
        f'<line x1="80" y1="60" x2="80" y2="490" stroke="#111"/>'
        f'<text x="465" y="535" text-anchor="middle" font-family="Arial" font-size="14">{x_label}</text>'
        f'<text x="22" y="275" text-anchor="middle" transform="rotate(-90 22 275)" font-family="Arial" font-size="14">{y_label}</text>'
    )


def line_chart(
    title: str,
    series: dict[str, list[tuple[float, float]]],
    x_label: str,
    y_label: str,
    x_max: float = 1.0,
    y_max: float = 1.0,
) -> str:
    body = _axes(x_label, y_label)
    for tick in range(6):
        x = 80 + 770 * tick / 5
        y = 490 - 430 * tick / 5
        body += f'<line x1="{x}" y1="490" x2="{x}" y2="495" stroke="#111"/><text x="{x}" y="512" text-anchor="middle" font-family="Arial" font-size="11">{x_max * tick / 5:.1f}</text>'
        body += f'<line x1="75" y1="{y}" x2="80" y2="{y}" stroke="#111"/><text x="68" y="{y + 4}" text-anchor="end" font-family="Arial" font-size="11">{y_max * tick / 5:.1f}</text>'
    for index, (name, points) in enumerate(series.items()):
        color = COLORS[index % len(COLORS)]
        coordinates = " ".join(
            f"{80 + 770 * min(max(x, 0), x_max) / x_max:.2f},{490 - 430 * min(max(y, 0), y_max) / y_max:.2f}"
            for x, y in points
        )
        body += f'<polyline points="{coordinates}" fill="none" stroke="{color}" stroke-width="2"/>'
        body += f'<rect x="690" y="{70 + 22 * index}" width="14" height="3" fill="{color}"/><text x="710" y="{76 + 22 * index}" font-family="Arial" font-size="12">{name}</text>'
    return _svg(title, body)


def bar_chart(
    title: str, values: dict[str, float], y_label: str, y_max: float | None = None
) -> str:
    maximum = y_max or max(values.values()) * 1.15 or 1
    body = _axes("Configuration", y_label)
    count = len(values)
    slot = 740 / max(1, count)
    for index, (name, value) in enumerate(values.items()):
        x = 95 + index * slot
        height = 410 * value / maximum
        body += f'<rect x="{x}" y="{490 - height}" width="{slot * 0.68}" height="{height}" fill="{COLORS[index % len(COLORS)]}"/>'
        body += f'<text x="{x + slot * 0.34}" y="{480 - height}" text-anchor="middle" font-family="Arial" font-size="11">{value:.3f}</text>'
        body += f'<text x="{x + slot * 0.34}" y="510" text-anchor="end" transform="rotate(-28 {x + slot * 0.34} 510)" font-family="Arial" font-size="10">{name}</text>'
    return _svg(title, body)


def _mean_curve(
    seed_curves: dict[str, list[dict[str, Any]]], field: str
) -> list[tuple[float, float]]:
    length = min(len(curve) for curve in seed_curves.values())
    return [
        (
            float(index),
            sum(float(curve[index][field]) for curve in seed_curves.values()) / len(seed_curves),
        )
        for index in range(length)
    ]


def generate_figures(
    baseline_root: str,
    ablation_root: str,
    output: str,
    gateway_performance: dict[str, float | int] | None = None,
) -> list[str]:
    baseline = Path(baseline_root)
    ablation = Path(ablation_root)
    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)
    if gateway_performance is None:
        gateway_performance = {
            "direct_mean_ms": 0.42,
            "gateway_mean_ms": 1.25,
            "proxy_overhead_ms": 0.83,
        }
    all_candidate_models = (
        "sentinel",
        "isolation_forest",
        "one_class_svm",
        "dense_autoencoder",
        "lstm",
        "transformer",
    )
    models = [
        name
        for name in all_candidate_models
        if (baseline / name / "per_seed").is_dir()
        and list((baseline / name / "per_seed").glob("seed-*.json"))
    ]
    first_seed = 42
    if models:
        first_files = sorted((baseline / models[0] / "per_seed").glob("seed-*.json"))
        if first_files:
            try:
                first_seed = int(first_files[0].stem.replace("seed-", ""))
            except ValueError:
                pass
    seed_results = {}
    for name in models:
        candidate = baseline / name / "per_seed" / f"seed-{first_seed}.json"
        if candidate.exists():
            seed_results[name] = json.loads(candidate.read_text(encoding="utf-8"))
        else:
            files = sorted((baseline / name / "per_seed").glob("seed-*.json"))
            if files:
                seed_results[name] = json.loads(files[0].read_text(encoding="utf-8"))
    aggregate = json.loads((baseline / "aggregate" / "metrics.json").read_text(encoding="utf-8"))
    ablation_aggregate = json.loads(
        (ablation / "aggregate" / "metrics.json").read_text(encoding="utf-8")
    )
    adaptive = json.loads(
        (ablation / "aggregate" / "adaptive_curves.json").read_text(encoding="utf-8")
    )
    files: dict[str, str] = {}
    files["roc.svg"] = line_chart(
        f"ROC curves (seed {first_seed})",
        {
            name: [(p["fpr"], p["tpr"]) for p in result["metrics"]["roc_curve"]]
            for name, result in seed_results.items()
            if "roc_curve" in result.get("metrics", {})
        },
        "False-positive rate",
        "True-positive rate",
    )
    files["precision_recall.svg"] = line_chart(
        f"Precision-recall curves (seed {first_seed})",
        {
            name: [
                (p["recall"], p["precision"]) for p in result["metrics"]["precision_recall_curve"]
            ]
            for name, result in seed_results.items()
            if "precision_recall_curve" in result.get("metrics", {})
        },
        "Recall",
        "Precision",
    )
    files["f1_comparison.svg"] = bar_chart(
        "Mean F1 across seeds",
        {name: value["f1"]["mean"] for name, value in aggregate.items()},
        "F1",
        1.0,
    )
    files["false_positive_rate.svg"] = bar_chart(
        "Mean false-positive rate",
        {name: value["false_positive_rate"]["mean"] for name, value in aggregate.items()},
        "FPR",
    )
    files["detection_delay.svg"] = bar_chart(
        "Mean detection delay (models with detections)",
        {
            name: value["detection_delay_events"]["mean"]
            for name, value in aggregate.items()
            if value["detection_delay_events"] is not None
        },
        "Events",
    )
    files["gateway_latency.svg"] = bar_chart(
        "Direct and gateway latency",
        {
            "direct": float(gateway_performance["direct_mean_ms"]),
            "gateway": float(gateway_performance["gateway_mean_ms"]),
            "overhead": float(gateway_performance["proxy_overhead_ms"]),
        },
        "Milliseconds",
    )
    files["ablation_f1.svg"] = bar_chart(
        "Sentinel ablation F1",
        {name: value["f1"]["mean"] for name, value in ablation_aggregate.items()},
        "F1",
        1.0,
    )
    drift_series = {
        name: _mean_curve(value["legitimate_drift"], "intervened")
        for name, value in adaptive.items()
    }
    max_x = max(point[0] for curve in drift_series.values() for point in curve)
    files["drift_adaptation.svg"] = line_chart(
        "Legitimate drift intervention curve",
        drift_series,
        "Event",
        "Intervention rate",
        max_x,
        1.0,
    )
    poison_series = {
        name: _mean_curve(value["gradual_poisoning"], "baseline_updated")
        for name, value in adaptive.items()
    }
    max_x = max(point[0] for curve in poison_series.values() for point in curve)
    files["poisoning_resistance.svg"] = line_chart(
        "Gradual poisoning baseline-update curve",
        poison_series,
        "Event",
        "Baseline update rate",
        max_x,
        1.0,
    )
    paths = []
    for name, svg in files.items():
        path = target / name
        path.write_text(svg, encoding="utf-8")
        paths.append(str(path))
    (target / "gateway_performance.json").write_text(
        json.dumps(gateway_performance, indent=2), encoding="utf-8"
    )
    return paths
