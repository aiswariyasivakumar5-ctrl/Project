# Claims, Counts, and Framing Audit (Phase 5 Check)

This document provides a systematic line-by-line audit of claims, numerical counts, and methodological framing across the MCP Runtime Sentinel repository (README, `docs/*.md`, and result reports).

## 1. Disambiguation of Benchmark Counts

The repository contains two distinct benchmark evaluations with different scenario and phase counts:

| Evaluation Benchmark | Scenarios | Variants | Seeds | Phases / Cells | Reference Artifact |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Main Comparison Benchmark** | 14 test scenarios (12 attack families + `normal` + `cross_server`) | 6 models | 20 seeds (20001–20020) | 120 model evaluations | `results/baselines_20seed/` |
| **Novelty Ablation Matrix v2** | 8 scenarios (6 novelty + 2 legacy provenance) | 6 variants | 5 seeds (42, 123, 456, 789, 1001) | 330 phases (11 phases/variant/seed) | `results/novelty/publication_scale_v2/` |
| **Novelty Ablation Matrix v3** | 8 scenarios (randomized fixtures) | 6 variants | 20 new seeds (30001–30020) | 1,320 phases (66 phases/seed) | `results/novelty/publication_scale_v3/` |
| **Matched Poisoning Study** | 1 adaptive poisoning scenario | 7 policies | 20 seeds (20001–20020) | 700 cells | `results/matched_poisoning_20seed/` |
| **Held-Out Capability Trust D1**| 2 new scenarios | 1 frozen design | 20 new seeds (30001–30020) | 40 evaluations | `results/capability_trust_held_out/` |

Any document referencing scenarios, variants, or phases must state whether it refers to the 14-scenario comparison benchmark or the 8-scenario novelty matrix.

## 2. Seed Set Disjointness & Framing Rule

- **Development & Exploratory Seeds:** `42, 123, 456, 789, 1001` (used in early offline development and novelty matrix v1/v2).
- **Held-Out Main Comparison Seeds:** `20001–20020` (used strictly for 20-seed baseline and ablation comparisons).
- **Held-Out Novelty & D1 Validation Seeds:** `30001–30020` (used strictly for publication matrix v3 and held-out D1 evaluation).
- **Framing Rule:** The 5-seed and 20-seed tables evaluate distinct PRNG seed distributions. They must **never** be framed as 'improvements' or 'optimizations'; each is an independent evaluation cohort.

## 3. Flagged Claims and Verification Status

### A. Unbacked or Sweeping Claims (Audit Findings)
| File | Line | Category / Issue | Text Snippet | Status |
|---|---|---|---|---|
| `docs/capability_trust_design.md` | 62 | Use of 'eliminates' without qualification | `To eliminate data snooping concerns from Phase B, Design D1 was frozen and evaluated once on 20 new held-out seeds (3000` | Flagged / Corrected |
| `docs/claims_audit.md` | 56 | Sweeping 'zero false positives' claim without Clopper-Pearson bound or scenario qualification | `- “Zero false positives,” “100% attack detection,” or “works on all MCP attacks.”` | Flagged / Corrected |
| `docs/claims_check.md` | 31 | Use of 'eliminates' without qualification | `| `docs/capability_trust_design.md` | 62 | Use of 'eliminates' without qualification | `To eliminate data snooping conce` | Flagged / Corrected |
| `docs/claims_check.md` | 32 | Use of 'eliminates' without qualification | `| `docs/causal_workload_analysis.md` | 56 | Use of 'eliminates' without qualification | `- **Benefit:** `causal_requires` | Flagged / Corrected |
| `docs/claims_check.md` | 33 | Sweeping 'zero false positives' claim without Clopper-Pearson bound or scenario qualification | `| `docs/claims_audit.md` | 56 | Sweeping 'zero false positives' claim without Clopper-Pearson bound or scenario qualific` | Flagged / Corrected |
| `docs/claims_check.md` | 34 | Use of 'eliminates' without qualification | `| `docs/novelty_development_findings.md` | 41 | Use of 'eliminates' without qualification | `the counterfactual-score ab` | Flagged / Corrected |
| `docs/novelty_development_findings.md` | 41 | Use of 'eliminates' without qualification | `the counterfactual-score ablation reduces but does not eliminate that effect.` | Flagged / Corrected |

### B. Before/After Framing Violations
None detected: all seed cohorts are cleanly framed as independent evaluation sets.

### C. Inconsistent Numerical Counts
| File | Line | Issue | Text Snippet | Status |
|---|---|---|---|---|
| `docs/claims_check.md` | 42 | Unexpected scenario count (24) | `| `docs/runtime_controls.md` | 162 | Unexpected scenario count (24) | `24 scenario/phase/seed evaluations. Outputs are u` | Flagged / Corrected |
| `docs/runtime_controls.md` | 162 | Unexpected scenario count (24) | `24 scenario/phase/seed evaluations. Outputs are under the ignored local directory` | Flagged / Corrected |
