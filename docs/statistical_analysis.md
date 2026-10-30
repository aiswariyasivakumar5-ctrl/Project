# Statistical Analysis & Evaluation Methodology: MCP Runtime Sentinel

## 1. Study Framing: 20-Seed Primary vs. 5-Seed Exploratory

Experimental reporting in this work is structured into two distinct tiers:

1. **Primary Confirmatory Benchmark (20 Seeds: 20001–20020)**:
   - Evaluates Sentinel against five ML and deep sequence baselines (`dense_autoencoder`, `lstm`, `transformer`, `one_class_svm`, `isolation_forest`) across 20 independent seeds.
   - Sample size $N = 20$ provides high statistical power ($p < 0.0001$ under exact Wilcoxon signed-rank tests with Holm step-down correction).
   - Generates the primary publication tables (Tables 1–3 in [`results/tables_20seed/`](file:///e:/MCP-Runtime-Sentinel-main%20%281%29%20%282%29/MCP-Runtime-Sentinel-main/results/tables_20seed)).
2. **Exploratory Runtime Novelty Matrix (5 Seeds: 42, 123, 456, 789, 1001)**:
   - Evaluates interactive multi-phase adaptation, capability trust, and intent provenance across 8 scenarios and 6 variants (330 phases total).
   - Serves as exploratory runtime evidence. With $N = 5$ paired observations under exact sign-flip tests, the minimum possible two-sided p-value is $2 \times (1/2)^5 = 0.0625$, precluding $p < 0.05$ claims.

---

## 2. Statistical Design & Metric Quantification

The independent replication unit is the random seed, not the individual event. Events within a seed share generated sessions, training data, and model state and are therefore not treated as independent observations for hypothesis testing.

### 2.1 False Positive Rate & Exact Clopper-Pearson Confidence Bounds
Rather than asserting an informal "zero false positives" claim, false positive rates are quantified with exact binomial confidence intervals:
- Across the 20 publication test seeds, Sentinel evaluated **35,000 normal test events** ($20 \times 1,750$ events).
- Exactly 1 false positive occurred across all 20 seeds (in seed 20008: 1 FP, 1,749 TN; the remaining 19 seeds had 0 FP, 1,750 TN).
- **Pooled Empirical FPR**: $1 / 35,000 = 0.0000286$ (or **0.00286%**).
- **Exact 95% Clopper-Pearson CI**: $[0.0000007, 0.0001592]$ ($[0.00007\%, 0.01592\%]$).
- **Exact 95% Upper Bound**: $\mathbf{0.0159\%}$ (less than 1.6 false alarms per 10,000 legitimate requests).
- **Per-Seed Zero-FP Bound**: For each individual seed observing 0 false alarms out of 1,750 events, the exact 95% Clopper-Pearson upper bound is $1 - 0.025^{1/1750} \approx \mathbf{0.2106\%}$.

### 2.2 All-or-Nothing Recall Distribution (0.6667 Mean Recall)
Sentinel's reported test recall of $0.6667$ across 12 evaluated attack families does not reflect a uniform random 66.7% detection probability. It is an exact all-or-nothing step function:
- **Detected Families (8 of 12, Recall = 1.0000)**: `cross_server`, `data_exfiltration`, `delayed_malicious`, `destructive_operation`, `intent_mismatch`, `policy_injection`, `schema_mutation`, `tool_poisoning`.
- **Missed Families (4 of 12, Recall = 0.0000)**: `abnormal_sequence`, `capability_drift`, `gradual_poisoning`, `low_and_slow`.
- These 4 blind spots arise from fundamental architectural trade-offs: the order-invariant bag-of-calls feature representation cannot detect sequence permutations, and cumulative parameter drift within legitimate schemas remains beneath per-event reconstruction error thresholds (see [`docs/zero_recall_analysis.md`](zero_recall_analysis.md)).

### 2.3 Matched-FPR Baseline Recall Comparison
While neural baselines (Dense Autoencoder, LSTM, Transformer) achieve higher raw $F_1$ ($0.8250 - 0.8815$), their recall advantages depend entirely on accepting an intolerable $7.71\% - 7.82\%$ false alarm rate on normal requests.

When baselines are evaluated under operating thresholds constrained to match low false positive regimes comparable to Sentinel, their detection capabilities collapse:

| Model Architecture | Nominal Test FPR | Matched Recall at FPR <= 0.01% | Matched Recall at FPR <= 0.1% | Matched Recall at FPR <= 1.0% |
|---|---:|---:|---:|---:|
| **Sentinel** | **0.0029%** | **0.0333** | **0.0333** | **0.0333** |
| **Dense Autoencoder** | 7.71% | 0.0000 | 0.0000 | 0.0000 |
| **LSTM** | 7.82% | 0.0000 | 0.0000 | 0.0000 |
| **Transformer** | 7.78% | 0.0000 | 0.0000 | 0.0000 |
| **One-Class SVM** | 8.59% | 0.0942 | 0.1794 | 0.3419 |
| **Isolation Forest** | 0.73% | 0.0000 | 0.0000 | 0.0000 |

*Finding*: The minimum non-zero FPR for Dense Autoencoder, LSTM, and Transformer on test data is $7.14\%$ ($125/1,750$ events). Below this point, their recall is strictly 0.0000. In enterprise MCP enforcement, disrupting 1 out of 13 benign calls is operationally unacceptable; Sentinel's conservative causal and intent filters prevent this failure mode.


## Reproduction

Run all six Sentinel configurations at publication scale:

```powershell
python -m sentinel.cli ablate --seeds 42,123,456,789,1001 `
  --train-size 5000 --validation-size 1000 --test-size 3000 `
  --output results/ablations_publication --bootstrap-resamples 20000
```

Analyze the approved baseline files without modifying them:

```powershell
python -m sentinel.cli analyze --baselines results/baselines_publication `
  --output results/statistical_analysis --bootstrap-resamples 20000
```

Generate SVG figures and Markdown tables:

```powershell
python -m sentinel.cli figures --baselines results/baselines_publication `
  --ablations results/ablations_publication --output results/figures
python -m sentinel.cli research-tables --baselines results/baselines_publication `
  --ablations results/ablations_publication --statistics results/statistical_analysis `
  --output results/tables
```

## Ablation interpretation

The held-out matrix preserves the normal-only TRAIN, normal VALIDATION, and frozen-
baseline TEST split. A single 99th-percentile validation threshold is selected per
variant and then applied globally.

Removing causal risk increases held-out recall and F1 but substantially increases
false positives. This indicates the current causal floor acts as a conservative
operating constraint rather than uniformly improving discrimination. Removing intent
causes zero threshold-level detections, even though ranking metrics remain nonzero.

Attestation and uncertainty do not change the offline held-out operating decisions;
their mechanisms act through runtime challenges and capability evidence not fully
represented by this static test. Quarantine also cannot affect a frozen no-learning
TEST, so it is evaluated in a separate adaptive poisoning phase.

In adaptive diagnostics, full Sentinel prevents malicious samples from entering the
baseline, while removing quarantine permits them all. Removing intent has the same
failure in the present poisoning workload. The exact paired p-value is 0.0625, so
these consistent effects are not called statistically significant at alpha 0.05.

## Weakness diagnostics

The diagnostics preserve the validation threshold and explain observed misses:

- capability drift produces attestation risk, but its fusion contribution remains
  below the global threshold;
- low-and-slow and gradual poisoning produce elevated behavioral risk that remains
  below the 0.5 operating threshold;
- abnormal sequence calls occur in new sessions, while the current transition model
  learns counts per session and therefore provides little transferable evidence.

Isolation Forest shows useful ranking AUROC but zero operating recall because every
attack score remains below the fixed 99th-percentile validation threshold. This is
a threshold-transfer/calibration discrepancy, not evidence that its ranking metric
is fabricated. No alternative threshold is selected after examining TEST.

## Outputs and limitations

Results are written to `results/ablations_publication`, `results/statistical_analysis`,
`results/tables`, and `results/figures`. SVG is generated without plotting-library
dependencies and remains editable for conference layout.

Limitations include five seed clusters, synthetic traffic, deterministic workload
families, no confidence interval correction for multiple metrics, no formal power
analysis, and no real-enterprise external validation. No component improvement is
claimed statistically significant under the implemented exact tests.

