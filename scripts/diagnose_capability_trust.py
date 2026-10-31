"""Diagnose capability trust degradation, absorbing state, and spurious causal alarms."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sentinel_research.novelty_experiment import NoveltyLiveExperiment, ExperimentConfig, VARIANTS
from sentinel_research.workload import normal_workload
from sentinel_research.novelty_scenarios import build_novelty_scenarios
from sentinel_research.metrics import calculate_metrics


def run_diagnosis(seed: int = 42, training_events: int = 200, validation_events: int = 80):
    results = {}
    config = ExperimentConfig(seed=seed, training_events=training_events, in_process=True)
    scenarios = build_novelty_scenarios(seed, events=12)
    test_scenarios_to_check = [
        "coordinated_servers",
        "delayed_causal_misuse",
        "provenance_replay",
        "capability_laundering",
        "schema_stable_response",
        "legitimate_upgrade",
    ]

    target_variants = ["baseline", "full", "without_capability_trust"]

    for variant in target_variants:
        live = NoveltyLiveExperiment(config, variant, in_process=True)
        with live:
            # 1. Train Phase
            train = normal_workload(training_events, seed, "novelty-train")
            train_obs, train_details = live.run_phase(train, True, 1000, trusted_enrollment=True)
            
            # Record trust trajectory during train
            trust_after_train = {}
            for srv_id, gw in live.gateways.items():
                if gw.novelty:
                    for (s_id, tool), state in gw.novelty.capabilities.states.items():
                        trust_after_train[f"{s_id}:{tool}"] = state.trust

            checkpoint = live.checkpoint()

            # Count spurious causal in train
            spurious_causal_train = sum(
                1 for d in train_details if (((d.get("components") or {}).get("causal")) or 0.0) >= 0.50
            )
            interventions_train = sum(
                1 for o in train_obs if o.intervened
            )

            # 2. Validation Phase
            val = normal_workload(validation_events, seed + 1, "novelty-validation")
            val_obs, val_details = live.run_phase(val, False, 10000)
            val_metrics = calculate_metrics(val_obs)

            trust_after_val = {}
            for srv_id, gw in live.gateways.items():
                if gw.novelty:
                    for (s_id, tool), state in gw.novelty.capabilities.states.items():
                        trust_after_val[f"{s_id}:{tool}"] = state.trust

            # 3. Test Scenarios
            test_results = {}
            for sc_name in test_scenarios_to_check:
                if sc_name not in scenarios:
                    continue
                live.restore(checkpoint)
                sc = scenarios[sc_name]
                test_obs, _ = live.run_phase(sc.scenario.cases, False, 20000)
                m = calculate_metrics(test_obs, sc.scenario.attack_start)
                test_results[sc_name] = {
                    "fpr": m["false_positive_rate"],
                    "recall": m["recall"],
                    "f1": m["f1"],
                }

            results[variant] = {
                "train_spurious_causal": spurious_causal_train,
                "train_interventions": interventions_train,
                "trust_after_train": trust_after_train,
                "val_fpr": val_metrics["false_positive_rate"],
                "trust_after_val": trust_after_val,
                "test_scenarios": test_results,
            }

    return results


def main():
    print("Running capability trust diagnosis across variants (seed=42, train=200, val=80)...")
    res = run_diagnosis(42, training_events=200, validation_events=80)
    print("\n" + "=" * 80)
    print("CAPABILITY TRUST DIAGNOSIS SUMMARY (seed=42, train=200, val=80)")
    print("=" * 80)
    for var, data in res.items():
        print(f"\nVariant: {var}")
        print(f"  Train spurious causal risk >= 0.50: {data['train_spurious_causal']}/200 events ({data['train_spurious_causal']/2:.1f}%)")
        print(f"  Train interventions (CONFIRM/SANDBOX/ISOLATE): {data['train_interventions']}/200")
        print(f"  Trust after train: {data['trust_after_train']}")
        print(f"  Validation FPR: {data['val_fpr']:.4f}")
        print(f"  Trust after val: {data['trust_after_val']}")
        print("  Test Scenarios FPR:")
        for sc, sc_m in data["test_scenarios"].items():
            print(f"    - {sc:28s}: FPR={sc_m['fpr']:.4f}, Recall={sc_m['recall']:.4f}, F1={sc_m['f1']:.4f}")

    # Publication scale numbers
    pub_root = Path("results/novelty/publication_scale_complete")
    if pub_root.exists():
        print("\n" + "=" * 80)
        print("PUBLICATION MATRIX (results/novelty/publication_scale_complete, 5 seeds)")
        print("=" * 80)
        scenarios = ["coordinated_servers", "delayed_causal_misuse", "provenance_replay",
                     "capability_laundering", "schema_stable_response", "legitimate_upgrade"]
        seeds = [42, 123, 456, 789, 1001]
        for sc in scenarios:
            print(f"\nScenario: {sc}")
            for var in ["baseline", "full", "without_capability_trust"]:
                fprs, recalls = [], []
                for s in seeds:
                    f = pub_root / var / sc / f"seed-{s}-test.json"
                    if f.exists():
                        d = json.loads(f.read_text("utf-8"))
                        fprs.append(d["metrics"]["false_positive_rate"])
                        recalls.append(d["metrics"]["recall"])
                if fprs:
                    print(f"  {var:26s}: mean FPR = {sum(fprs)/len(fprs):.4f}, mean Recall = {sum(recalls)/len(recalls):.4f}")


if __name__ == "__main__":
    main()

