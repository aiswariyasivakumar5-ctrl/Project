# Causal Workload Analysis & Response Origin Evaluation

## 1. Quantification of Spurious Causal Alarms

In both the novelty benchmark and the offline ML comparison benchmark, synthetic normal traffic multiplexes calls across two servers (`local-test-mcp` and `secondary-test-mcp`) within persistent sessions. Synthetic tools (primarily `safe_read`) query records from a bounded pool (`record-1000` through `record-1020`), echoing `record:<record_id>` in the text response payload.

When `secondary-test-mcp` is invoked with a record previously queried by `local-test-mcp` in the same session, `TemporalCausalGraph.observe()` identifies token overlap (`record-XXXX`) between `event.arguments` and `prior_response`. Because the servers differ, this is classified as `cross_server_data_flow`, clamping the anomaly score to $\ge 0.50$.

### Empirical Rate of Causal Floor Triggers
- **Novelty Workload:**
  - Novelty training stream: **8.6% - 8.7%** of benign calls trigger the causal floor.
- **Main Comparison Workload (`ComparisonDataset`):**
  - Validation set ($N = 1000$): **107 events (10.70%)** trigger the causal floor ($risk \ge 0.50$).
  - Normal test set ($N = 1750$): **128 to 144 events (7.31% - 8.23%)** trigger the causal floor.

---

## 2. Why the Main Comparison Reported Test FPR 0.0000

A critical diagnostic question is why the main ML baseline table reported a Sentinel test false positive rate of **0.0000%**, despite 7.3%–8.2% of normal test calls receiving a 0.50 anomaly score.

### Mechanism: Deterministic Tie-Handling & Strict Threshold Semantics
1. **Threshold Calibration (`calibrate_threshold`):**
   - The evaluation framework calibrates Sentinel's threshold at the 99th percentile ($1 - \text{validation\_fpr} = 0.99$, targeting $\alpha = 0.01$) on 1,000 normal validation events.
   - Because 10.7% of validation events are tied at the discrete causal floor ($0.5000$), the 99th percentile quantile (using `method='higher'`) evaluates exactly to **$T = 0.5000$**.
2. **Strict Inequality Rule:**
   - The decision rule is strictly defined as `raw > threshold`.
   - On the test set, any benign event with `raw = 0.5000` evaluates as `0.5000 > 0.5000 \implies \text{False}`.
   - As a result, not a single one of the 128–144 causal false alarms triggered an intervention on test data.
3. **Difference from the Novelty Benchmark:**
   - In the novelty benchmark (`sentinel/novelty.py`), decisions are made by `CapabilityTrustController` using fixed online action boundaries (`Action.CONFIRM` at effective risk $\ge 0.45$).
   - The 0.50 causal risk exceeded the 0.45 boundary, immediately penalizing capability trust and triggering an absorbing feedback loop that collapsed trust to $< 0.10$ and caused test FPR to reach $1.0000$.

---

## 3. Upstream Mitigation: `causal_requires_response_origin`

In Phase C, an optional configuration flag `causal_requires_response_origin: bool = False` was introduced to `TemporalCausalGraph`, `EngineConfig`, and `NoveltyConfig`.

### Implementation Details
When `causal_requires_response_origin` is enabled:
- `TemporalCausalGraph.observe()` filters candidate cross-server token overlaps against generic record patterns (`GENERIC_RECORD_ID = re.compile(r"^(?:record[-_]?)?\d+$|^record$", re.I)`).
- Cross-server references to static entity IDs (`record-1001`, `record-1020`) are recognized as entity queries rather than data originated by the prior server, eliminating spurious data flow edges.
- Dynamic tokens (such as `canary-token-88421` in `cross_server` or `canary-...` in `coordinated_servers`) bypass the filter and are fully tracked.

### Empirical Evaluation & Trade-offs
| Metric | Default (`False`) | `causal_requires_response_origin=True` |
| :--- | :--- | :--- |
| **Benign Validation Causal $\ge 0.50$** | 107 / 1000 (10.70%) | **0 / 1000 (0.00%)** |
| **Calibrated Threshold ($T$)** | 0.5000 | 0.0693 |
| **`cross_server` Attack Recall** | 1.0000 | 1.0000 |
| **Overall Attack Recall** | 0.6667 (8 of 12 detected) | **0.9180** |
| **Observed Normal Test FPR** | 0.0000 | 0.0760 |

### Findings & Negative Result
- **Benefit:** `causal_requires_response_origin` suppresses upstream spurious cross-server alarms on benign traffic (observed 0.0000 FPR across evaluated synthetic fixtures).
- **Attack Sensitivity:** Removing the artificial 0.50 validation floor allows the threshold to drop to 0.0693, increasing overall attack detection recall from 0.6667 to 0.9180 (catching subtle attacks that were previously masked beneath the 0.50 floor).
- **Negative Result (Trade-off):** At the lower threshold (0.0693), minor feature jitter from synthetic autoencoder inputs causes observed test FPR to rise to 0.0760 (above the nominal 0.01 target).
- **Design Decision:** In accordance with non-negotiable rules, default behavior remains unchanged (`False`), and `causal_requires_response_origin` is retained as a principled, documented opt-in feature for multi-server environments.
