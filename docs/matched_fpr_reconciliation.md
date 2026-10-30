# Matched-FPR Reconciliation: Decision Rule vs. Percentile Sweep

## 1. Executive Summary & Problem Statement

In earlier draft materials ([`results/matched_fpr/matched_fpr_comparison.md`](file:///e:/MCP-Runtime-Sentinel-main%20%281%29%20%282%29/MCP-Runtime-Sentinel-main/results/matched_fpr/matched_fpr_comparison.md)), an apparent contradiction emerged:
- **Headline Decision-Rule Performance**: Sentinel achieves **Recall = 0.6667**; pooled across 20 seeds, 1 false alarm occurred among 35,000 benign test events ($\text{FPR} = 0.0000286$, or **0.00286%**; exact Clopper--Pearson 95% upper bound **0.0159%**).
- **Draft Matched-FPR Sweep**: Reported Sentinel Recall as **0.0333** at $\text{FPR} \le 1.0\%$.

Both numbers purported to describe the same system on the same 20 seeds (20001–20020). This document presents the mathematical root cause, empirical proof, and the reconciled dual-basis evaluation framework.

---

## 2. Root Cause Analysis

### 2.1 The Validation Causal Floor & Tied Scores
In [`sentinel/compare.py`](file:///e:/MCP-Runtime-Sentinel-main%20%281%29%20%282%29/MCP-Runtime-Sentinel-main/sentinel/compare.py), Sentinel evaluates training, validation, and test splits:
- In benign normal validation traffic, approximately 10.7% of events exhibit cross-server data flow, triggering the causal analysis engine and placing an anomaly floor of exactly **0.5000**.
- The 99th percentile validation threshold ($\tau$) fitted with NumPy `method="higher"` falls directly on this discrete spike:
  $$\tau_{\text{validation}} = 0.5000000$$

### 2.2 The Percentile Compression Artifact
In [`sentinel/compare.py`](file:///e:/MCP-Runtime-Sentinel-main%20%281%29%20%282%29/MCP-Runtime-Sentinel-main/sentinel/compare.py) (lines 110 & 123), test event observations were constructed by passing validation percentile ranks into `Observation.risk`:
```python
scores = percentile_scores(validation_raw, test_raw)
observations = [Observation(row.malicious, bool(raw > threshold), float(score), ...) ...]
```
The helper function `percentile_scores` computes:
```python
def percentile_scores(validation_scores, values):
    ordered = np.sort(validation_scores)
    return np.searchsorted(ordered, values, side="right") / len(ordered)
```
Because the maximum score in benign validation traffic was `0.5000`, any test event with $\text{raw\_score} \ge 0.5000$ produced `searchsorted = len(ordered)`, assigning it `score_percentile = 1.0000`.

On the comparison test split (3,250 events per seed: 1,750 benign, 1,500 malicious):
- Exactly **175 benign test events** had causal alarms (`raw_score = 0.5000`). They received `score_percentile = 1.0000`.
- Exactly **1,000 detected attack events** had high composite anomaly scores (`raw_score >= 0.5600`). They also received `score_percentile = 1.0000`.

### 2.3 Weak Inequality in ROC Sweep (`risk >= threshold`)
In [`sentinel/metrics.py`](file:///e:/MCP-Runtime-Sentinel-main%20%281%29%20%282%29/MCP-Runtime-Sentinel-main/sentinel/metrics.py), `score_curves` sweeps over the unique values of `Observation.risk` using standard weak inequality:
```python
tp = sum(item.malicious and item.risk >= threshold for item in observations)
fp = sum(not item.malicious and item.risk >= threshold for item in observations)
```
When `score_curves` evaluated $\text{threshold} = 1.0000$:
- All items with `risk >= 1.0` were classified positive: both the 1,000 attacks AND the 175 benign events.
- This produced $\text{FP} = 175$ out of 1,750 normal events:
  $$\text{FPR} = \frac{175}{1750} = 0.1000 \quad (10.0\%)$$
- At the subsequent sweep point ($\text{threshold} = 1.0000000000000002$), zero events had `risk >= 1.0000000000000002`, yielding $\text{FPR} = 0.0, \text{TPR} = 0.0$.

Consequently, in the stored percentile ROC curve, there was a discrete discontinuity: **zero points existed between $\text{FPR} = 0.0\%$ and $\text{FPR} = 10.0\%$**.

When the initial v1 script filtered for points where $\text{FPR} \le 1.0\%$, the threshold at 1.0 was rejected ($10.0\% > 1.0\%$), leaving only the empty-selection endpoint ($\text{TPR} = 0.0$). Across 20 seeds, 19 seeds returned $0.0$ and 1 seed returned $0.6667$, producing the artificial average $\frac{1}{20} \times 0.6667 = 0.0333$.

---

## 3. The True Decision Rule Operation

In actual runtime enforcement, the decision rule is NOT a weak inequality sweep over percentile ranks. It is a strict inequality on raw scores:
$$\text{Intervene} \iff \text{raw\_score} > \tau_{\text{validation}}$$

Evaluating this rule on test data for seed 20001 (the example described in this subsection):
- For the 175 benign events with causal alarms:
  $$0.5000000 > 0.5000000 \implies \mathbf{False}$$
  None of the 175 benign events are intervened ($\text{FP} = 0$).
- For the remaining 1,575 benign events in this seed:
  $$\text{raw\_score} \le 0.4931 < 0.5000000 \implies \mathbf{False}$$
  None are intervened. This seed has **0** false positives; across all 20 seeds there is **1** false positive ($1/35{,}000$, pooled FPR $=0.0000286$).
- For the 1,000 detected attack events:
  $$\text{raw\_score} \ge 0.5600 > 0.5000000 \implies \mathbf{True}$$
  All 1,000 attacks are intervened ($\text{TP} = 1000$, $\text{Recall} = \frac{1000}{1500} = 0.6667$).

The headline recall is $0.6667$. Report the pooled empirical FPR as $0.0000286$; the single-seed example above does not imply zero false positives across the full evaluation.

---

## 4. Reconciled Dual-Basis Presentation

To ensure complete scientific transparency and fairness across all models, comparisons are published on two clearly distinguished bases:

### Basis (a): Actual Decision-Rule Operating Point
Evaluates each method under its validation-calibrated operational threshold applied held-out to test data:

| Model Architecture | Recall (Mean ± Std [95% CI]) | Test FPR (Mean ± Std [95% CI]) | F1 Score (Mean ± Std [95% CI]) | Precision |
|---|---:|---:|---:|---:|
| **Sentinel** | **0.6667 ± 0.0000** [0.6667, 0.6667] | **0.0000 ± 0.0001** [0.0000, 0.0001] | **0.8000 ± 0.0001** [0.8000, 0.8000] | **1.0000** |
| **Dense Autoencoder** | 0.8601 ± 0.0448 [0.8406, 0.8796] | 0.0771 ± 0.0019 [0.0763, 0.0780] | 0.8815 ± 0.0258 [0.8703, 0.8928] | 0.9051 |
| **LSTM** | 0.7663 ± 0.0100 [0.7621, 0.7707] | 0.0782 ± 0.0024 [0.0771, 0.0792] | 0.8250 ± 0.0056 [0.8227, 0.8276] | 0.8936 |
| **Transformer** | 0.7869 ± 0.0163 [0.7795, 0.7937] | 0.0778 ± 0.0021 [0.0769, 0.0788] | 0.8381 ± 0.0098 [0.8336, 0.8422] | 0.8965 |
| **One-Class SVM** | 0.7364 ± 0.1755 [0.6558, 0.8118] | 0.0859 ± 0.0570 [0.0607, 0.1108] | 0.7904 ± 0.1214 [0.7339, 0.8421] | 0.8849 |
| **Isolation Forest** | 0.0000 ± 0.0000 [0.0000, 0.0000] | 0.0073 ± 0.0026 [0.0062, 0.0085] | 0.0000 ± 0.0000 [0.0000, 0.0000] | 0.0000 |

### Basis (b): Descriptive Raw-Score Threshold Sweep (Strict Inequality `score > threshold`)
This sweep selects thresholds using benign scores from the same test split. It describes test-set ROC behavior and is not an independently calibrated or deployable operating point:

| Model Architecture | Matched Recall at FPR <= 0.01% | Matched Recall at FPR <= 0.1% | Matched Recall at FPR <= 1.0% | Matched Recall at FPR <= 5.0% | Matched Recall at FPR <= 8.0% |
|---|---:|---:|---:|---:|---:|
| **Sentinel** | **0.6667** [0.6667, 0.6667] | **0.6667** [0.6667, 0.6667] | **0.6667** [0.6667, 0.6667] | **0.6667** [0.6667, 0.6667] | 0.6667 [0.6667, 0.6667] |
| **Dense Autoencoder** | 0.5000 [0.5000, 0.5000] | 0.5000 [0.5000, 0.5000] | 0.5000 [0.5000, 0.5000] | 0.5000 [0.5000, 0.5000] | 0.8780 [0.8584, 0.8959] |
| **LSTM** | 0.5000 [0.5000, 0.5000] | 0.5000 [0.5000, 0.5000] | 0.5000 [0.5000, 0.5000] | 0.5000 [0.5000, 0.5000] | 0.7767 [0.7711, 0.7830] |
| **Transformer** | 0.5000 [0.5000, 0.5000] | 0.5000 [0.5000, 0.5000] | 0.5000 [0.5000, 0.5000] | 0.5000 [0.5000, 0.5000] | 0.8025 [0.7930, 0.8157] |
| **One-Class SVM** | 0.3756 [0.2868, 0.4611] | 0.4385 [0.3381, 0.5377] | 0.5583 [0.4697, 0.6512] | 0.5834 [0.4934, 0.6750] | 0.7337 [0.6475, 0.8126] |
| **Isolation Forest** | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] | 0.1123 [0.0612, 0.1689] | 0.4375 [0.3386, 0.5398] |

---

## 5. Paper Citation Rules

1. **Primary Operational Numbers**: When discussing real runtime enforcement, cite **Basis (a)**. Sentinel operates at $\text{Recall} = 0.6667, \text{FPR} = 0.0000286 \le 0.0159\%$ (exact 95% Clopper-Pearson bound) with $F_1 = 0.8000$.
2. **Trade-Off Analysis**: When comparing against deep baselines, cite both Basis (a) and Basis (b):
   - Dense Autoencoder, LSTM, and Transformer achieve higher nominal $F_1$ ($0.8250 - 0.8815$) strictly by accepting an intolerable $7.71\% - 7.82\%$ false alarm rate on benign traffic.
   - When constrained to low false positive regimes ($\text{FPR} \le 1.0\%$), neural baseline recall drops from $\sim 0.77 - 0.86$ down to $0.5000$ (they detect only large reconstruction anomalies like tool poisoning and data exfiltration, missing intent and sequence violations).
3. **Prohibited Numbers**: Never cite the v1 draft artifact ($\text{Recall} = 0.0333$); it is an artifact of weak inequality on tied percentile bins, not a property of the underlying detector.
