# Baseline Snapshot

**Date recorded:** 2026-10-25
**Test suite status:** 261 tests passed in 101.082s (`python -m unittest discover -s tests`).
**Ground-truth claims audit:** Treated according to `docs/claims_audit.md` and `docs/final_limitations.md`.
**Workload context:** All data is synthetic; safe mock MCP servers; 5 research seeds (`42, 123, 456, 789, 1001`).

---

## 1. Headline Model Comparison

*Source file:* `results/final/master_model_comparison.md` (derived from `results/baselines_publication` and `results/baselines_sequence`)
*Protocol:* Normal-only TRAIN=5,000, normal VALIDATION=1,000, TEST=3,000. Decisions use validation-only p99 threshold. Values are mean ± sample standard deviation across 5 seeds.

| Model | F1 | Precision | Recall | FPR | AUROC | AUPRC | Detection Delay (events) | Offline Inference (ms/event) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **sentinel** | 0.7999 ± 0.0001 | 0.9998 ± 0.0004 | 0.6667 ± 0.0000 | 0.0001 ± 0.0003 | 0.8357 ± 0.0122 | 0.8230 ± 0.0140 | 0.0 ± 0.0 | 0.1166 ± 0.0079 |
| **isolation_forest** | 0.0000 ± 0.0000 | 0.0000 ± 0.0000 | 0.0000 ± 0.0000 | 0.0071 ± 0.0030 | 0.8899 ± 0.0180 | 0.7780 ± 0.0444 | — | 0.0870 ± 0.0095 |
| **one_class_svm** | 0.6103 ± 0.1959 | 0.8139 ± 0.1217 | 0.5296 ± 0.2431 | 0.1119 ± 0.0631 | 0.8522 ± 0.0658 | 0.8299 ± 0.0899 | 150.0 ± 205.4 | 0.0019 ± 0.0003 |
| **dense_autoencoder** | 0.8944 ± 0.0243 | 0.9063 ± 0.0024 | 0.8837 ± 0.0447 | 0.0783 ± 0.0025 | 0.9043 ± 0.0033 | 0.8878 ± 0.0026 | 0.0 ± 0.0 | 0.0006 ± 0.0000 |
| **lstm** | 0.8268 ± 0.0087 | 0.8929 ± 0.0026 | 0.7700 ± 0.0155 | 0.0792 ± 0.0031 | 0.9164 ± 0.0024 | 0.8870 ± 0.0022 | 0.0 ± 0.0 | 0.0111 ± 0.0013 |
| **transformer** | 0.8345 ± 0.0121 | 0.8950 ± 0.0032 | 0.7819 ± 0.0208 | 0.0786 ± 0.0034 | 0.9125 ± 0.0038 | 0.8865 ± 0.0021 | 0.0 ± 0.0 | 0.0167 ± 0.0008 |

---

## 2. Per-Attack Recall

*Source file:* `results/final/master_per_attack.md` (derived from `results/baselines_publication/*/per_seed`, `results/baselines_sequence/*/per_seed`, `results/sequence_publication/sequence_analysis.json`)
*Values:* Mean held-out recall across 5 seeds.

| Attack Family / Scenario | Sentinel | Isolation Forest | One-Class SVM | Dense AE | LSTM | Transformer |
|---|---:|---:|---:|---:|---:|---:|
| **Capability drift** | 0.000 | 0.000 | 0.298 | 0.683 | 0.000 | 0.000 |
| **Low-and-slow** | 0.000 | 0.000 | 0.464 | 0.928 | 0.565 | 0.640 |
| **Gradual poisoning (frozen TEST)** | 0.000 | 0.000 | 0.430 | 0.994 | 0.675 | 0.742 |
| **Abnormal sequence** | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| **Cross-server flow** | 1.000 | 0.000 | 0.800 | 1.000 | 1.000 | 1.000 |
| **Data exfiltration** | 1.000 | 0.000 | 0.459 | 1.000 | 1.000 | 1.000 |
| **Destructive operation** | 1.000 | 0.000 | 0.600 | 1.000 | 1.000 | 1.000 |
| **Intent mismatch** | 1.000 | 0.000 | 0.600 | 1.000 | 1.000 | 1.000 |
| **Policy injection** | 1.000 | 0.000 | 0.600 | 1.000 | 1.000 | 1.000 |
| **Schema mutation** | 1.000 | 0.000 | 0.600 | 1.000 | 1.000 | 1.000 |
| **Tool poisoning** | 1.000 | 0.000 | 0.800 | 1.000 | 1.000 | 1.000 |
| **Delayed malicious behavior** | 1.000 | 0.000 | 0.704 | 1.000 | 1.000 | 1.000 |

*Zero-recall families for Sentinel:* Capability drift (0.000), Low-and-slow (0.000), Gradual poisoning (0.000), Abnormal sequence (0.000).

---

## 3. Ablation Comparison

*Source file:* `results/final/master_ablation.md` (derived from `results/ablations_publication/aggregate`)

| Variant | F1 | Precision | Recall | FPR |
|---|---:|---:|---:|---:|
| **Full** | 0.7999 | 0.9998 | 0.6667 | 0.0001 |
| **Without intent** | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| **Without causal** | 0.9127 | 0.9088 | 0.9167 | 0.0789 |
| **Without attestation** | 0.7999 | 0.9998 | 0.6667 | 0.0001 |
| **Without uncertainty** | 0.7999 | 0.9998 | 0.6667 | 0.0001 |
| **Without quarantine** | 0.7999 | 0.9998 | 0.6667 | 0.0001 |

Adaptive poisoning updates:
- Malicious poisoning events updating baseline: Full (0.000) vs without quarantine (1.000), p = 0.0625.
- Malicious poisoning events updating baseline: Full (0.000) vs without intent (1.000), p = 0.0625.
- Legitimate-drift intervention: Full (0.000) vs without causal (0.126 mean), p = 0.0625.

---

## 4. Statistical Limitations Snapshot

*Source file:* `results/final/statistical_evidence.md`
- 5 research seeds (`42, 123, 456, 789, 1001`).
- Exact two-sided sign-flip p-value minimum bound with 5 nonzero pairs is `p = 0.0625` (no comparison can reach `p < 0.05`).
- Holm adjustment applied across classical baselines and ablation tests.
