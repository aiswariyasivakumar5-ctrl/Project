"""Run publication-scale novelty matrix v3 across 20 new seeds in parallel."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure local repository takes precedence over any site-packages or other downloads
WORKSPACE_ROOT = str(Path(__file__).resolve().parent.parent)
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

import concurrent.futures
import json
import os
import time
from dataclasses import asdict

from sentinel.novelty_experiment import (
    NoveltyStudyConfig,
    run_novelty_study,
    summarize,
)
from sentinel.novelty_report import generate

SEEDS = tuple(range(30001, 30021))
OUTPUT_DIR = "results/novelty/publication_scale_v3"
REPORT_DIR = "results/novelty/publication_scale_v3_report"


def run_single_seed(seed: int) -> int:
    # Ensure sys.path in worker processes
    if WORKSPACE_ROOT not in sys.path:
        sys.path.insert(0, WORKSPACE_ROOT)
    config = NoveltyStudyConfig(
        seeds=(seed,),
        training_events=5000,
        validation_events=1000,
        test_events=3000,
        output=OUTPUT_DIR,
        validation_fpr=0.01,
        in_process=True,
        resumable=True,
    )
    t0 = time.perf_counter()
    run_novelty_study(config)
    elapsed = time.perf_counter() - t0
    print(f"[Worker] Completed seed {seed} in {elapsed:.1f}s", flush=True)
    return seed


def main() -> None:
    root = Path(OUTPUT_DIR)
    root.mkdir(parents=True, exist_ok=True)

    # Master protocol with all 20 seeds
    full_config = NoveltyStudyConfig(
        seeds=SEEDS,
        training_events=5000,
        validation_events=1000,
        test_events=3000,
        output=OUTPUT_DIR,
        validation_fpr=0.01,
        in_process=True,
        resumable=True,
    )
    protocol = {
        "configuration": asdict(full_config),
        "policy": "fixed gateway action bands and runtime trust; optional validation-only secondary score threshold",
        "validation_used_for_tuning": True,
        "test_learning": False,
        "calibration_scope": "secondary score report only; gateway decisions unchanged",
        "adaptive_from": "independent post-TRAIN checkpoint",
        "identity_model": "trusted sequential fixture; rotating raw sessions do not create independent actors",
        "reviewed_recovery": "operator incident-response API; intentionally not exercised during autonomous unattended benchmarks",
    }
    (root / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")

    max_workers = min(10, os.cpu_count() or 4)
    print(f"Launching publication_scale_v3 on {len(SEEDS)} seeds with {max_workers} parallel workers...", flush=True)
    t_start = time.perf_counter()

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_single_seed, seed): seed for seed in SEEDS}
        for future in concurrent.futures.as_completed(futures):
            seed = futures[future]
            try:
                future.result()
            except Exception as exc:
                print(f"[Error] Seed {seed} failed: {exc}", file=sys.stderr, flush=True)
                raise

    total_time = time.perf_counter() - t_start
    print(f"All {len(SEEDS)} seeds finished in {total_time:.1f}s ({total_time/60:.2f} mins)", flush=True)

    # Collect all rows across all 20 seeds and write summary
    files = [p for p in sorted(root.glob("*/*/seed-*.json")) if "calibration" not in p.parts]
    print(f"Aggregating {len(files)} phase records into summary...", flush=True)
    results = []
    for f in files:
        row = json.loads(f.read_text(encoding="utf-8"))
        row.pop("decisions", None)
        results.append(row)

    summary = summarize(results)
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Generate full publication statistical report
    print(f"Generating publication statistical report in {REPORT_DIR}...", flush=True)
    report = generate(OUTPUT_DIR, REPORT_DIR)
    print("Novelty matrix publication scale v3 completed successfully!", flush=True)
    for comp in report["primary_comparisons"]:
        print(f"  {comp['name']}: A-B = {comp['difference_ci']['estimate']:.6f}, "
              f"p = {comp['test']['p_value_two_sided']:.6f}, holm_p = {comp['holm_p']:.6f}")


if __name__ == "__main__":
    main()
