"""Live-gateway novelty comparisons with isolated frozen and adaptive phases."""

from __future__ import annotations

import copy
import gc
import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
import traceback
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .experiment import ExperimentConfig, LiveExperiment
from .metrics import calculate_metrics
from .novelty import NoveltyConfig, NoveltySentinelEngine
from .novelty_scenarios import build_novelty_scenarios
from .statistics import exact_paired_sign_flip
from .workload import normal_workload


@dataclass(frozen=True)
class ValidationCalibration:
    threshold: float
    target_fpr: float
    validation_scores: tuple[float, ...]

    @classmethod
    def fit(cls, validation, target_fpr):
        if type(target_fpr) not in (int, float) or not 0 < target_fpr < 1:
            raise ValueError("validation FPR must be between zero and one")
        if not validation or any(row.malicious is not False for row in validation):
            raise ValueError("calibration requires nonempty benign validation observations")
        scores = tuple(row.risk for row in validation)
        if any(
            type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1
            for value in scores
        ):
            raise ValueError("validation risk scores must be finite and between zero and one")
        # Reuse the existing offline comparison rule; no runtime policy fitting.
        from .compare import calibrate_threshold

        threshold = calibrate_threshold(np.asarray(scores), target_fpr)
        return cls(threshold, target_fpr, scores)

    def artifact(self):
        encoded = json.dumps(
            self.validation_scores, separators=(",", ":"), allow_nan=False
        ).encode()
        return {
            **asdict(self),
            "rule": "benign validation quantile, method=higher; score > threshold",
            "validation_count": len(self.validation_scores),
            "validation_scores_sha256": hashlib.sha256(encoded).hexdigest(),
            "observed_validation_fpr": sum(s > self.threshold for s in self.validation_scores)
            / len(self.validation_scores),
            "test_used_for_threshold": False,
            "changes_gateway_policy": False,
        }

    def metrics(self, observations, attack_start=None):
        return calculate_metrics(
            [replace(row, intervened=row.risk > self.threshold) for row in observations],
            attack_start,
        )


VARIANTS = {
    "baseline": None,
    "full": NoveltyConfig(require_promotion_approval=False),
    "without_intent_provenance": NoveltyConfig(
        intent_provenance=False, require_promotion_approval=False
    ),
    "without_capability_trust": NoveltyConfig(
        capability_trust=False, require_promotion_approval=False
    ),
    "without_dual_memory": NoveltyConfig(dual_memory=False, require_promotion_approval=False),
    "approval_required": NoveltyConfig(),
}


@dataclass(frozen=True)
class NoveltyStudyConfig:
    seeds: tuple[int, ...] = (42,)
    variants: tuple[str, ...] = tuple(VARIANTS)
    scenarios: tuple[str, ...] = tuple(build_novelty_scenarios())
    training_events: int = 100
    validation_events: int = 40
    test_events: int = 12
    output: str = "results/novelty/development"
    validation_fpr: float | None = None
    in_process: bool = True
    resumable: bool = False

    def validate(self):
        if not self.seeds or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("provide unique seeds")
        if (
            not self.variants
            or len(set(self.variants)) != len(self.variants)
            or set(self.variants) - VARIANTS.keys()
        ):
            raise ValueError("provide unique supported variants")
        known = build_novelty_scenarios(events=self.test_events)
        if (
            not self.scenarios
            or len(set(self.scenarios)) != len(self.scenarios)
            or set(self.scenarios) - known.keys()
        ):
            raise ValueError("provide unique supported scenarios")
        if self.training_events < 1 or self.validation_events < 1:
            raise ValueError("training and validation sizes must be positive")
        if self.validation_fpr is not None and (
            type(self.validation_fpr) not in (int, float) or not 0 < self.validation_fpr < 1
        ):
            raise ValueError("validation FPR must be between zero and one")


class NoveltyLiveExperiment(LiveExperiment):
    def __init__(self, config: ExperimentConfig, variant: str, in_process: bool | None = None):
        super().__init__(config, in_process=in_process)
        self.variant = variant
        self.identity = None
        self.execution_context = None

    def _rpc(
        self,
        server_id,
        method,
        params,
        request_id,
        intent,
        session="experiment",
        provenance_id=None,
    ):
        if self.execution_context is not None:
            self.execution_context["last_request"] = {
                "server_id": server_id,
                "method": method,
                "request_id": request_id,
            }
        return super()._rpc(server_id, method, params, request_id, intent, session, provenance_id)

    def __enter__(self):
        super().__enter__()
        for gateway in self.gateways.values():
            if VARIANTS[self.variant] is not None:
                gateway.novelty = NoveltySentinelEngine(self.engine, config=VARIANTS[self.variant])
                gateway.config.novelty = True
            # The sequential trusted fixture supplies identity, never a caller header.
            gateway.session_identity = lambda headers: self.identity
        return self

    def checkpoint(self):
        # Copy the complete object graph together to preserve shared base-engine
        # identity across two gateways and their novelty wrappers.
        return copy.deepcopy(
            (
                self.engine,
                {key: gateway.novelty for key, gateway in self.gateways.items()},
                {
                    key: (gateway.tool_metadata, gateway.capability_digest)
                    for key, gateway in self.gateways.items()
                },
                {key: asdict(state) for key, state in self.states.items()},
            )
        )

    def restore(self, checkpoint):
        self.engine, novelty, metadata, states = copy.deepcopy(checkpoint)
        for key, gateway in self.gateways.items():
            gateway.engine = self.engine
            gateway.novelty = novelty[key]
            gateway.tool_metadata, gateway.capability_digest = metadata[key]
            gateway.audit.clear()
            for name, value in states[key].items():
                setattr(self.states[key], name, value)
        self.provenance_claims.clear()
        self.identity = None

    def learning_state(self):
        digest = hashlib.sha256()
        updates = 0
        for key, profile in sorted(self.engine.profiles.items()):
            updates += profile.trusted_count
            digest.update(key.encode())
            digest.update(
                str(
                    (
                        profile.scaler.count,
                        profile.trusted_count,
                        profile.error_mean,
                        profile.error_m2,
                    )
                ).encode()
            )
            for array in (
                profile.scaler.mean,
                profile.scaler.m2,
                profile.autoencoder.w1,
                profile.autoencoder.w2,
                profile.autoencoder.b1,
                profile.autoencoder.b2,
            ):
                digest.update(array.tobytes())
        memory = {
            key: {
                "trusted": repr(gateway.novelty.memory.trusted),
                "candidates": repr(gateway.novelty.memory.candidates),
            }
            for key, gateway in self.gateways.items()
            if gateway.novelty
        }
        digest.update(json.dumps(memory, sort_keys=True).encode())
        digest.update(repr(self.engine.sequence.transitions).encode())
        digest.update(repr(self.engine.sequence.previous).encode())
        digest.update(repr(self.engine.attestation.enrolled).encode())
        return {"model_updates": updates, "learning_state_sha256": digest.hexdigest()}

    def execute(self, case, request_id, learn, trusted_enrollment=False):
        self.identity = (
            case.interaction.session_id
            if trusted_enrollment
            else getattr(case, "independent_identity", None)
        )
        state = self.states[case.interaction.server_id]
        state.response_overrides.clear()
        override = getattr(case, "response_override", None)
        if override is not None:
            state.response_overrides[case.interaction.tool_name] = copy.deepcopy(override)
        before = sum(profile.trusted_count for profile in self.engine.profiles.values())
        try:
            observation, detail = super().execute(case, request_id, learn, trusted_enrollment)
            audit = self.gateways[case.interaction.server_id].audit[-1]
            after = sum(profile.trusted_count for profile in self.engine.profiles.values())
            detail.update(
                novelty=audit.novelty,
                attestation_verified=audit.attestation_verified,
                model_updates=after - before,
                independent_identity=self.identity,
            )
            return observation, detail
        finally:
            state.response_overrides.clear()
            self.identity = None


def _revision():
    root = Path(__file__).resolve().parent.parent
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
        dirty = bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
        )
        return {"commit": revision, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def _workload_digest(cases):
    hasher = hashlib.sha256(b"[")
    for index, case in enumerate(cases):
        if index > 0:
            hasher.update(b", ")
        hasher.update(json.dumps(asdict(case), sort_keys=True, allow_nan=False).encode())
    hasher.update(b"]")
    return hasher.hexdigest()


def summarize(results):
    rows = []
    for variant, scenario, phase in sorted(
        {(r["variant"], r["scenario"], r["phase"]) for r in results}
    ):
        group = [
            r
            for r in results
            if (r["variant"], r["scenario"], r["phase"]) == (variant, scenario, phase)
        ]
        rows.append(
            {
                "variant": variant,
                "scenario": scenario,
                "phase": phase,
                "seeds": len(group),
                **{
                    name: statistics.mean(r["metrics"][name] for r in group)
                    for name in ("f1", "recall", "false_positive_rate")
                },
                "model_updates": statistics.mean(
                    r["learning_after"]["model_updates"] - r["learning_before"]["model_updates"]
                    for r in group
                ),
            }
        )
    comparisons = []
    for row in rows:
        if row["variant"] == "full":
            continue
        full = {
            r["seed"]: r
            for r in results
            if r["variant"] == "full"
            and (r["scenario"], r["phase"]) == (row["scenario"], row["phase"])
        }
        other = {
            r["seed"]: r
            for r in results
            if r["variant"] == row["variant"]
            and (r["scenario"], r["phase"]) == (row["scenario"], row["phase"])
        }
        seeds = sorted(full.keys() & other.keys())
        if seeds:
            comparisons.append(
                {
                    "variant": row["variant"],
                    "scenario": row["scenario"],
                    "phase": row["phase"],
                    "paired_seeds": seeds,
                    "metric": "f1",
                    "test": exact_paired_sign_flip(
                        [full[s]["metrics"]["f1"] for s in seeds],
                        [other[s]["metrics"]["f1"] for s in seeds],
                    ),
                }
            )
    return {
        "aggregate": rows,
        "exploratory_paired_comparisons": comparisons,
        "inference_note": "Development diagnostics, not preregistered confirmatory evidence; seed is the paired unit.",
    }


def _execution_record(root, execution):
    record = {key: value for key, value in execution.items() if key != "_output_created"}
    record["recorded_at_utc"] = datetime.now(UTC).isoformat()
    (root / "execution.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


def run_novelty_study(config: NoveltyStudyConfig):
    """Retain failure context without retries, parameter changes or partial summaries."""
    execution = {"_output_created": False, "status": "running", "completed_phase_records": 0}
    try:
        result = _run_novelty_study(config, execution)
    except Exception as exc:
        if execution["_output_created"]:
            execution.update(
                status="failed",
                error_type=type(exc).__name__,
                error=str(exc),
                traceback=[
                    {"file": frame.filename, "line": frame.lineno, "function": frame.name}
                    for frame in traceback.extract_tb(exc.__traceback__)
                ],
            )
            _execution_record(Path(config.output), execution)
        raise
    execution.update(status="completed", phase="complete")
    _execution_record(Path(config.output), execution)
    return result


def _run_novelty_study(config: NoveltyStudyConfig, execution):
    config.validate()
    software = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "platform": platform.platform(),
        **_revision(),
    }
    source_root = Path(__file__).resolve().parent
    software["source_sha256"] = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(source_root.glob("*.py"))
    }
    root = Path(config.output)
    root.mkdir(parents=True, exist_ok=config.resumable)
    execution["_output_created"] = True
    protocol = {
        "configuration": asdict(config),
        "software": software,
        "policy": "fixed gateway action bands and runtime trust; optional validation-only secondary score threshold",
        "validation_used_for_tuning": config.validation_fpr is not None,
        "test_learning": False,
        "calibration_scope": "secondary score report only; gateway decisions unchanged",
        "adaptive_from": "independent post-TRAIN checkpoint",
        "identity_model": "trusted sequential fixture; rotating raw sessions do not create independent actors",
        "reviewed_recovery": "operator incident-response API; intentionally not exercised during autonomous unattended benchmarks",
    }
    (root / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    results = []
    for seed in config.seeds:
        catalog = build_novelty_scenarios(seed, config.test_events)
        for variant in config.variants:
            needed_phases = []
            for name in config.scenarios:
                selected = catalog[name]
                for phase in ("test", "adaptive") if selected.adaptive else ("test",):
                    phase_file = root / variant / name / f"seed-{seed}-{phase}.json"
                    if config.resumable and phase_file.exists():
                        try:
                            cached_row = json.loads(phase_file.read_text(encoding="utf-8"))
                            cached_row.pop("decisions", None)
                            results.append(cached_row)
                            execution["completed_phase_records"] += 1
                            continue
                        except Exception:
                            pass
                    needed_phases.append((name, phase))
            if not needed_phases:
                _execution_record(root, execution)
                continue
            live_config = ExperimentConfig(
                seed=seed, training_events=config.training_events, in_process=config.in_process
            )
            execution.update(
                seed=seed, variant=variant, scenario=None, phase="initialize", last_request=None
            )
            _execution_record(root, execution)
            live = NoveltyLiveExperiment(live_config, variant, in_process=config.in_process)
            live.execution_context = execution
            with live:
                execution.update(phase="train", last_request=None)
                _execution_record(root, execution)
                print(
                    f"Novelty study: seed={seed} variant={variant} TRAIN",
                    file=sys.stderr,
                    flush=True,
                )
                train = normal_workload(config.training_events, seed, "novelty-train")
                train_digest = _workload_digest(train)
                live.run_phase(train, True, 1_000, trusted_enrollment=True)
                checkpoint = live.checkpoint()
                before = live.learning_state()
                validation = normal_workload(
                    config.validation_events, seed + 1, "novelty-validation"
                )
                validation_digest = _workload_digest(validation)
                execution.update(phase="validation", last_request=None)
                _execution_record(root, execution)
                validation_observations, _ = live.run_phase(validation, False, 10_000)
                if before != live.learning_state():
                    raise RuntimeError("validation changed learning state")
                validation_metrics = calculate_metrics(validation_observations)
                calibration = None
                calibration_reference = None
                if config.validation_fpr is not None:
                    calibration = ValidationCalibration.fit(
                        validation_observations, config.validation_fpr
                    )
                    calibration_reference = f"calibration/{variant}/seed-{seed}-calibration.json"
                    calibration_path = root / calibration_reference
                    calibration_path.parent.mkdir(parents=True, exist_ok=True)
                    calibration_path.write_text(
                        json.dumps(
                            {
                                **calibration.artifact(),
                                "seed": seed,
                                "variant": variant,
                                "validation_workload_sha256": validation_digest,
                            },
                            indent=2,
                            allow_nan=False,
                        ),
                        encoding="utf-8",
                    )
                for name, phase in needed_phases:
                    selected = catalog[name]
                    execution.update(scenario=name, phase=phase, last_request=None)
                    _execution_record(root, execution)
                    print(
                        f"Novelty study: seed={seed} variant={variant} scenario={name} phase={phase}",
                        file=sys.stderr,
                        flush=True,
                    )
                    live.restore(checkpoint)
                    learning_before = live.learning_state()
                    observations, details = live.run_phase(
                        selected.scenario.cases, phase == "adaptive", 20_000
                    )
                    learning_after = live.learning_state()
                    if phase == "test" and learning_before != learning_after:
                        raise RuntimeError("held-out TEST changed learning state")
                    row = {
                        "seed": seed,
                        "variant": variant,
                        "scenario": name,
                        "phase": phase,
                        "novelty_components": asdict(VARIANTS[variant])
                        if VARIANTS[variant]
                        else None,
                        "description": selected.scenario.description,
                        "dataset_sizes": {
                            "train": len(train),
                            "validation": len(validation),
                            phase: len(selected.scenario.cases),
                        },
                        "workload_sha256": {
                            "train": train_digest,
                            "validation": validation_digest,
                            phase: _workload_digest(selected.scenario.cases),
                        },
                        "learning_before": learning_before,
                        "learning_after": learning_after,
                        "validation_metrics": validation_metrics,
                        "metrics": calculate_metrics(observations, selected.scenario.attack_start),
                        "decisions": details,
                    }
                    if calibration is not None:
                        row["calibration_reference"] = calibration_reference
                        row["score_metrics"] = calibration.metrics(
                            observations, selected.scenario.attack_start
                        )
                        row["score_threshold"] = calibration.threshold
                    folder = root / variant / name
                    folder.mkdir(parents=True, exist_ok=True)
                    (folder / f"seed-{seed}-{phase}.json").write_text(
                        json.dumps(row, indent=2), encoding="utf-8"
                    )
                    row.pop("decisions", None)
                    results.append(row)
                    execution["completed_phase_records"] += 1
                    _execution_record(root, execution)
            gc.collect()
    execution.update(phase="summarize", last_request=None)
    _execution_record(root, execution)
    summary = summarize(results)
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "# Novelty development study",
        "",
        summary["inference_note"],
        "",
        "Gateway decisions use fixed bands. TEST and ADAPTIVE each restart from TRAIN.",
        "",
        "| Variant | Scenario | Phase | Seeds | Recall | FPR | F1 | Model updates |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary["aggregate"]:
        lines.append(
            f"| {row['variant']} | {row['scenario']} | {row['phase']} | {row['seeds']} | "
            f"{row['recall']:.4f} | {row['false_positive_rate']:.4f} | {row['f1']:.4f} | {row['model_updates']:.1f} |"
        )
    if config.validation_fpr is not None:
        lines.extend(
            [
                "",
                "## Validation-calibrated score results",
                "",
                "Secondary score predictions only; the table above uses actual gateway interventions.",
                "Thresholds were saved before scenario execution; TEST and ADAPTIVE share their variant/seed threshold.",
                "",
                "| Variant | Scenario | Phase | Seed | Threshold | TP | TN | FP | FN |",
                "|---|---|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in results:
            metrics = row["score_metrics"]
            lines.append(
                f"| {row['variant']} | {row['scenario']} | {row['phase']} | {row['seed']} | "
                f"{row['score_threshold']:.6f} | {metrics['tp']} | {metrics['tn']} | {metrics['fp']} | {metrics['fn']} |"
            )
    (root / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
