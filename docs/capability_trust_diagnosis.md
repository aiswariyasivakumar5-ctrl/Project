# Capability Trust Diagnosis: Root Cause, Absorbing State, and Empirical Evidence

**Date:** 2026-10-25  
**Evaluation Script:** [`scripts/diagnose_capability_trust.py`](../scripts/diagnose_capability_trust.py)  
**Historical Evidence:** [`results/novelty/publication_scale_complete/`](../results/novelty/publication_scale_complete/)

---

## 1. Verified Root Cause Chain

In the publication-scale novelty experiments, the `full` variant exhibited a catastrophic **1.0000 false positive rate (FPR)** across 6 test scenarios (`coordinated_servers`, `delayed_causal_misuse`, `provenance_replay`, `capability_laundering`, `schema_stable_response`, and `legitimate_upgrade`), performing drastically worse than the unaugmented `baseline` (which maintained 0.0000 FPR on the first three scenarios and `legitimate_upgrade`).

Empirical profiling reveals a 3-part causal failure chain:

### (a) Upstream Benign Record ID Collision in `normal_workload`
- In [`sentinel/workload.py`](../sentinel/workload.py), `normal_workload()` generates synthetic calls against both `local-test-mcp` (primary, weight 0.75) and `secondary-test-mcp` (secondary, weight 0.25).
- Both servers draw record IDs from a narrow shared range: `record-{1000..1020}`.
- Because sessions multiplex multiple tool invocations within the same session ID (`novelty-train-session-{index % session_count}`), when `secondary-test-mcp` invokes `safe_read({"record_id": "record-1005"})` after `local-test-mcp` has previously returned `record:record-1005` in that session, the temporal causal graph ([`sentinel/causal.py`](../sentinel/causal.py)) detects string token overlap (`record`, `1005`).
- The causal engine classifies this as an unexplained `cross_server_data_flow`, raising causal risk to $\ge 0.60$, which triggers the engine's causal hard floor:
  $$\text{risk} = \max(\text{risk}, 0.50)$$
- **Impact:** Approximately **7.0% to 8.5%** of entirely benign training events receive a risk score of exactly 0.50 (in the `CONFIRM` band, $\ge 0.45$).

### (b) CapabilityTrustController Absorbing State
- In [`sentinel/novelty.py`](../sentinel/novelty.py), `CapabilityTrustController.decide()` manages per-(server, tool) trust:
  $$\text{effective} = \max(\text{risk}, 1 - \text{trust}, \dots)$$
- On `Action.ALLOW` ($\text{effective} < 0.45$), trust increments slightly:
  $$\text{trust} \leftarrow \min(1.0, \text{trust} + 0.006 \times (1 - \text{risk}))$$
- On any non-ALLOW action (`CONFIRM`, `SANDBOX`, `ISOLATE`), trust is penalized:
  $$\text{trust} \leftarrow \max(0.0, \text{trust} - 0.05 - 0.10 \times \text{risk})$$
- When a spurious causal alarm assigns $\text{risk} = 0.50$, trust decreases by $0.05 + 0.10(0.50) = 0.10$.
- Starting from baseline trust $0.75$, two or three spurious alarms drop trust below $0.55$.
- **The Absorbing Trap:** As soon as $\text{trust} < 0.55$, $1 - \text{trust} > 0.45$. Because $\text{effective} = \max(\text{risk}, 1 - \text{trust})$, `effective` is strictly $> 0.45$ for **every subsequent event**, even when the incoming event has $\text{risk} = 0.00$.
- Consequently, `SentinelEngine._action(effective)` can **never return `ALLOW` again**.
- Because trust is incremented only when `action == Action.ALLOW`, trust is structurally prevented from recovering. Every future call is permanently restricted, and any subsequent causal ping continues to drive trust down to 0.00.
- The reviewed recovery path (`begin_recovery` / `evaluate_recovery`) was intended for manual operator intervention after security incidents, and is never exercised by the automated benchmark runner during training/testing.

### (c) Collapse of Downstream Encodings & Validation Calibration
- During normal training, `secondary-test-mcp:safe_read` trust collapses from $0.75$ to **$0.0879$**.
- At checkpoint time, the saved state has `safe_read` permanently restricted.
- In validation, **82.5% to 87.0%** of benign calls are blocked (`CONFIRM`/`SANDBOX`/`ISOLATE`).
- In held-out test scenarios, every benign call to `safe_read` is blocked, resulting in **FPR = 1.0000**.
- Calibrated score thresholds sit at 0.82+, and the risk score becomes completely uninformative ($\text{AUROC} \approx 0.497$).

---

## 2. Empirical Verification Results

Ran [`scripts/diagnose_capability_trust.py`](../scripts/diagnose_capability_trust.py) on seed 42 ($N_{\text{train}}=200$, $N_{\text{val}}=80$):

| Variant | Spurious Causal Train Events ($\ge 0.50$) | Train Interventions | `safe_read` Trust After Train (Primary / Secondary) | Validation FPR |
|---|:---:|:---:|:---:|:---:|
| `baseline` | 17 / 200 (8.5%) | 17 / 200 | N/A (untracked) | **0.0500** |
| `without_capability_trust` | 17 / 200 (8.5%) | 20 / 200 | N/A (disabled) | **0.0500** |
| `full` | 14 / 200 (7.0%) | **50 / 200** | 0.3214 / **0.0879** | **0.8250** |

### Test Scenario FPR Degradation (Seed 42)

| Test Scenario | `baseline` FPR | `without_capability_trust` FPR | `full` FPR (Degraded) |
|---|:---:|:---:|:---:|
| `coordinated_servers` | 0.0000 | 0.0000 | **1.0000** |
| `delayed_causal_misuse` | 0.0000 | 0.0000 | **1.0000** |
| `provenance_replay` | 0.0000 | 0.0000 | **1.0000** |
| `capability_laundering` | 0.0000 | 0.1667 | **1.0000** |
| `schema_stable_response` | 0.0000 | 0.1667 | **1.0000** |
| `legitimate_upgrade` | 0.0000 | 0.0000 | **1.0000** |

---

## 3. Retained Historical Baseline (`results/novelty/publication_scale_complete`)

Mean FPR across all 5 evaluation seeds (`42, 123, 456, 789, 1001`, $N_{\text{train}}=5{,}000$, $N_{\text{val}}=1{,}000$, $N_{\text{test}}=3{,}000$):

| Scenario | `baseline` Mean FPR | `without_capability_trust` Mean FPR | `full` Mean FPR |
|---|:---:|:---:|:---:|
| `coordinated_servers` | 0.0000 | 0.2000 | **1.0000** |
| `delayed_causal_misuse` | 0.0000 | 0.2000 | **1.0000** |
| `provenance_replay` | 0.0000 | 0.2000 | **1.0000** |
| `capability_laundering` | 0.9953 | 0.9969 | **1.0000** |
| `schema_stable_response` | 0.9947 | 0.9967 | **1.0000** |
| `legitimate_upgrade` | 0.0000 | 0.4000 | **1.0000** |

---

## 4. Remediation Plan (Phases B & C)

1. **Autonomous Bounded Recovery:** In [`sentinel/novelty.py`](../sentinel/novelty.py), decouple historical trust from immediate event health. When an incoming event has intrinsic $\text{risk} < 0.45$ (benign ALLOW band), permit slow, bounded trust replenishment even if the historical trust held the gateway decision in `CONFIRM`.
2. **Corroborated Trust Penalization:** Do not penalize capability trust on an isolated causal hard-floor flag ($0.50$) without corroboration from another orthogonal detector signal (behavioral autoencoder, intent mismatch, sequence, attestation) or persistent multi-event causal violations.
3. **Trust Floor Against Unreviewed Isolation:** Bound the unreviewed degradation floor (e.g. $\text{trust} \ge 0.40$ or $0.50$ for purely causal noise), ensuring false alarms cannot unilaterally drive a capability into permanent `ISOLATE` without human or multi-identity review.
4. **Value-Provenance Origin for Causal Graph (Phase C):** Add an optional mode `causal_requires_response_origin` in [`sentinel/causal.py`](../sentinel/causal.py) ensuring string tokens matched in downstream arguments were actually emitted as values by a prior tool response rather than matching an arbitrary record identifier from a synthetic pool.
