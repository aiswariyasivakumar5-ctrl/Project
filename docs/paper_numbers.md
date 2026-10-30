# Paper Numbers Traceability Index: MCP Runtime Sentinel

This document provides a line-by-line, cell-by-cell mapping of empirical metrics, confidence intervals, p-values, and test statistics reported in the manuscript.

Headline baseline values and generated tables are derived from retained JSON artifacts. Narrative protocol constants and some novelty/ablation values remain explicitly stated in the manuscript and should be checked against their cited source artifacts during final review.

---

## 1. Table 1: Main Model Baseline Comparison (20 Seeds)

**Evaluation Protocol**:
- Seeds: 20001–20020 (20 seeds).
- Splits: Train = 5,000, Validation = 1,000, Test = 3,250 synthetic mock events per seed (1,750 benign and 1,500 attack events).
- Confidence Intervals: 95% seed-cluster percentile bootstrap (20,000 resamples).
- Statistical Significance: Paired exact Wilcoxon signed-rank test against Sentinel with Holm step-down multiple-testing adjustment.
- **Source Scripts**: `scripts/reproduce_main.py`, `sentinel/compare.py`, `sentinel/research_tables.py`
- **Raw Artifacts**:
  - Aggregated Metrics: `results/baselines_20seed/aggregate/metrics.json`
  - Per-Seed Evaluations: `results/baselines_20seed/{model}/per_seed/seed-{20001..20020}.json`
  - Statistical Analysis: `results/statistical_analysis_20seed/baseline_statistics.json`
  - Publication Tables: `results/tables_20seed/baseline_comparison.md`, `.csv`, `.json`

### Cell-by-Cell Traceability

| Model | Reported F1 (Mean ± Std [95% CI]) | Precision | Recall | FPR | AUROC | AUPRC | Wilcoxon p (Holm-adj) | Effect Size $r$ | Exact Raw JSON Source Path |
|---|---|---|---|---|---|---|---|---|---|
| **Sentinel** | **0.8000 ± 0.0001** [0.8000, 0.8000] | 0.99995 | 0.6667 | 0.0000286 | 0.8691 | 0.8304 | Reference (-) | Reference (-) | `results/baselines_20seed/aggregate/metrics.json` -> `["sentinel"]` |
| **Dense Autoencoder** | **0.8815 ± 0.0265** [0.8704, 0.8931] | 0.9051 | 0.8601 | 0.0771 | 0.9349 | 0.8883 | $p = 0.000002$ ($p_{adj} = 0.000010$) | $r = -1.0000$ | `results/baselines_20seed/aggregate/metrics.json` -> `["dense_autoencoder"]` |
| **Isolation Forest** | **0.0000 ± 0.0000** [0.0000, 0.0000] | 0.0000 | 0.0000 | 0.0073 | 0.8923 | 0.7749 | $p = 0.000002$ ($p_{adj} = 0.000010$) | $r = +1.0000$ | `results/baselines_20seed/aggregate/metrics.json` -> `["isolation_forest"]` |
| **LSTM** | **0.8250 ± 0.0058** [0.8227, 0.8274] | 0.8936 | 0.7663 | 0.0782 | 0.9422 | 0.8868 | $p = 0.000002$ ($p_{adj} = 0.000010$) | $r = -1.0000$ | `results/baselines_20seed/aggregate/metrics.json` -> `["lstm"]` |
| **One-Class SVM** | **0.7904 ± 0.1245** [0.7350, 0.8391] | 0.8849 | 0.7364 | 0.0859 | 0.9218 | 0.8918 | $p = 0.927279$ ($p_{adj} = 0.927279$) | $r = +0.0286$ | `results/baselines_20seed/aggregate/metrics.json` -> `["one_class_svm"]` |
| **Transformer** | **0.8381 ± 0.0101** [0.8338, 0.8422] | 0.8965 | 0.7869 | 0.0778 | 0.9375 | 0.8859 | $p = 0.000002$ ($p_{adj} = 0.000010$) | $r = -1.0000$ | `results/baselines_20seed/aggregate/metrics.json` -> `["transformer"]` |

*Notes*:
- **False Positive Rate & Clopper-Pearson 95% Bound**: Across 35,000 benign test events (1,750 per seed across 20 seeds), one false positive occurred (seed 20008). The pooled empirical FPR is $1/35{,}000 = 0.0000286$ (0.00286%); the exact 95% upper bound is 0.0159%. Mean seed-level precision is 0.99995, not 1.0000.
- **All-or-Nothing Recall**: Sentinel's 0.6667 recall is an exact all-or-nothing step function across the 12 attack families: 8 families are detected with 1.0000 recall, while 4 subtle/temporal families (`abnormal_sequence`, `capability_drift`, `gradual_poisoning`, `low_and_slow`) have 0.0000 recall due to order-invariant feature boundaries (see Table 3).
- **Matched-FPR Dual-Basis Reconciliation**: The raw-score threshold sweep (Basis b) selects thresholds using benign scores from the same test split. Treat its values as descriptive ROC analysis, not independently calibrated operating performance. The stored percentile sweep (Basis c) is a different score representation; the minimum nonzero FPR at which neural baselines obtain nonzero recall is 7.14% (125/1,750 benign events). See `docs/matched_fpr_reconciliation.md`.
- **Isolation Forest Collapse**: Isolation Forest suffers complete detection collapse ($F_1 = 0.0000$) under validation-calibrated decision thresholds on this synthetic feature representation.

---

## 2. Table 2: Sentinel Ablation Study (20 Seeds)

**Protocol**:
- Compares Sentinel Full against 5 single-component ablations on identical 20-seed synthetic test splits.
- **Source Scripts**: `sentinel/ablation.py`, `sentinel/research_tables.py`
- **Raw Artifacts**:
  - Aggregated Metrics: `results/ablations_20seed/aggregate/metrics.json`
  - Per-Seed Evaluations: `results/ablations_20seed/{variant}/per_seed/seed-{20001..20020}.json`
  - Publication Tables: `results/tables_20seed/ablation_matrix.md`, `.csv`, `.json`

### Cell-by-Cell Traceability

| Sentinel Variant | F1 (Mean ± Std [95% CI]) | Precision | Recall | FPR | Sign-Flip $p$ | Effect Relative to Full Model | Exact Raw JSON Key |
|---|---|---|---|---|---|---|---|
| **Full Architecture** | **0.8000 ± 0.0001** [0.8000, 0.8000] | 1.0000 | 0.6667 | 0.0000 | Reference | Reference | `results/ablations_20seed/aggregate/metrics.json` -> `["full"]` |
| **Without Attestation** | **0.8000 ± 0.0001** [0.8000, 0.8000] | 1.0000 | 0.6667 | 0.0000 | $p = 1.0000$ | Zero metric change on mock workload | `results/ablations_20seed/aggregate/metrics.json` -> `["without_attestation"]` |
| **Without Causal Filter** | **0.9119 ± 0.0025** [0.9108, 0.9129] | 0.9072 | 0.9167 | 0.0804 | $p = 0.000002$ | Trades zero-FPR for higher recall ($\Delta F1 = +0.1119$, FPR increases to $8.04\%$) | `results/ablations_20seed/aggregate/metrics.json` -> `["without_causal"]` |
| **Without Intent Context** | **0.0000 ± 0.0000** [0.0000, 0.0000] | 0.0000 | 0.0000 | 0.0000 | $p = 0.000002$ | Complete collapse ($\Delta F1 = -0.8000$); intent conditioning is critical | `results/ablations_20seed/aggregate/metrics.json` -> `["without_intent"]` |
| **Without Quarantine** | **0.8000 ± 0.0001** [0.8000, 0.8000] | 1.0000 | 0.6667 | 0.0000 | $p = 1.0000$ | Static test split invariance; dynamic impact seen in poisoning | `results/ablations_20seed/aggregate/metrics.json` -> `["without_quarantine"]` |
| **Without Uncertainty** | **0.8000 ± 0.0001** [0.8000, 0.8000] | 1.0000 | 0.6667 | 0.0000 | $p = 1.0000$ | Boundary invariant under non-overlapping mock feature distributions | `results/ablations_20seed/aggregate/metrics.json` -> `["without_uncertainty"]` |

---

## 3. Table 3: Per-Attack Scenario Recall & Failure Modes

**Source Scripts**: `sentinel/compare.py`, `sentinel/research_tables.py`
**Raw Artifacts**: `results/tables_20seed/per_attack_recall.md`, `results/baselines_20seed/per_scenario/metrics.csv`

### Cell-by-Cell Traceability

| Attack Scenario Family | Events | Sentinel Full Recall | Dense AE Recall | LSTM Recall | Transformer Recall | Vulnerability / Analysis |
|---|---|---|---|---|---|---|
| `abnormal_sequence` | 1,002 | **0.0000** | 1.0000 | 1.0000 | 1.0000 | **Zero-Recall Family**: Order-invariant bag-of-calls representation cannot detect temporal permutations. |
| `capability_drift` | 1,002 | **0.0000** | 0.9980 | 0.9960 | 0.9970 | **Zero-Recall Family**: Gradual parameter drift within legitimate tooling envelope. |
| `cross_server` | 1,002 | **1.0000** | 1.0000 | 1.0000 | 1.0000 | Fully detected by intent-conditioned capability matching. |
| `data_exfiltration` | 1,002 | **1.0000** | 1.0000 | 1.0000 | 1.0000 | Detected via high reconstruction error on payload size & destination. |
| `delayed_malicious` | 1,002 | **1.0000** | 1.0000 | 1.0000 | 1.0000 | Fully intercepted upon departure from baseline profile. |
| `destructive_operation` | 1,002 | **1.0000** | 1.0000 | 1.0000 | 1.0000 | Intercepted by intent provenance violation. |
| `gradual_poisoning` | 1,002 | **0.0000** | 0.9990 | 0.9970 | 0.9980 | **Zero-Recall Family**: Incremental drift stays inside autoencoder threshold per step. |
| `intent_mismatch` | 1,002 | **1.0000** | 1.0000 | 1.0000 | 1.0000 | Fully detected by semantic intent matcher. |
| `low_and_slow` | 1,002 | **0.0000** | 0.9980 | 0.9960 | 0.9970 | **Zero-Recall Family**: Low frequency anomalies fall below cumulative variance detector. |
| `policy_injection` | 1,002 | **1.0000** | 1.0000 | 1.0000 | 1.0000 | Intercepted by policy validator. |
| `schema_mutation` | 1,002 | **1.0000** | 1.0000 | 1.0000 | 1.0000 | Detected by capability signature mismatch. |
| `tool_poisoning` | 1,002 | **1.0000** | 1.0000 | 1.0000 | 1.0000 | Intercepted by quarantined memory buffer. |

---

## 4. Table 4: Novelty Evaluation Matrix (v2 Exploratory & v3 20-Seed Preregistered)

### A. Novelty Evaluation Matrix v3 (20 New Seeds 30001–30020, 1,320 Completed Phases)
- **Protocol**: 8 scenarios × 6 variants × 20 seeds (30001–30020) with genuine seed-driven fixture randomization = 1,320 completed evaluations.
- **Source Scripts**: `scripts/run_novelty_matrix_v3.py`, `scripts/finish_novelty_v3.py`, `sentinel/novelty_report.py`
- **Raw Artifacts**:
  - Evaluation Files: `results/novelty/publication_scale_v3/*/*/seed-*.json` (1,320 files)
  - Summary: `results/novelty/publication_scale_v3/summary.json`
  - Report: `results/novelty/publication_scale_v3_report/REPORT.md`
  - Statistics: `results/novelty/publication_scale_v3_report/statistics.json`

#### Planned Primary Hypothesis Comparisons (v3, 20 Seeds)

| Endpoint Name | Variant A | Variant B | Scenario | Phase | Metric | A minus B [95% CI] | Two-Sided $p$ | Holm-Adjusted $p$ | Significant ($\alpha=0.05$)? | Raw Artifact Key |
|---|---|---|---|---|---|---|---|---|---|---|
| `capability_isolation` | `full` | `without_capability_trust` | `capability_laundering` | `test` | `false_positive_rate` | **-0.995233** [-0.995700, -0.994900] | **1.91e-06** | **7.63e-06** | **Yes** ($p < 0.0001$) | `publication_scale_v3_report/statistics.json` -> `primary_comparisons[0]` |
| `single_actor_poisoning` | `full` | `without_dual_memory` | `distributed_poisoning` | `adaptive` | `model_updates` | **-3000.000000** [-3000.0, -3000.0] | **1.91e-06** | **7.63e-06** | **Yes** ($p < 0.0001$) | `publication_scale_v3_report/statistics.json` -> `primary_comparisons[1]` |
| `intent_consistency` | `full` | `without_intent_provenance` | `coordinated_servers` | `test` | `recall` | **0.000000** [0.000, 0.000] | $1.000000$ | $1.000000$ | No (Null result) | `publication_scale_v3_report/statistics.json` -> `primary_comparisons[2]` |
| `review_requirement` | `approval_required` | `full` | `multi_actor_poisoning` | `adaptive` | `model_updates` | **0.000000** [0.000, 0.000] | $1.000000$ | $1.000000$ | No (Null result) | `publication_scale_v3_report/statistics.json` -> `primary_comparisons[3]` |

### B. Historical Novelty Matrix v2 (5 Seeds 42..1001, 330 Phases)
- **Protocol**: 8 scenarios × 6 variants × 5 legacy seeds = 330 evaluations.
- **Source Artifacts**: `results/novelty/publication_scale_v2_report/REPORT.md`, `statistics.json` (330 phase files in `publication_scale_v2/`).
- *Note*: Deterministic fixtures capped exact sign-flip tests at $p = 0.0625$ floor.

---

## 4.1 Table 4.1: Matched-FPR Reconciliation & Dual-Basis Evaluation (20 Seeds)
- **Source Scripts**: `scripts/reconcile_matched_fpr.py`
- **Raw Artifacts**:
  - Basis (a) Decision-Rule Operating Points: `results/matched_fpr_v2/decision_rule_operating_points.json`, `.csv`, `.md`
  - Basis (b) Raw-Score ROC Sweeps: `results/matched_fpr_v2/raw_score_matched_fpr.json`, `.csv`, `.md`
  - Score Tie Statistics: `results/matched_fpr_v2/tie_statistics.json`

| Basis | Model | Operating FPR (95% CI) | Operating Recall (95% CI) | Status in Paper |
| :--- | :--- | :---: | :---: | :--- |
| **Basis (a): Gateway Decision Rule** | **Sentinel** | **0.000029** [0.000000, 0.000159] | **0.6667** [0.6667, 0.6667] | Primary headline operating point |
| Basis (a): Gateway Decision Rule | Dense Autoencoder | 0.077143 [0.076317, 0.077977] | 0.8601 [0.8492, 0.8711] | Baseline operating point |
| Basis (a): Gateway Decision Rule | Transformer | 0.077829 [0.076880, 0.078749] | 0.7869 [0.7825, 0.7913] | Baseline operating point |
| Basis (a): Gateway Decision Rule | LSTM | 0.078200 [0.077114, 0.079257] | 0.7663 [0.7637, 0.7688] | Baseline operating point |
| **Basis (b): Raw-Score Sweep ($\text{FPR} \le 1.0\%$)** | **Sentinel** | **0.000029** [0.000000, 0.000159] | **0.6667** [0.6667, 0.6667] | Continuous sweep operating point |
| Basis (b): Raw-Score Sweep ($\text{FPR} \le 1.0\%$) | Dense Autoencoder | 0.010000 [0.009714, 0.010000] | **0.5000** [0.5000, 0.5000] | Partial recall (reconstruction anomalies only) |
| Basis (b): Raw-Score Sweep ($\text{FPR} \le 1.0\%$) | Transformer | 0.010000 [0.009714, 0.010000] | **0.5000** [0.5000, 0.5000] | Partial recall (reconstruction anomalies only) |
| Basis (b): Raw-Score Sweep ($\text{FPR} \le 1.0\%$) | LSTM | 0.010000 [0.009714, 0.010000] | **0.5000** [0.5000, 0.5000] | Partial recall (reconstruction anomalies only) |
| **Basis (c): Stored Percentile Sweep ($\text{FPR} \le 1.0\%$)** | **Sentinel** | 0.000000 [0.000000, 0.000000] | **0.0333** [0.0000, 0.1000] | Percentile compression tie artifact |
| Basis (c): Stored Percentile Sweep ($\text{FPR} \le 1.0\%$) | Dense Autoencoder | 0.006667 [0.005700, 0.007600] | **0.0000** [0.0000, 0.0000] | Collapsed (min non-zero test FPR is 7.14%) |
| Basis (c): Stored Percentile Sweep ($\text{FPR} \le 1.0\%$) | Transformer | 0.007467 [0.006400, 0.008500] | **0.0000** [0.0000, 0.0000] | Collapsed (min non-zero test FPR is 7.14%) |
| Basis (c): Stored Percentile Sweep ($\text{FPR} \le 1.0\%$) | LSTM | 0.007900 [0.006700, 0.009100] | **0.0000** [0.0000, 0.0000] | Collapsed (min non-zero test FPR is 7.14%) |

*Note on Basis (c) & Manuscript Inclusion*:
Basis (c) is documented here strictly for diagnostic traceability to explain why draft v1 sweeps reported 0.0333 (19/20 seeds collapsed to 0.0 and 1 seed returned 0.6667 due to weak-inequality percentile tie compression at the 0.50 causal floor). As mandated by [`docs/matched_fpr_reconciliation.md`](file:///e:/MCP-Runtime-Sentinel-main%20%281%29%20%282%29/MCP-Runtime-Sentinel-main/docs/matched_fpr_reconciliation.md), this artifactual 0.0333 number is **excluded from the manuscript**. The paper reports the verified Basis (a) validation-calibrated operating point (Sentinel recall 0.6667, observed FPR 0.00286%) and Basis (b) continuous raw-score sweep (Sentinel 0.6667 vs. neural baselines 0.5000 at $\text{FPR} \le 1.0\%$).

---

## 5. Table 5: Matched Poisoning Study (20 Seeds, 700 Cells)

**Protocol**:
- 5 attacker streams (`clean`, `colluding`, `late_sparse`, `mixed`, `single_identity`)
- 7 learning policies (`delayed_oracle`, `frozen`, `gated`, `immediate`, `mistaken_review`, `oracle_review`, `withheld`)
- 20 seeds (31001–31020) = 700 execution cells.
- **Source Scripts**: `sentinel/matched_poisoning.py`, `sentinel/matched_poisoning_stats.py`
- **Raw Artifacts**:
  - Summary: `results/adaptation/matched_poisoning_20seed/summary.json` (700 runs)
  - Report: `results/adaptation/matched_poisoning_20seed/tables_20seed.md`
  - Statistics: `results/adaptation/matched_poisoning_20seed/stats_20seed.json`

### Cell-by-Cell Traceability

| Stream | Policy | Total Updates (Mean ± Std) | Malicious Updates (Mean ± Std) | Contamination Rate | Benign Learning Delay | Raw JSON Cell Path |
|---|---|---|---|---|---|---|
| `single_identity` | `immediate` | **12.0 ± 0.00** | **12.0 ± 0.00** | **1.000** | NA (no benign events) | `stats_20seed.json` -> `[stream=single_identity, policy=immediate]` |
| `single_identity` | `gated` (Sentinel) | **0.0 ± 0.00** | **0.0 ± 0.00** | **0.000** | NA (no benign events) | `stats_20seed.json` -> `[stream=single_identity, policy=gated]` |
| `colluding` | `gated` (Sentinel) | **12.0 ± 0.00** | **12.0 ± 0.00** | **1.000** | NA (no benign events) | `stats_20seed.json` -> `[stream=colluding, policy=gated]` |
| `mixed` | `gated` (Sentinel) | **12.0 ± 0.00** | **4.0 ± 0.00** | **0.333** | 2.0 steps | `stats_20seed.json` -> `[stream=mixed, policy=gated]` |
| `late_sparse` | `gated` (Sentinel) | **12.0 ± 0.00** | **3.0 ± 0.00** | **0.250** | 2.0 steps | `stats_20seed.json` -> `[stream=late_sparse, policy=gated]` |
| `clean` | `gated` (Sentinel) | **12.0 ± 0.00** | **0.0 ± 0.00** | **0.000** | 2.0 steps | `stats_20seed.json` -> `[stream=clean, policy=gated]` |
| `clean` | `frozen` | **0.0 ± 0.00** | **0.0 ± 0.00** | **0.000** | Censored (20/20) | `stats_20seed.json` -> `[stream=clean, policy=frozen]` |

### Transactional Parity
- **Ineligible Stale/Replay Challenges**: 0/6 under both transactional and adaptive setups.
- **Eligible Claims**: 0/2 under both setups.
- **Algorithmic Advantage**: Exactly zero ($0.0000$). Documented in `docs/learning_admission_prototype.md` and `docs/claims_audit.md`.

---

## 6. Table 6: Gateway Runtime Performance & Overhead

**Source Scripts**: `sentinel/gateway_benchmark.py`, `sentinel/plots.py`
**Raw Artifacts**: `results/figures_20seed/gateway_latency.svg`

| Metric | Measured Latency | Standard Error | Description | Raw Key |
|---|---|---|---|---|
| **Direct Mock Server Latency** | **0.42 ms** | $\pm 0.03\text{ ms}$ | Direct loopback call to mock arithmetic MCP server without intermediary | `direct_mean_ms` |
| **Sentinel Gateway Latency** | **1.25 ms** | $\pm 0.08\text{ ms}$ | End-to-end HTTP reverse proxy call with parsing, intent check, autoencoder inference, and profile update | `gateway_mean_ms` |
| **Sentinel Proxy Overhead** | **0.83 ms** | $\pm 0.08\text{ ms}$ | Net proxy inspection latency introduced by Sentinel gateway | `proxy_overhead_ms` |

---

## 7. Regenerating This Document

To verify that all numbers in this document match current disk artifacts:
```bash
python scripts/reproduce_all.py --verify-only
```
If any checksum or metric diverges, the script immediately exits with a non-zero code.
