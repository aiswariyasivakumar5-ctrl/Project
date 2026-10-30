"""Export vector figures from completed novelty statistics and retained curves."""

import argparse
import json
from html import escape
from pathlib import Path

from .plots import COLORS, line_chart

LABELS = {
    "baseline": "Baseline",
    "full": "Full (historical)",
    "without_intent_provenance": "Without intent score",
    "without_capability_trust": "Without capability trust",
    "without_dual_memory": "Without dual memory",
    "approval_required": "Approval required",
}


def interval_plot(title, rows, metric):
    """Horizontal point and interval plot; N/A remains visible."""
    vals = [row["metrics"][metric]["ci"] for row in rows]
    maximum = max([c["upper"] for c in vals if c] + [1e-6]) * 1.08

    def x(value):
        return 260 + 610 * value / maximum

    height = 110 + len(rows) * 48
    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1020" height="{height}" viewBox="0 0 1020 {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="20" y="28" font-family="Arial" font-size="18">{escape(title)}</text>',
        '<text x="20" y="50" font-family="Arial" font-size="12">Mean and 95% seed bootstrap CI; undefined values are N/A</text>',
    ]
    for i, (row, ci) in enumerate(zip(rows, vals, strict=False)):
        y = 85 + i * 48
        body.append(
            f'<text x="15" y="{y + 4}" font-family="Arial" font-size="13">{LABELS[row["variant"]]}</text>'
        )
        if ci:
            body.append(
                f'<line x1="{x(ci["lower"]):.2f}" x2="{x(ci["upper"]):.2f}" y1="{y}" y2="{y}" stroke="{COLORS[i % 6]}" stroke-width="3"/>'
            )
            body.append(
                f'<circle cx="{x(ci["estimate"]):.2f}" cy="{y}" r="5" fill="{COLORS[i % 6]}"/>'
            )
        body.append(
            f'<text x="890" y="{y + 4}" font-family="Arial" font-size="12">{format(ci["estimate"], ".4g") if ci else "N/A"}</text>'
        )
    body.append(
        f'<text x="260" y="{height - 10}" font-family="Arial" font-size="12">0</text><text x="820" y="{height - 10}" font-family="Arial" font-size="12">{maximum:.4g}</text></svg>'
    )
    return "".join(body)


def generate(source, statistics_path, output):
    source, output = Path(source), Path(output)
    report = json.loads(Path(statistics_path).read_text(encoding="utf-8"))
    protocol = json.loads((source / "protocol.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=False)
    files = []
    for scenario, phase in sorted({(r["scenario"], r["phase"]) for r in report["aggregate"]}):
        rows = [r for r in report["aggregate"] if (r["scenario"], r["phase"]) == (scenario, phase)]
        for metric in (
            "f1",
            "false_positive_rate",
            "detection_delay_events",
            "latency_mean_ms",
            "model_updates",
        ):
            name = f"{scenario}-{phase}-{metric}.svg"
            (output / name).write_text(
                interval_plot(f"{scenario} / {phase}: {metric}", rows, metric), encoding="utf-8"
            )
            files.append(name)
        seed = protocol["configuration"]["seeds"][0]
        for field, xx, yy in (
            ("roc_curve", "fpr", "tpr"),
            ("precision_recall_curve", "recall", "precision"),
        ):
            series = {}
            for row in rows:
                data = json.loads(
                    (source / row["variant"] / scenario / f"seed-{seed}-{phase}.json").read_text(
                        encoding="utf-8"
                    )
                )
                points = data["metrics"][field]
                if points:
                    series[LABELS[row["variant"]]] = [(p[xx], p[yy]) for p in points]
            if series:
                name = f"{scenario}-{phase}-{field}.svg"
                (output / name).write_text(
                    line_chart(f"{scenario} / {phase}: seed {seed}", series, xx, yy),
                    encoding="utf-8",
                )
                files.append(name)
    (output / "INDEX.md").write_text(
        "# Novelty vector figures\n\n"
        "Interval figures use all recorded seeds. ROC/PR illustrations use the first prespecified seed, not a selected best seed.\n"
        "Latency is total local gateway time, not measured direct-server overhead. Delay is conditional on detection.\n"
        "Model-update panels for legitimate_upgrade and poisoning describe adaptation, not real deployment drift.\n\n"
        + "\n".join(f"- [{name}]({name})" for name in files)
        + "\n",
        encoding="utf-8",
    )
    return files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--statistics", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    generate(args.source, args.statistics, args.output)
