"""Fixed development probes isolate learned-profile effects from runtime history."""

import argparse
import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from .adaptation_study import summarize_events
from .experiment import ExperimentConfig
from .learning_attribution import LearningAttribution
from .matched_poisoning import SEEDS, build_matched, learning_delays
from .novelty_experiment import NoveltyLiveExperiment, _workload_digest

POLICIES = {
    "frozen": "approval_required",
    "immediate": "without_dual_memory",
    "gated": "full",
    "blanket_review": "approval_required",
    "withheld": "approval_required",
}


def response(text):
    return {"content": [{"type": "text", "text": text}]}


def fixtures(seed):
    train, matched = build_matched(seed)
    clean = matched["clean"]
    streams = {"clean": clean}
    for name in ("abrupt", "gradual_after_promotion"):
        rows = []
        for index, case in enumerate(clean):
            malicious = name == "abrupt" or index >= 3
            size = 64 if name == "abrupt" else 4 + 2 * (index - 3)
            rows.append(
                replace(
                    case,
                    scenario=name,
                    malicious=malicious,
                    expected_intervention=malicious,
                    response_override=response("9" * size) if malicious else None,
                )
            )
        streams[name] = rows
    probes = []
    for index, (args, text) in enumerate(
        (
            ({"a": 1.0, "b": 2.0}, None),
            ({"a": 100.0, "b": 200.0}, None),
            *[({"a": 1.0, "b": 2.0}, "9" * size) for size in (4, 12, 32, 64)],
        )
    ):
        event = replace(clean[0].interaction, arguments=args, session_id=f"probe-{seed}-{index}")
        probes.append(
            replace(
                clean[0],
                interaction=event,
                scenario="fixed-probe",
                malicious=text is not None,
                expected_intervention=text is not None,
                independent_identity=f"probe-principal-{index}",
                response_override=response(text) if text is not None else None,
            )
        )
    return train, streams, probes


def model_digest(profiles):
    digest = hashlib.sha256()
    for key, profile in sorted(profiles.items()):
        digest.update(key.encode())
        digest.update(
            repr(
                (profile.trusted_count, profile.scaler.count, profile.error_mean, profile.error_m2)
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
    return digest.hexdigest()


def probe_profiles(live, enrollment, profiles, probes):
    rows = []
    for index, case in enumerate(probes):
        # Reset all runtime history for EACH probe, transferring only the fitted
        # numeric model state. Even profile trust/quarantine counters stay fixed.
        live.restore(enrollment)
        for key, source in profiles.items():
            target = live.engine.profiles[key]
            for field in ("scaler", "autoencoder", "trusted_count", "error_mean", "error_m2"):
                setattr(target, field, copy.deepcopy(getattr(source, field)))
        before = model_digest(live.engine.profiles)
        observation, detail = live.execute(case, 50000 + index, False)
        if before != model_digest(live.engine.profiles) or detail["model_updates"]:
            raise AssertionError("frozen probe changed fitted model state")
        rows.append(
            {
                "index": index,
                "malicious": case.malicious,
                "risk": observation.risk,
                "intervened": observation.intervened,
                "model_sha256": before,
            }
        )
    return rows


def probe_metrics(rows):
    benign = [r for r in rows if not r["malicious"]]
    attacks = [r for r in rows if r["malicious"]]
    return {
        "attack_recall": sum(r["intervened"] for r in attacks) / len(attacks),
        "benign_fpr": sum(r["intervened"] for r in benign) / len(benign),
        "mean_attack_risk": sum(r["risk"] for r in attacks) / len(attacks),
    }


def run_study(output, seeds=SEEDS):
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("unique nonempty seeds required")
    workloads = {seed: fixtures(seed) for seed in seeds}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        (output / name).write_text(
            json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )

    save(
        "protocol.json",
        {
            "purpose": "development model-degradation diagnostic; no tuning",
            "seeds": seeds,
            "policies": POLICIES,
            "training": "same balanced integer inventory, shuffled by seed",
            "streams": "12 clean calls; 12 wrong 64-digit answers; or 3 clean then 9 wrong answers growing from 4 to 20 digits",
            "probes": "2 benign and 4 wrong-response probes, lengths 4/12/32/64, fixed before execution",
            "probe_isolation": "reset enrollment runtime state for each probe; transfer only fitted model/scaler/error moments; learn=False",
            "reviews": "blanket approval at index 0, no oracle filtering",
            "inference": "descriptive; 3 training-order seeds, not independent real tasks; no significance claim",
            "source_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(Path(__file__).parent.glob("*.py"))
            },
            "workload_sha256": {
                str(seed): {
                    "train": _workload_digest(train),
                    "probes": _workload_digest(probes),
                    **{name: _workload_digest(cases) for name, cases in streams.items()},
                }
                for seed, (train, streams, probes) in workloads.items()
            },
        },
    )
    state = {"status": "running", "completed": 0, "planned": len(seeds) * len(POLICIES) * 3}
    save("execution.json", state)
    results = []
    try:
        for seed, (train, streams, probes) in workloads.items():
            for policy, variant in POLICIES.items():
                state.update(seed=seed, policy=policy, stream="enrollment")
                save("execution.json", state)
                with NoveltyLiveExperiment(
                    ExperimentConfig(training_events=len(train)), variant
                ) as live:
                    live.run_phase(train, True, 1000, True)
                    enrollment = live.checkpoint()
                    baseline_profiles = copy.deepcopy(live.engine.profiles)
                    before_probes = probe_profiles(live, enrollment, baseline_profiles, probes)
                    for name, cases in streams.items():
                        state["stream"] = name
                        save("execution.json", state)
                        live.restore(enrollment)
                        if policy == "blanket_review":
                            gateway = live.gateways["local-test-mcp"]
                            gateway.novelty.approve_promotion(
                                replace(
                                    cases[0].interaction,
                                    capability_digest=gateway.capability_digest,
                                ),
                                reviewer="fixture-blanket",
                                evidence_ref=f"{seed}-{name}",
                                ttl=3600,
                            )
                        rows = []
                        with (
                            (output / f"{seed}-{policy}-{name}.jsonl").open(
                                "x", encoding="utf-8"
                            ) as handle,
                            LearningAttribution(live.engine, cases) as attribution,
                        ):
                            for index, case in enumerate(cases):
                                attribution.step = index
                                offset = len(attribution.records)
                                observation, detail = live.execute(
                                    case, 10000 + index, policy != "frozen"
                                )
                                detail.update(
                                    index=index,
                                    fixture_malicious=case.malicious,
                                    fixture_response_override=case.response_override,
                                    intervened=observation.intervened,
                                    learned_events=attribution.records[offset:],
                                )
                                handle.write(json.dumps(detail, allow_nan=False) + "\n")
                                handle.flush()
                                rows.append(detail)
                        post_profiles = copy.deepcopy(live.engine.profiles)
                        after_probes = probe_profiles(live, enrollment, post_profiles, probes)
                        before_metrics, after_metrics = (
                            probe_metrics(before_probes),
                            probe_metrics(after_probes),
                        )
                        record = {
                            "seed": seed,
                            "policy": policy,
                            "stream": name,
                            **summarize_events(rows),
                            **learning_delays(rows),
                            "before_model_sha256": model_digest(baseline_profiles),
                            "after_model_sha256": model_digest(post_profiles),
                            "before_probes": before_probes,
                            "after_probes": after_probes,
                            "before_probe_metrics": before_metrics,
                            "after_probe_metrics": after_metrics,
                            "probe_deltas": {
                                key: after_metrics[key] - before_metrics[key]
                                for key in before_metrics
                            },
                        }
                        results.append(record)
                        save(f"{seed}-{policy}-{name}-probes.json", record)
                        state["completed"] += 1
                        save("execution.json", state)
        # Paired clean-adaptation control, not just comparison against no learning.
        for row in results:
            clean = next(
                r
                for r in results
                if (r["seed"], r["policy"], r["stream"]) == (row["seed"], row["policy"], "clean")
            )
            row["post_minus_clean_probe_metrics"] = {
                key: row["after_probe_metrics"][key] - clean["after_probe_metrics"][key]
                for key in row["after_probe_metrics"]
            }
        save("summary.json", results)
        state["status"] = "complete"
    except Exception as exc:
        state.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        save("execution.json", state)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({"completed": len(run_study(args.output))}))
