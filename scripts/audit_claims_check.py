"""Audit claims across docs, README, and drafts."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(".")
FILES_TO_CHECK = [
    Path("README.md"),
    *sorted(Path("docs").glob("*.md")),
    Path("results/novelty/publication_scale_v2_report/REPORT.md"),
    Path("results/novelty/publication_scale_v3_report/REPORT.md"),
]
if Path("paper_draft.md").exists():
    FILES_TO_CHECK.append(Path("paper_draft.md"))

PATTERNS = [
    ("zero false positive", re.compile(r"zero\s+false[- ]positive", re.I)),
    ("eliminates", re.compile(r"\beliminates?\b", re.I)),
    ("proves / proof", re.compile(r"\b(proves|proven|unconditionally)\b", re.I)),
    ("100% recall / perfect", re.compile(r"\b(100%\s+detection|perfect\s+detection)\b", re.I)),
    ("5 vs 20 improvement framing", re.compile(r"(improved|boosted|increased)\s+from\s+5\s+seeds", re.I)),
]


def audit() -> list[dict]:
    findings = []
    for f in FILES_TO_CHECK:
        if not f.exists():
            continue
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        for idx, line in enumerate(lines, 1):
            for name, pat in PATTERNS:
                if pat.search(line):
                    findings.append({
                        "file": str(f).replace("\\", "/"),
                        "line": idx,
                        "category": name,
                        "content": line.strip()[:140],
                    })
    return findings


if __name__ == "__main__":
    results = audit()
    print(f"Found {len(results)} matches.")
    for r in results[:30]:
        print(f"[{r['category']}] {r['file']}:{r['line']} -> {r['content']}")
