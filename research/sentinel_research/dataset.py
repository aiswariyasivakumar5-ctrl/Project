"""Export reproducible synthetic workloads, not observed runtime results."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from sentinel import models as runtime_models
from sentinel import provenance as runtime_provenance

from .novelty_scenarios import build_novelty_scenarios
from .scenarios import build_scenarios
from .workload import normal_workload

SEEDS = tuple(range(20001, 20021))


def export_dataset(
    output: Path, seeds=SEEDS, training=10000, validation=2000, scenario_events=3000
):
    seeds = tuple(seeds)
    if (
        not seeds
        or len(set(seeds)) != len(seeds)
        or any(type(seed) is not int or seed < 0 for seed in seeds)
        or any(type(n) is not int or n < 3 for n in (training, validation, scenario_events))
    ):
        raise ValueError("unique nonnegative integer seeds and sizes >= 3 required")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "kind": "synthetic-workload-not-runtime-evidence",
        "status": "building",
        "seeds": seeds,
        "requested_counts": {
            "train": training,
            "validation": validation,
            "per_scenario": scenario_events,
        },
        "source_sha256": {},
        "shards": [],
        "limitations": [
            "No measured responses or transport latency",
            "Shared templates and servers across splits; not independent real-world data",
            "Labels are fixture assumptions, not observed detector outcomes",
            "No evaluation, threshold tuning, or significance claims",
        ],
    }
    source_paths = {
        "dataset.py": Path(__file__),
        "workload.py": Path(__file__).with_name("workload.py"),
        "scenarios.py": Path(__file__).with_name("scenarios.py"),
        "novelty_scenarios.py": Path(__file__).with_name("novelty_scenarios.py"),
        "models.py": Path(runtime_models.__file__),
        "provenance.py": Path(runtime_provenance.__file__),
    }
    for name, source_path in source_paths.items():
        manifest["source_sha256"][name] = hashlib.sha256(
            source_path.read_bytes()
        ).hexdigest()
    manifest_path = output / "manifest.json"

    def save():
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    def shard(seed, split, scenario, cases, adaptive=False):
        prefix = f"{seed}/{split}/{scenario}"
        filename = f"seed-{seed}-{split}-{scenario}.jsonl.gz"
        digest = hashlib.sha256()
        malicious = 0
        # Explicit mtime and empty header filename make gzip bytes reproducible.
        with (output / filename).open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
                for index, case in enumerate(cases):
                    row = asdict(case)
                    row["interaction"]["session_id"] = (
                        prefix + "/" + row["interaction"]["session_id"]
                    )
                    row.update(event_id=f"{prefix}/{index}", seed=seed, split=split, synthetic=True)
                    line = (
                        json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False)
                        + "\n"
                    ).encode("utf-8")
                    zipped.write(line)
                    digest.update(line)
                    malicious += int(case.malicious)
        manifest["shards"].append(
            {
                "path": filename,
                "seed": seed,
                "split": split,
                "scenario": scenario,
                "events": len(cases),
                "malicious": malicious,
                "benign": len(cases) - malicious,
                "adaptive_eligible": adaptive,
                "jsonl_sha256": digest.hexdigest(),
                "gzip_sha256": hashlib.sha256((output / filename).read_bytes()).hexdigest(),
            }
        )
        save()

    save()
    for seed in seeds:
        shard(seed, "train", "normal", normal_workload(training, seed * 10, "train"))
        shard(
            seed, "validation", "normal", normal_workload(validation, seed * 10 + 1, "validation")
        )
        scenarios = build_scenarios(seed * 10 + 2, scenario_events)
        novelty = build_novelty_scenarios(seed * 10 + 2, scenario_events)
        scenarios.update({name: item.scenario for name, item in novelty.items()})
        for name, scenario in sorted(scenarios.items()):
            shard(seed, "test", name, scenario.cases, name in novelty and novelty[name].adaptive)
    manifest["total_events"] = sum(item["events"] for item in manifest["shards"])
    manifest["status"] = "complete"
    save()
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = export_dataset(args.output)
    print(json.dumps({"events": result["total_events"], "shards": len(result["shards"])}))


if __name__ == "__main__":
    main()
