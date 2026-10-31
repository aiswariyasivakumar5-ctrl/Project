"""Audit retained degradation evidence and render descriptive per-seed tables."""

import argparse
import itertools
import json
import math
from pathlib import Path

from .adaptation_study import summarize_events
from .degradation_study import probe_metrics


def render(output):
    output = Path(output)

    def read(name):
        return json.loads((output / name).read_text(encoding="utf-8"))

    execution, protocol, rows = read("execution.json"), read("protocol.json"), read("summary.json")
    expected = set(
        itertools.product(
            protocol["seeds"], protocol["policies"], ("clean", "abrupt", "gradual_after_promotion")
        )
    )
    actual = {(r["seed"], r["policy"], r["stream"]) for r in rows}
    if (
        execution["status"] != "complete"
        or execution["completed"] != len(expected)
        or actual != expected
        or len(rows) != len(expected)
    ):
        raise ValueError("incomplete or duplicated matrix")
    for row in rows:
        path = output / f"{row['seed']}-{row['policy']}-{row['stream']}.jsonl"
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        summary = summarize_events(events)
        if len(events) != 12 or not summary["attribution_complete"]:
            raise ValueError("incomplete event attribution")
        for key, value in summary.items():
            if row[key] != value:
                raise ValueError(f"event summary mismatch: {key}")
        for phase in ("before", "after"):
            probes = row[f"{phase}_probes"]
            if len(probes) != 6 or [p["index"] for p in probes] != list(range(6)):
                raise ValueError("incomplete probes")
            if any(p["model_sha256"] != row[f"{phase}_model_sha256"] for p in probes):
                raise ValueError("probe model digest mismatch")
            for key, value in probe_metrics(probes).items():
                if not math.isclose(value, row[f"{phase}_probe_metrics"][key], abs_tol=1e-12):
                    raise ValueError("probe metric mismatch")
        clean = next(
            r
            for r in rows
            if (r["seed"], r["policy"], r["stream"]) == (row["seed"], row["policy"], "clean")
        )
        for key, value in row["after_probe_metrics"].items():
            if not math.isclose(
                value - clean["after_probe_metrics"][key],
                row["post_minus_clean_probe_metrics"][key],
                abs_tol=1e-12,
            ):
                raise ValueError("paired clean comparison mismatch")
    lines = [
        "# Audited fixed-probe development results",
        "",
        "Scores are descriptive. No confidence intervals or statistical significance are claimed.",
        "",
        "| Seed | Policy | Stream | Updates | Malicious updates | Probe recall before / after | Probe FPR after | Attack-risk change vs clean |",
        "| --- | --- | --- | ---: | ---: | --- | ---: | ---: |",
    ]
    for r in rows:
        lines.append(
            f"| {r['seed']} | {r['policy']} | {r['stream']} | {r['model_updates']} | {r['malicious_learning_updates']} | "
            f"{r['before_probe_metrics']['attack_recall']:.2f} / {r['after_probe_metrics']['attack_recall']:.2f} | "
            f"{r['after_probe_metrics']['benign_fpr']:.2f} | {r['post_minus_clean_probe_metrics']['mean_attack_risk']:.6f} |"
        )
    with (output / "tables.md").open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return {
        "audited_cells": len(rows),
        "event_records": len(rows) * 12,
        "stored_probe_records": len(rows) * 12,
        "note": "Pre-adaptation probe records are reused across streams within each seed/policy.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(render(parser.parse_args().output), indent=2))
