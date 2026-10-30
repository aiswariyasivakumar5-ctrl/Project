"""Comprehensive reconciliation between Decision-Rule and Score-Sweep operating points.

Derives all numbers directly from raw evaluation files in results/baselines_20seed/.
Writes all outputs to NEW directory results/matched_fpr_v2/.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import numpy as np


def bootstrap_ci(values: list[float], n_boot: int = 10000, alpha: float = 0.05, seed: int = 42) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    arr = np.asarray(values)
    if len(arr) == 0:
        return (0.0, 0.0)
    if np.all(arr == arr[0]):
        return (float(arr[0]), float(arr[0]))
    boot_means = [np.mean(rng.choice(arr, size=len(arr), replace=True)) for _ in range(n_boot)]
    low = float(np.percentile(boot_means, 100 * (alpha / 2)))
    high = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))
    return (low, high)


def main() -> None:
    models = ["sentinel", "dense_autoencoder", "lstm", "transformer", "one_class_svm", "isolation_forest"]
    base_dir = Path("results/baselines_20seed")
    out_dir = Path("results/matched_fpr_v2")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Basis (a): Decision-Rule Operating Points
    decision_data: dict[str, dict[str, list[float]]] = {
        m: {"recall": [], "fpr": [], "f1": [], "precision": []} for m in models
    }

    # 2. Basis (b): Descriptive test-set ROC sweeps at fixed test FPR targets.
    # These thresholds use test benign scores and are not held-out calibration.
    target_fprs = [0.0001, 0.001, 0.01, 0.05, 0.08]
    raw_sweep_data: dict[str, dict[float, list[float]]] = {
        m: {tf: [] for tf in target_fprs} for m in models
    }

    # 3. Basis (c): Stored percentile ROC curve sweep
    stored_pct_sweep_data: dict[str, dict[float, list[float]]] = {
        m: {tf: [] for tf in target_fprs} for m in models
    }

    # Tie analysis
    tie_stats: dict[str, dict[str, Any]] = {m: {} for m in models}

    for s in range(20001, 20021):
        for m in models:
            p = base_dir / m / "per_seed" / f"seed-{s}.json"
            d = json.loads(p.read_text(encoding="utf-8"))

            # Basis (a): Decision rule metrics
            metrics = d["metrics"]
            decision_data[m]["recall"].append(metrics["recall"])
            decision_data[m]["fpr"].append(metrics["false_positive_rate"])
            decision_data[m]["f1"].append(metrics["f1"])
            decision_data[m]["precision"].append(metrics["precision"])

            # Basis (b): Raw score sweep
            outcomes = d["event_outcomes"]
            benign_raw = [e["raw_score"] for e in outcomes if not e["malicious"]]
            mal_raw = [e["raw_score"] for e in outcomes if e["malicious"]]
            sorted_benign = sorted(benign_raw, reverse=True)
            n_benign = len(benign_raw)
            n_mal = len(mal_raw)

            for tf in target_fprs:
                max_fp = int(tf * n_benign)
                if max_fp == 0:
                    th = max(sorted_benign)
                    tp = sum(score > th for score in mal_raw)
                else:
                    th = sorted_benign[max_fp]
                    tp = sum(score > th for score in mal_raw)
                raw_sweep_data[m][tf].append(tp / n_mal)

            # Basis (c): Stored ROC curve points
            roc = metrics["roc_curve"]
            for tf in target_fprs:
                eligible = [pt["tpr"] for pt in roc if pt["fpr"] <= tf]
                stored_pct_sweep_data[m][tf].append(max(eligible) if eligible else 0.0)

            # Record tie statistics on seed 20001
            if s == 20001:
                benign_pct_1 = sum(1 for e in outcomes if not e["malicious"] and e["score_percentile"] >= 1.0)
                mal_pct_1 = sum(1 for e in outcomes if e["malicious"] and e["score_percentile"] >= 1.0)
                benign_raw_max = sum(1 for e in outcomes if not e["malicious"] and e["raw_score"] == max(benign_raw))
                tie_stats[m] = {
                    "benign_total": n_benign,
                    "malicious_total": n_mal,
                    "benign_percentile_1_0_count": benign_pct_1,
                    "malicious_percentile_1_0_count": mal_pct_1,
                    "benign_percentile_1_0_fraction": benign_pct_1 / n_benign,
                    "benign_raw_max_tie_count": benign_raw_max,
                }

    # Aggregate Basis (a)
    decision_summary = {}
    for m in models:
        decision_summary[m] = {}
        for metric in ["recall", "fpr", "f1", "precision"]:
            vals = decision_data[m][metric]
            mean_v = float(np.mean(vals))
            std_v = float(np.std(vals))
            ci_v = bootstrap_ci(vals)
            decision_summary[m][metric] = {
                "mean": mean_v,
                "std": std_v,
                "ci_95": ci_v,
                "min": float(np.min(vals)),
                "max": float(np.max(vals)),
                "per_seed": vals,
            }

    # Aggregate Basis (b)
    raw_sweep_summary = {}
    for m in models:
        raw_sweep_summary[m] = {}
        for tf in target_fprs:
            vals = raw_sweep_data[m][tf]
            raw_sweep_summary[m][str(tf)] = {
                "target_fpr": tf,
                "mean_recall": float(np.mean(vals)),
                "std_recall": float(np.std(vals)),
                "ci_95": bootstrap_ci(vals),
                "min": float(np.min(vals)),
                "max": float(np.max(vals)),
                "per_seed": vals,
            }

    # Aggregate Basis (c)
    stored_pct_summary = {}
    for m in models:
        stored_pct_summary[m] = {}
        for tf in target_fprs:
            vals = stored_pct_sweep_data[m][tf]
            stored_pct_summary[m][str(tf)] = {
                "target_fpr": tf,
                "mean_recall": float(np.mean(vals)),
                "std_recall": float(np.std(vals)),
                "ci_95": bootstrap_ci(vals),
                "min": float(np.min(vals)),
                "max": float(np.max(vals)),
                "per_seed": vals,
            }

    # Save JSON files
    (out_dir / "decision_rule_operating_points.json").write_text(json.dumps(decision_summary, indent=2), encoding="utf-8")
    (out_dir / "raw_score_matched_fpr.json").write_text(json.dumps(raw_sweep_summary, indent=2), encoding="utf-8")
    (out_dir / "stored_percentile_roc_sweep.json").write_text(json.dumps(stored_pct_summary, indent=2), encoding="utf-8")
    (out_dir / "tie_statistics.json").write_text(json.dumps(tie_stats, indent=2), encoding="utf-8")

    # Generate Markdown Table: Basis (a)
    md_decision = [
        "# Basis (a): Actual Decision-Rule Operating Points (20 Seeds)",
        "",
        "Evaluates the true runtime decision rule for every model (validation-calibrated thresholding).",
        "Thresholds were calibrated strictly on benign validation splits (1% FPR target) and applied held-out to test splits.",
        "",
        "| Model | Recall (Mean ± Std [95% CI]) | Test FPR (Mean ± Std [95% CI]) | F1 Score (Mean ± Std [95% CI]) | Precision |",
        "|---|---:|---:|---:|---:|",
    ]
    for m in models:
        r = decision_summary[m]["recall"]
        f = decision_summary[m]["fpr"]
        f1 = decision_summary[m]["f1"]
        p = decision_summary[m]["precision"]
        md_decision.append(
            f"| **{m}** | {r['mean']:.4f} ± {r['std']:.4f} [{r['ci_95'][0]:.4f}, {r['ci_95'][1]:.4f}] | "
            f"{f['mean']:.4f} ± {f['std']:.4f} [{f['ci_95'][0]:.4f}, {f['ci_95'][1]:.4f}] | "
            f"{f1['mean']:.4f} ± {f1['std']:.4f} [{f1['ci_95'][0]:.4f}, {f1['ci_95'][1]:.4f}] | "
            f"{p['mean']:.4f} |"
        )
    (out_dir / "decision_rule_operating_points.md").write_text("\n".join(md_decision), encoding="utf-8")

    # Generate Markdown Table: Basis (b)
    md_raw = [
        "# Basis (b): Raw-Score Threshold Sweep at Fixed Test FPR Targets (20 Seeds)",
        "",
        "Evaluates recall when thresholds are swept directly over continuous/raw anomaly scores,",
        "resolving ties at the boundary strictly (score > threshold).",
        "Thresholds are selected using the same test-set benign scores, so these are descriptive test ROC results, not independently calibrated operating-point estimates.",
        "",
        "| Model | Matched Recall at FPR <= 0.01% | Matched Recall at FPR <= 0.1% | Matched Recall at FPR <= 1.0% | Matched Recall at FPR <= 5.0% | Matched Recall at FPR <= 8.0% |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for m in models:
        row_strs = []
        for tf in target_fprs:
            s = raw_sweep_summary[m][str(tf)]
            row_strs.append(f"{s['mean_recall']:.4f} [{s['ci_95'][0]:.4f}, {s['ci_95'][1]:.4f}]")
        md_raw.append(f"| **{m}** | " + " | ".join(row_strs) + " |")
    (out_dir / "raw_score_matched_fpr.md").write_text("\n".join(md_raw), encoding="utf-8")

    # Generate CSV Exports
    with open(out_dir / "decision_rule_operating_points.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["model", "recall_mean", "recall_ci_low", "recall_ci_high", "fpr_mean", "fpr_ci_low", "fpr_ci_high", "f1_mean", "precision_mean"])
        for m in models:
            w.writerow([
                m,
                f"{decision_summary[m]['recall']['mean']:.4f}",
                f"{decision_summary[m]['recall']['ci_95'][0]:.4f}",
                f"{decision_summary[m]['recall']['ci_95'][1]:.4f}",
                f"{decision_summary[m]['fpr']['mean']:.4f}",
                f"{decision_summary[m]['fpr']['ci_95'][0]:.4f}",
                f"{decision_summary[m]['fpr']['ci_95'][1]:.4f}",
                f"{decision_summary[m]['f1']['mean']:.4f}",
                f"{decision_summary[m]['precision']['mean']:.4f}",
            ])

    with open(out_dir / "raw_score_matched_fpr.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["model"] + [f"recall_fpr_{tf*100:.2f}pct" for tf in target_fprs])
        for m in models:
            w.writerow([m] + [f"{raw_sweep_summary[m][str(tf)]['mean_recall']:.4f}" for tf in target_fprs])

    print("Reconciliation outputs generated in results/matched_fpr_v2/")


if __name__ == "__main__":
    main()
