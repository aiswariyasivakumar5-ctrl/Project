from __future__ import annotations

import copy
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .compare import calibrate_threshold
from .comparison_data import ComparisonDataset, DatasetRow, build_comparison_dataset
from .engine import EngineConfig, SentinelEngine
from .ml_features import simulated_response
from .plots import bar_chart, line_chart
from .scenarios import build_scenarios

COMPONENTS = ("behavior", "intent", "sequence", "causal", "impact", "failure", "attestation")
WEIGHTS = {
    "behavior": 0.34,
    "intent": 0.20,
    "sequence": 0.10,
    "causal": 0.16,
    "impact": 0.08,
    "failure": 0.05,
    "attestation": 0.07,
}
QUANTILES = (0.50, 0.95, 0.99, 0.995, 0.999, 1.0)


@dataclass(frozen=True)
class TradeoffConfig:
    seeds: tuple[int, ...] = (42, 123, 456, 789, 1001)
    train_size: int = 5000
    validation_size: int = 1000
    test_size: int = 3000
    validation_fpr: float = 0.01
    output: str = "results/tradeoff_diagnostics"


def _quantiles(values: list[float] | np.ndarray) -> dict[str, float]:
    data = np.asarray(values, dtype=float)
    return {f"p{q * 100:g}": float(np.quantile(data, q)) for q in QUANTILES}


def _contributions(components: dict[str, float]) -> dict[str, float]:
    return {name: float(WEIGHTS[name] * components[name]) for name in COMPONENTS}


def _record(
    index: int, phase: str, row: DatasetRow, verdict: Any, threshold: float | None = None
) -> dict[str, Any]:
    contributions = _contributions(verdict.components)
    linear = float(sum(contributions.values()))
    floor_active = verdict.components["causal"] >= 0.60 and linear < 0.50
    return {
        "index": index,
        "phase": phase,
        "scenario": row.scenario,
        "malicious": row.malicious,
        "server_id": row.interaction.server_id,
        "session_id": row.interaction.session_id,
        "tool_name": row.interaction.tool_name,
        "components": {k: float(v) for k, v in verdict.components.items()},
        "contributions": contributions,
        "linear_risk": linear,
        "causal_floor_active": floor_active,
        "uncertainty": float(verdict.uncertainty),
        "final_risk": float(verdict.anomaly_score),
        "trust": float(verdict.trust_score),
        "threshold": threshold,
        "decision": verdict.action.value,
        "intervened": None if threshold is None else bool(verdict.anomaly_score > threshold),
        "baseline_updated": bool(verdict.baseline_updated),
    }


def _replay(
    dataset: ComparisonDataset, config: EngineConfig, validation_fpr: float
) -> dict[str, Any]:
    engine = SentinelEngine(20, config)
    for row in dataset.train:
        engine.evaluate(copy.deepcopy(row.interaction), learn=True, trusted_enrollment=True)
    trained = copy.deepcopy(engine)
    validation_records = []
    for index, row in enumerate(dataset.validation):
        verdict = engine.evaluate(copy.deepcopy(row.interaction), learn=False)
        validation_records.append(_record(index, "validation", row, verdict))
    validation_risks = np.asarray([item["final_risk"] for item in validation_records])
    threshold = calibrate_threshold(validation_risks, validation_fpr)
    engine = trained
    test_records = []
    for index, row in enumerate(dataset.test):
        verdict = engine.evaluate(copy.deepcopy(row.interaction), learn=False)
        test_records.append(_record(index, "test", row, verdict, threshold))
    for item in validation_records:
        item["threshold"] = threshold
        item["intervened"] = item["final_risk"] > threshold
    return {"threshold": threshold, "validation": validation_records, "test": test_records}


def _outcome(item: dict[str, Any]) -> str:
    return (
        ("tp" if item["intervened"] else "fn")
        if item["malicious"]
        else ("fp" if item["intervened"] else "tn")
    )


def _component_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    scenarios = sorted({item["scenario"] for item in records})
    for scenario in scenarios:
        result[scenario] = {}
        for outcome in ("tp", "fp", "fn", "tn"):
            selected = [
                item
                for item in records
                if item["scenario"] == scenario and _outcome(item) == outcome
            ]
            if selected:
                result[scenario][outcome] = {
                    "count": len(selected),
                    "mean_final_risk": float(np.mean([x["final_risk"] for x in selected])),
                    "mean_components": {
                        name: float(np.mean([x["components"][name] for x in selected]))
                        for name in COMPONENTS
                    },
                    "mean_contributions": {
                        name: float(np.mean([x["contributions"][name] for x in selected]))
                        for name in COMPONENTS
                    },
                    "causal_floor_rate": float(
                        np.mean([x["causal_floor_active"] for x in selected])
                    ),
                }
    return result


def _metrics(records: list[dict[str, Any]], field: str = "intervened") -> dict[str, float | int]:
    tp = sum(x["malicious"] and x[field] for x in records)
    fn = sum(x["malicious"] and not x[field] for x in records)
    fp = sum(not x["malicious"] and x[field] for x in records)
    tn = sum(not x["malicious"] and not x[field] for x in records)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0,
    }


def _percentile_map(reference: np.ndarray, values: np.ndarray) -> np.ndarray:
    ordered = np.sort(reference)
    return np.searchsorted(ordered, values, side="right") / len(ordered)


def _alternatives(
    validation: list[dict[str, Any]], test: list[dict[str, Any]], fpr: float
) -> dict[str, Any]:
    refs = {name: np.asarray([x["components"][name] for x in validation]) for name in COMPONENTS}

    def scores(records: list[dict[str, Any]]) -> dict[str, np.ndarray]:
        percentiles = {
            name: _percentile_map(refs[name], np.asarray([x["components"][name] for x in records]))
            for name in COMPONENTS
        }
        normalized = sum(WEIGHTS[name] * percentiles[name] for name in COMPONENTS) / sum(
            WEIGHTS.values()
        )
        maximum = np.maximum.reduce([percentiles[name] for name in COMPONENTS])
        linear = np.asarray([x["linear_risk"] for x in records])
        return {
            "component_normalized_weighted": normalized,
            "per_component_max_percentile": maximum,
            "simple_linear_decomposition": linear,
        }

    val, tst = scores(validation), scores(test)
    result = {}
    for name in val:
        threshold = calibrate_threshold(val[name], fpr)
        decisions = tst[name] > threshold
        diagnostic = [
            dict(item, diagnostic=bool(decision))
            for item, decision in zip(test, decisions, strict=False)
        ]
        result[name] = {
            "validation_only_threshold": threshold,
            "test_used_for_threshold": False,
            "metrics": _metrics(diagnostic, "diagnostic"),
            "validation_distribution": _quantiles(val[name]),
            "test_distribution": _quantiles(tst[name]),
        }
    return result


def _distributions(replay: dict[str, Any]) -> dict[str, Any]:
    validation = replay["validation"]
    test = replay["test"]
    normal = [x for x in test if not x["malicious"]]
    attack = [x for x in test if x["malicious"]]
    groups = {"validation_normal": validation, "test_normal": normal, "test_attack": attack}
    return {
        name: {
            "final_risk": _quantiles([x["final_risk"] for x in rows]),
            "components": {c: _quantiles([x["components"][c] for x in rows]) for c in COMPONENTS},
            "causal_floor_rate": float(np.mean([x["causal_floor_active"] for x in rows])),
        }
        for name, rows in groups.items()
    }


def _scenario_comparison(
    full: list[dict[str, Any]], no_causal: list[dict[str, Any]]
) -> dict[str, Any]:
    result = {}
    for scenario in sorted({x["scenario"] for x in full}):
        a = [x for x in full if x["scenario"] == scenario]
        b = [x for x in no_causal if x["scenario"] == scenario]
        result[scenario] = {
            "full": _metrics(a),
            "without_causal": _metrics(b),
            "full_risk": _quantiles([x["final_risk"] for x in a]),
            "without_causal_risk": _quantiles([x["final_risk"] for x in b]),
            "changed_decisions": sum(
                x["intervened"] != y["intervened"] for x, y in zip(a, b, strict=False)
            ),
        }
    return result


def _adaptive_trajectory(
    seed: int, scenario: str, train_size: int, validation_size: int
) -> list[dict[str, Any]]:
    dataset = build_comparison_dataset(seed, train_size, validation_size, 120)
    engine = SentinelEngine(20, EngineConfig())
    for row in dataset.train:
        engine.evaluate(copy.deepcopy(row.interaction), learn=True, trusted_enrollment=True)
    trained = copy.deepcopy(engine)
    validation = np.asarray(
        [
            engine.evaluate(copy.deepcopy(row.interaction), learn=False).anomaly_score
            for row in dataset.validation
        ]
    )
    threshold = calibrate_threshold(validation, 0.01)
    engine = trained
    result = []
    for index, case in enumerate(build_scenarios(seed, 200)[scenario].cases):
        event = copy.deepcopy(case.interaction)
        event.response = simulated_response(event)
        event.capability_digest = "cap-v2" if case.control == "capability_drift" else "cap-v1"
        verdict = engine.evaluate(event, learn=True)
        rec = _record(
            index, "adaptive", DatasetRow(event, case.malicious, scenario), verdict, threshold
        )
        rec["quarantined_total"] = sum(p.quarantined_count for p in engine.profiles.values())
        rec["capability_digest"] = event.capability_digest
        rec["enrolled_digest"] = engine.attestation.enrolled.get(event.server_id)
        result.append(rec)
    return result


def sequence_locality_probe() -> dict[str, Any]:
    from .detectors import SequenceModel

    model = SequenceModel()
    for _ in range(20):
        model.update("learned-session", "safe_read")
        model.update("learned-session", "calculate")
    return {
        "learned_session_score": model.anomaly("learned-session", "export_data"),
        "new_session_score": model.anomaly("new-session", "export_data"),
        "transition_namespaces": sorted(model.transitions),
        "interpretation": "A new session has no previous-tool state and therefore returns zero sequence anomaly.",
    }


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    rows = []
    for item in records:
        row = {k: v for k, v in item.items() if k not in {"components", "contributions"}}
        row.update({f"component_{k}": v for k, v in item["components"].items()})
        row.update({f"contribution_{k}": v for k, v in item["contributions"].items()})
        rows.append(row)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _figures(root: Path, summary: dict[str, Any], trajectories: dict[str, Any]) -> list[str]:
    target = root / "figures"
    target.mkdir(parents=True, exist_ok=True)
    files = {}
    seeds = summary["seeds"]
    files["thresholds.svg"] = line_chart(
        "Validation thresholds by seed",
        {
            name: [(i, seed[name]["threshold"]) for i, seed in enumerate(seeds)]
            for name in ("full", "without_causal")
        },
        "Seed index",
        "Risk",
        max(1, len(seeds) - 1),
        1,
    )
    files["causal_vs_noncausal_recall.svg"] = bar_chart(
        "Full vs without-causal recall",
        {
            name: float(np.mean([s[name]["metrics"]["recall"] for s in seeds]))
            for name in ("full", "without_causal")
        },
        "Recall",
        1,
    )
    first = seeds[0]["full"]["component_summary"]
    fn = [v["fn"] for v in first.values() if "fn" in v]
    if fn:
        files["false_negative_components.svg"] = bar_chart(
            "Mean components among false negatives (seed 42)",
            {c: float(np.mean([x["mean_components"][c] for x in fn])) for c in COMPONENTS},
            "Component",
            1,
        )
    for scenario, curve in trajectories.items():
        files[f"{scenario}_trajectory.svg"] = line_chart(
            f"{scenario.replace('_', ' ').title()} trajectory",
            {
                "final risk": [(x["index"], x["final_risk"]) for x in curve],
                "trust": [(x["index"], x["trust"]) for x in curve],
                "causal": [(x["index"], x["components"]["causal"]) for x in curve],
            },
            "Event",
            "Score",
            max(x["index"] for x in curve),
            1,
        )
    paths = []
    for name, content in files.items():
        path = target / name
        path.write_text(content, encoding="utf-8")
        paths.append(str(path))
    return paths


def run_tradeoff_analysis(config: TradeoffConfig) -> dict[str, Any]:
    root = Path(config.output)
    data_dir = root / "data"
    tables = root / "tables"
    data_dir.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    seed_summaries = []
    for seed in config.seeds:
        dataset = build_comparison_dataset(
            seed, config.train_size, config.validation_size, config.test_size
        )
        variants = {}
        for name, engine_config in (
            ("full", EngineConfig()),
            ("without_causal", EngineConfig(causal=False)),
        ):
            replay = _replay(dataset, engine_config, config.validation_fpr)
            _write_csv(
                data_dir / f"seed-{seed}-{name}-events.csv", replay["validation"] + replay["test"]
            )
            variants[name] = {
                "threshold": replay["threshold"],
                "metrics": _metrics(replay["test"]),
                "distributions": _distributions(replay),
                "component_summary": _component_summary(replay["test"]),
                "offline_alternatives": _alternatives(
                    replay["validation"], replay["test"], config.validation_fpr
                ),
            }
            variants[name]["_test"] = replay["test"]
        variants["scenario_comparison"] = _scenario_comparison(
            variants["full"].pop("_test"), variants["without_causal"].pop("_test")
        )
        seed_summaries.append({"seed": seed, **variants})
    adaptive_sizes = (min(config.train_size, 1000), min(config.validation_size, 250))
    trajectories = {
        name: _adaptive_trajectory(config.seeds[0], name, *adaptive_sizes)
        for name in ("low_and_slow", "gradual_poisoning", "capability_drift")
    }
    for name, records in trajectories.items():
        _write_csv(data_dir / f"{name}-trajectory.csv", records)
    result = {
        "configuration": asdict(config),
        "guardrails": {
            "production_logic_changed": False,
            "approved_results_modified": False,
            "test_used_for_threshold": False,
            "alternatives_are_offline_diagnostics_only": True,
        },
        "seeds": seed_summaries,
        "sequence_locality": sequence_locality_probe(),
        "trajectories": trajectories,
    }
    result["figures"] = _figures(root, result, trajectories)
    (root / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    rows = []
    for seed in seed_summaries:
        for name in ("full", "without_causal"):
            rows.append(
                {
                    "seed": seed["seed"],
                    "variant": name,
                    "threshold": seed[name]["threshold"],
                    **seed[name]["metrics"],
                }
            )
    with (tables / "full-vs-causal.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return result
