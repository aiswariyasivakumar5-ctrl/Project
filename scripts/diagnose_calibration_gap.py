"""Diagnose baseline validation-to-test calibration gap across all 20 seeds."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

MODELS = ["dense_autoencoder", "lstm", "transformer", "isolation_forest", "one_class_svm", "sentinel"]
SEEDS = list(range(20001, 20021))


def diagnose_gap() -> dict:
    results = {}
    for model in MODELS:
        model_results = []
        for seed in SEEDS:
            path = Path(f"results/baselines_20seed/{model}/per_seed/seed-{seed}.json")
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            val_thresh = data["calibration"]["raw_threshold"]
            outcomes = data["event_outcomes"]
            benign = [o for o in outcomes if not o["malicious"]]

            by_scenario = defaultdict(list)
            for o in benign:
                by_scenario[o["scenario"]].append(o["intervened"])

            seed_stat = {
                "seed": seed,
                "val_threshold": val_thresh,
                "overall_test_benign": len(benign),
                "overall_fp": sum(o["intervened"] for o in benign),
                "overall_fpr": sum(o["intervened"] for o in benign) / len(benign),
                "by_scenario": {
                    scen: {
                        "count": len(flags),
                        "fp": sum(flags),
                        "fpr": sum(flags) / len(flags),
                    }
                    for scen, flags in by_scenario.items()
                },
            }
            model_results.append(seed_stat)

        # Aggregate across seeds
        if model_results:
            n_seeds = len(model_results)
            mean_fpr = float(np.mean([s["overall_fpr"] for s in model_results]))
            std_fpr = float(np.std([s["overall_fpr"] for s in model_results]))
            scenarios = list(model_results[0]["by_scenario"].keys())
            scen_aggs = {}
            for scen in scenarios:
                fps = [s["by_scenario"][scen]["fp"] for s in model_results]
                counts = [s["by_scenario"][scen]["count"] for s in model_results]
                fprs = [s["by_scenario"][scen]["fpr"] for s in model_results]
                scen_aggs[scen] = {
                    "count": counts[0],
                    "mean_fp": float(np.mean(fps)),
                    "mean_fpr": float(np.mean(fprs)),
                    "std_fpr": float(np.std(fprs)),
                }
            results[model] = {
                "n_seeds": n_seeds,
                "mean_overall_fpr": mean_fpr,
                "std_overall_fpr": std_fpr,
                "scenarios": scen_aggs,
            }
    return results


if __name__ == "__main__":
    report = diagnose_gap()
    print(json.dumps(report, indent=2))
