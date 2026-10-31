"""Runner for complete publication-scale novelty matrix with checkpoint resumption."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentinel_research.novelty_experiment import NoveltyStudyConfig, run_novelty_study
from sentinel_research.novelty_report import generate as generate_novelty_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run complete publication-scale novelty matrix with checkpointing.")
    parser.add_argument("--seeds", default="42,123,456,789,1001")
    parser.add_argument("--output", default="results/novelty/publication_scale_complete")
    parser.add_argument("--report-output", default="results/novelty/publication_scale_report")
    parser.add_argument("--training-events", type=int, default=5000)
    parser.add_argument("--validation-events", type=int, default=1000)
    parser.add_argument("--test-events", type=int, default=3000)
    parser.add_argument("--validation-fpr", type=float, default=0.01)
    parser.add_argument("--in-process", action="store_true", default=True)
    args = parser.parse_args()

    seeds = tuple(int(s.strip()) for s in args.seeds.split(",") if s.strip())

    config = NoveltyStudyConfig(
        seeds=seeds,
        training_events=args.training_events,
        validation_events=args.validation_events,
        test_events=args.test_events,
        output=args.output,
        validation_fpr=args.validation_fpr,
        in_process=args.in_process,
        resumable=True,
    )

    print(f"=== Running Novelty Matrix ({len(seeds)} seeds, {len(config.variants)} variants, 330 phases) ===")
    print(f"Output directory: {args.output}")
    print(f"In-process transport: {args.in_process} (no socket exhaustion risk)")
    print(f"Sizes: train={args.training_events}, val={args.validation_events}, test={args.test_events}")
    t0 = time.time()

    summary = run_novelty_study(config)
    elapsed = time.time() - t0
    print(f"\nCompleted {len(summary['aggregate'])} aggregated records in {elapsed:.1f}s.")

    # Check phase record count (excluding calibration files)
    phase_files = [p for p in Path(args.output).glob("*/*/seed-*.json") if "calibration" not in p.parts]
    print(f"Total phase JSON records saved: {len(phase_files)} / 330")

    if len(phase_files) == 330:
        print("\nGenerating formal statistical novelty evaluation report...")
        generate_novelty_report(args.output, args.report_output)
        print(f"Report written to {args.report_output}/REPORT.md")
    else:
        print(f"\nMatrix incomplete ({len(phase_files)}/330). Excluded from claims.")


if __name__ == "__main__":
    main()
