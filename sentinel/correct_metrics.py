"""Read retained event scores and write a separate, versioned AUROC correction."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .metrics import Observation, calculate_metrics


def correction_report(root: Path) -> dict:
    rows, unavailable = [], []
    for folder in ("baselines_publication", "baselines_sequence"):
        for source in sorted((root / "results" / folder).glob("*/per_seed/*.json")):
            data = json.loads(source.read_text(encoding="utf-8"))
            events = data.get("event_outcomes")
            if not events:
                unavailable.append(str(source.relative_to(root)))
                continue
            observations = [
                Observation(
                    event["malicious"],
                    event["intervened"],
                    event["score_percentile"],
                    0,
                    0,
                    1,
                    1,
                    index,
                )
                for index, event in enumerate(events)
            ]
            corrected = calculate_metrics(observations)["auroc"]
            rows.append(
                {
                    "model": data["model"],
                    "seed": data["seed"],
                    "source": str(source.relative_to(root)),
                    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "original_auroc": data["metrics"]["auroc"],
                    "corrected_auroc": corrected,
                }
            )
    return {
        "schema_version": 1,
        "correction": "include empty-selection ROC endpoint",
        "scope": "Recomputed from saved percentile scores; no retraining or threshold changes.",
        "results": rows,
        "missing_event_outcomes": unavailable,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = correction_report(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite an existing artifact, including the original evidence.
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"Wrote {len(report['results'])} recalculations to {args.output}")


if __name__ == "__main__":
    main()
