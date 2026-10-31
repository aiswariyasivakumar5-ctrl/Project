"""Check README and paper-number summaries against generated TeX metrics."""

from __future__ import annotations

import re
from pathlib import Path
import sys

MACRO = re.compile(r"\\newcommand\{\\([A-Za-z]+)\}\{([^}]*(?:\{[^}]*\}[^}]*)*)\}")
REQUIRED_VALUES = {
    "SentinelFOne": ("README.md", "docs/paper_numbers.md"),
    "SentinelPrecision": ("README.md", "docs/paper_numbers.md"),
    "SentinelRecall": ("README.md", "docs/paper_numbers.md"),
    "SentinelFPR": ("README.md", "docs/paper_numbers.md"),
    "SentinelFPRBound": ("README.md", "docs/paper_numbers.md"),
    "DenseAEFOne": ("README.md", "docs/paper_numbers.md"),
    "DenseAEPrecision": ("README.md", "docs/paper_numbers.md"),
    "DenseAERecall": ("README.md", "docs/paper_numbers.md"),
    "DenseAEFPR": ("README.md", "docs/paper_numbers.md"),
    "TransformerFOne": ("README.md", "docs/paper_numbers.md"),
    "TransformerPrecision": ("README.md", "docs/paper_numbers.md"),
    "TransformerRecall": ("README.md", "docs/paper_numbers.md"),
    "TransformerFPR": ("README.md", "docs/paper_numbers.md"),
    "LSTMFOne": ("README.md", "docs/paper_numbers.md"),
    "LSTMPrecision": ("README.md", "docs/paper_numbers.md"),
    "LSTMRecall": ("README.md", "docs/paper_numbers.md"),
    "LSTMFPR": ("README.md", "docs/paper_numbers.md"),
    "OneClassSVMFOne": ("README.md", "docs/paper_numbers.md"),
    "OneClassSVMPrecision": ("README.md", "docs/paper_numbers.md"),
    "OneClassSVMRecall": ("README.md", "docs/paper_numbers.md"),
    "OneClassSVMFPR": ("README.md", "docs/paper_numbers.md"),
    "IsolationForestFOne": ("README.md", "docs/paper_numbers.md"),
    "IsolationForestPrecision": ("README.md", "docs/paper_numbers.md"),
    "IsolationForestRecall": ("README.md", "docs/paper_numbers.md"),
}


def normalize(value: str) -> str:
    return value.replace("{,}", ",").replace(r"\%", "%").replace("{", "").replace("}", "")


def audit(root: Path) -> list[str]:
    tex = (root / "paper/numbers.tex").read_text(encoding="utf-8")
    macros = {name: normalize(value) for name, value in MACRO.findall(tex)}
    errors: list[str] = []
    for name, paths in REQUIRED_VALUES.items():
        if name not in macros:
            errors.append(f"paper/numbers.tex is missing generated macro {name}")
            continue
        expected = macros[name]
        for relpath in paths:
            content = normalize((root / relpath).read_text(encoding="utf-8"))
            if expected not in content:
                errors.append(f"{relpath} does not contain generated {name} value {expected!r}")

    main_seeds = "20 independent evaluation seeds" in (root / "README.md").read_text(
        encoding="utf-8"
    ) and "20001–20020" in (root / "README.md").read_text(encoding="utf-8")
    if not main_seeds:
        errors.append("README.md main-comparison seed count/range must be 20 seeds (20001–20020)")
    historical = "historical snapshots, not current test counts" in (
        root / "docs/project_status.md"
    ).read_text(encoding="utf-8")
    if not historical:
        errors.append("docs/project_status.md must label old test totals as historical snapshots")
    return errors


def main() -> None:
    errors = audit(Path(__file__).resolve().parents[1])
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    print(f"documentation number check passed: {len(REQUIRED_VALUES)} generated metrics and seed/test-count labels")


if __name__ == "__main__":
    main()
