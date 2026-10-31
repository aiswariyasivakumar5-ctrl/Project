from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any

SEEDS = (42, 123, 456, 789, 1001)
MODELS = (
    "sentinel",
    "isolation_forest",
    "one_class_svm",
    "dense_autoencoder",
    "lstm",
    "transformer",
)
METRICS = ("f1", "precision", "recall", "false_positive_rate", "auroc", "auprc")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_research_package(root: str | Path = ".") -> dict[str, Any]:
    base = Path(root)
    roots = {
        model: base
        / (
            "results/baselines_sequence"
            if model in {"lstm", "transformer"}
            else "results/baselines_publication"
        )
        for model in MODELS
    }
    errors: list[str] = []
    checked: list[str] = []
    digests: dict[str, str] = {}
    loaded: dict[str, list[dict[str, Any]]] = {}
    for model, result_root in roots.items():
        aggregate_path = result_root / "aggregate" / "metrics.json"
        if not aggregate_path.exists():
            errors.append(f"missing {aggregate_path}")
            continue
        aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))[model]
        checked.append(str(aggregate_path))
        digests[str(aggregate_path)] = _digest(aggregate_path)
        loaded[model] = []
        for seed in SEEDS:
            path = result_root / model / "per_seed" / f"seed-{seed}.json"
            if not path.exists():
                errors.append(f"missing {path}")
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
            loaded[model].append(value)
            checked.append(str(path))
            digests[str(path)] = _digest(path)
            if value.get("seed") != seed or value.get("model") != model:
                errors.append(f"identity mismatch {path}")
            sizes = value.get("dataset_sizes", {})
            if sizes.get("train") != 5000 or sizes.get("validation") != 1000:
                errors.append(f"unexpected publication split {path}: {sizes}")
            if value.get("calibration", {}).get("test_used_for_threshold") is not False:
                errors.append(f"test threshold leakage flag {path}")
            for metric in METRICS:
                number = value.get("metrics", {}).get(metric)
                if (
                    number is None
                    or not math.isfinite(float(number))
                    or not 0 <= float(number) <= 1
                ):
                    errors.append(f"invalid {metric} in {path}: {number}")
        if len(loaded[model]) == len(SEEDS):
            for metric in METRICS:
                mean = statistics.mean(item["metrics"][metric] for item in loaded[model])
                stored = aggregate[metric]["mean"]
                if not math.isclose(mean, stored, rel_tol=0, abs_tol=1e-12):
                    errors.append(f"aggregate mismatch {model}.{metric}: {mean} != {stored}")
    required = [
        "results/ablations_publication/aggregate/metrics.json",
        "results/ablations_publication/aggregate/statistics.json",
        "results/ablations_publication/aggregate/adaptive_statistics.json",
        "results/statistical_analysis/baseline_statistics.json",
        "results/tradeoff_diagnostics/summary.json",
        "results/fusion_study/results.json",
        "results/sequence_publication/sequence_analysis.json",
        "results/final/master_model_comparison.md",
        "results/final/master_per_attack.md",
        "results/final/master_ablation.md",
        "results/final/FINAL_RESEARCH_SYNTHESIS.md",
    ]
    for relative in required:
        path = base / relative
        if not path.exists():
            errors.append(f"missing {relative}")
        else:
            checked.append(relative)
            digests[relative] = _digest(path)
    final_table = base / "results/final/master_model_comparison.md"
    if final_table.exists():
        text = final_table.read_text(encoding="utf-8")
        for model, values in loaded.items():
            if model not in text:
                errors.append(f"master comparison missing {model}")
            if values:
                expected = f"{statistics.mean(x['metrics']['f1'] for x in values):.4f}"
                if expected not in text:
                    errors.append(f"master comparison missing {model} F1 {expected}")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "checked_file_count": len(set(checked)),
        "models": list(loaded),
        "seeds": list(SEEDS),
        "sha256_read_only_inventory": digests,
        "overwrite_note": "Hashes document files as read. Historical overwrite detection requires an earlier signed manifest.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only verification of retained MCP Runtime Sentinel research artifacts"
    )
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    report = verify_research_package(args.root)
    print(json.dumps(report, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
