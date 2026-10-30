import sys
from pathlib import Path

WORKSPACE_ROOT = str(Path(__file__).resolve().parent.parent)
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

import json
from sentinel.novelty_experiment import summarize
from sentinel.novelty_report import generate

root = Path("results/novelty/publication_scale_v3")
files = [p for p in sorted(root.glob("*/*/seed-*.json")) if "calibration" not in p.parts]
print(f"Aggregating {len(files)} files into summary.json...")
results = []
for f in files:
    row = json.loads(f.read_text(encoding="utf-8"))
    row.pop("decisions", None)
    results.append(row)

summary = summarize(results)
(root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print("summary.json written successfully!")

print("Generating publication statistical report...")
report = generate("results/novelty/publication_scale_v3", "results/novelty/publication_scale_v3_report")
print("Report generated successfully!")

print("\n=== PRIMARY HYPOTHESIS TESTS ON 20 NEW SEEDS (30001-30020) ===")
for comp in report["primary_comparisons"]:
    diff = comp["difference_ci"]["estimate"]
    ci_low = comp["difference_ci"]["lower"]
    ci_up = comp["difference_ci"]["upper"]
    p_val = comp["test"]["p_value_two_sided"]
    holm_p = comp["holm_p"]
    sig = comp["significant_0_05"]
    print(f"  {comp['name']}:")
    print(f"    Diff (A - B): {diff:.6f} [95% CI: {ci_low:.6f}, {ci_up:.6f}]")
    print(f"    Exact two-sided sign-flip p: {p_val:.6e}")
    print(f"    Holm-adjusted p: {holm_p:.6e}")
    print(f"    Significant at alpha=0.05? {sig}")
