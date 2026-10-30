# Calibration Tie Handling and Causal Hard Floor Analysis

## 1. Problem Description

In Sentinel's risk evaluation architecture, when causal propagation risk is detected ($\text{causal\_risk} \ge 0.60$), the engine enforces a discrete causal risk floor:
```python
if causal_risk >= 0.60:
    risk = max(risk, 0.50)
```
On the standard benign validation split ($N = 1,000$ normal events), 107 events (10.7%) experience this floor. Because the operation uses `max(risk, 0.50)`, it collapses continuous risk scores into a discrete probability mass at exactly $0.500000$.

The resulting empirical validation distribution exhibits a severe tie plateau:
- 701 events at $0.153333$
- 148 events at $0.078579$
- **107 events tied at $0.500000$** (representing the top 10.7% of benign validation scores)
- Maximum score across all benign validation events is exactly $0.500000$.

When calibrating a high-quantile decision threshold targeting $\alpha = 0.01$ (the 99th percentile, $q = 0.99$):
The 99th percentile index falls at position 990, directly inside the tied block of 107 scores at $0.500000$.

---

## 2. Decision Rule Ambiguity & Failure Modes

Under tied quantile conditions, decision semantics dictate operational outcomes:

| Convention | Operator | Empirical Benign Validation FPR | Test Attack Recall | Security Assessment |
|---|:---:|:---:|:---:|---|
| **Non-Strict Inequality** | $\text{score} \ge T$ | **10.70%** (107 / 1,000) | 66.67% | **Severe Budget Violation**: FPR explodes to $>10\times$ the 1% target budget. |
| **Strict Inequality** | $\text{score} > T$ | **0.00%** (0 / 1,000) | 66.67% | **Budget Preserved**: Zero false alarms on validation, maintaining high precision. |

---

## 3. Deterministic Tie-Handling Rule

To eliminate ambiguity across experiments and deployments, Sentinel defines a deterministic tie-handling specification in `sentinel/compare.py`:

```python
def calibrate_threshold(validation_scores: np.ndarray, false_positive_rate: float = 0.01) -> float:
    """Calibrate decision threshold on validation scores targeting false_positive_rate.

    Deterministic Tie-Handling Rule:
    When score distributions contain tied values (such as discrete causal or policy floors),
    standard quantile interpolation is ambiguous. Under the strict decision rule (score > threshold),
    this function selects the threshold T using the right-continuous upper quantile (method='higher').
    
    If multiple scores are tied at T (e.g. the causal floor at 0.50):
      1. Strict comparison (score > T) is enforced, guaranteeing that the empirical validation
         false positive rate strictly respects the budget: P(score > T) <= false_positive_rate.
      2. If non-strict comparison (score >= T) were used, the tie mass would cause an FPR spike.
         Therefore, threshold semantics are strictly defined as score > T.
    """
```

### Mathematical Guarantee
Let benign validation scores be $S = \{s_1, s_2, \dots, s_N\}$. The threshold $T$ is chosen as the right-continuous quantile $S_{\lceil (1-\alpha)(N-1) \rceil}$. Under strict decision semantics:
$$\text{FPR}(T) = \frac{1}{N} \sum_{i=1}^N \mathbf{1}(s_i > T) \le \alpha$$
When $T = 0.50$, $P(S > 0.50) = 0.000 \le 0.01$, strictly respecting the target false positive budget.

---

## 4. Before / After Validation Calibration Results

Calibrated on benign validation data ($N=1,000$) across 5 research seeds:

| Seed | Model | Before Threshold | Before FPR ($>T$) | After Deterministic Threshold | After Strict Validation FPR | After Non-Strict FPR ($\ge T$) |
|:---:|---|:---:|:---:|:---:|:---:|:---:|
| **42** | Sentinel | 0.500000 | 0.0000 | 0.500000 | 0.0000 | 0.1070 |
| **123** | Sentinel | 0.500000 | 0.0000 | 0.500000 | 0.0000 | 0.1070 |
| **456** | Sentinel | 0.500000 | 0.0000 | 0.500000 | 0.0000 | 0.1070 |
| **789** | Sentinel | 0.500000 | 0.0000 | 0.500000 | 0.0000 | 0.1070 |
| **1001** | Sentinel | 0.500000 | 0.0000 | 0.500000 | 0.0000 | 0.1070 |

The deterministic rule is formally integrated into `sentinel/compare.py` and validated by regression tests in `tests/test_validation_calibration.py`.
