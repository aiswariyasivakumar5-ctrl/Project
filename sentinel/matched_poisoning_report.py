"""Render exact per-seed diagnostic counts; no inferential statistics."""

import argparse
import json
from pathlib import Path


def render_report(output):
    output = Path(output)
    state = json.loads((output / "execution.json").read_text(encoding="utf-8"))
    if state["status"] != "complete" or state["completed"] != state["planned"]:
        raise ValueError("only a complete study can be reported")
    rows = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    if len(rows) != state["completed"]:
        raise ValueError("summary does not contain every completed run")
    seeds = sorted({r["seed"] for r in rows})
    lines = [
        "# Matched poisoning development diagnostic",
        "",
        f"Seed order: {seeds}. Slash-separated values are exact per-seed results, not confidence intervals.",
        "Delay is in event steps; NA means no benign events and censored means benign learning did not occur.",
        "",
        "| Stream | Policy | Total updates | Malicious-source updates | Benign learning delay | Benign intervention rate | Malicious intervention rate |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for stream, policy in sorted({(r["stream"], r["policy"]) for r in rows}):
        group = sorted(
            [r for r in rows if (r["stream"], r["policy"]) == (stream, policy)],
            key=lambda r: r["seed"],
        )
        if [r["seed"] for r in group] != seeds or not all(r["attribution_complete"] for r in group):
            raise ValueError("incomplete matched seeds or source attribution")

        def values(key, group=group):
            return " / ".join("NA" if r[key] is None else str(r[key]) for r in group)

        delay = " / ".join(
            "NA"
            if not r["benign_learning_applicable"]
            else "censored"
            if r["benign_learning_censored"]
            else str(r["benign_learning_delay"])
            for r in group
        )
        lines.append(
            f"| {stream} | {policy} | {values('model_updates')} | {values('malicious_learning_updates')} | {delay} | {values('benign_intervention_rate')} | {values('malicious_intervention_rate')} |"
        )
    lines += [
        "",
        "Malicious-source updates measure ingestion, not induced model degradation. The wrong numeric answers have the same extracted features as correct answers.",
        "Oracle review uses scenario knowledge. No statistical significance, real-world security, or patentability claim follows from these controls.",
        "",
    ]
    with (output / "tables.md").open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    render_report(parser.parse_args().output)
