# Zero-Recall Attack Families: Root Cause and Principled Evaluation Analysis

## Executive Summary

In the headline baseline comparison, Full Sentinel exhibits high overall precision (0.9998) and recall of 1.0000 across 8 primary attack families, but achieves **0.0000 held-out recall** across four specific attack families:
1. **Capability drift** (`0.0000`)
2. **Low-and-slow parameter scaling** (`0.0000`)
3. **Gradual parameter poisoning** (`0.0000`)
4. **Abnormal tool sequence** (`0.0000`)

This document provides the mathematical, structural, and empirical root cause analysis for each failure mode, documents principled improvements evaluated, and justifies why remaining limitations must be transparently reported in the Springer LNCS publication.

---

## 1. Capability Drift

### Root Cause
1. **Unenrolled Baselines**: In `sentinel/engine.py`, capability change detection relies on `event.capability_digest != self.attestation.enrolled[event.server_id]`. During standard offline training (`trusted_enrollment=True`), the attestation manager was not passed the initial capability digest (`self.attestation.enroll`), leaving the enrolled map empty.
2. **Linear Weight Cap**: In the Sentinel multi-signal fusion equation:
   $$\text{risk} = 0.34 \cdot \text{behavior} + 0.20 \cdot \text{intent} + 0.10 \cdot \text{sequence} + 0.16 \cdot \text{causal} + 0.08 \cdot \text{impact} + 0.05 \cdot \text{failure} + \mathbf{0.07 \cdot \text{attestation}}$$
   Attestation risk has a fixed weight coefficient of $0.07$. Even with attestation enrollment active and `capability_changed = True` ($\text{attestation\_risk} = 1.0$), the maximum contribution to risk is only $0.07$. For pure capability modifications where the invoked tool (`safe_read`) and intent are otherwise normal, total risk is bounded at:
   $$\text{risk} \approx 0.15 \text{ (behavior)} + 0.02 \text{ (impact)} + 0.07 \text{ (attestation)} = 0.24 \ll 0.50 \text{ (decision threshold)}$$

### Principled Improvement Evaluated
- Enforcing enrollment during trusted training.
- Treating unauthorized capability changes as an architectural violation rather than an additive linear term (similar to provenance violations), setting an attestation floor $\text{risk} = \max(\text{risk}, 0.70)$.
- **Empirical Impact**:
  - `capability_drift` recall jumps from **0.0000 to 1.0000**.
  - Benign test FPR remains strictly unchanged at **0.0000**.

---

## 2. Low-and-Slow & Gradual Poisoning

### Root Cause
1. **Logarithmic Compression of Parameter Size**:
   Feature extraction computes $\log(1 + \text{len}(\text{arguments}))$. A gradual parameter inflation of 60 to 180 characters per request causes minute step-by-step increments ($\Delta \log \approx 0.1$ to $0.3$), which the standardizer treats as normal variance within $1\sigma$.
2. **Mathematical Fusion Upper Bound on Pure Parameter Attacks**:
   In low-and-slow and gradual poisoning, the attacker preserves benign intents (`"Read record 1001"`), invokes legitimate tools (`safe_read`), maintains normal sequence structure, causes no execution failure, and induces no causal loop. Consequently:
   $$\text{intent} = 0, \quad \text{sequence} = 0, \quad \text{causal} = 0, \quad \text{failure} = 0, \quad \text{attestation} = 0$$
   The maximum possible risk that Sentinel can output—even under an infinite behavioral autoencoder anomaly ($\text{behavior} = 1.0$)—is:
   $$\text{risk}_{\max} = 0.34 \times 1.0 + 0.08 \times 0.25 = 0.34 + 0.02 = \mathbf{0.3600}$$
   Because the calibrated decision threshold is **0.5000**, it is mathematically impossible for Sentinel's linear fusion formula to flag any attack that only manipulates parameter dimensions without triggering a secondary channel.

### Principled Improvements & Security Tradeoff Analysis
1. **Behavior Floor / Elevation**:
   Setting a floor when autoencoder anomaly $\text{behavior} \ge 0.85$ ($\text{risk} = \max(\text{risk}, 0.55)$):
   - Recall on `low_and_slow` increases from **0.0000 to 0.4720**.
   - **Severe Tradeoff**: Benign test false positive rate (FPR) immediately degrades from **0.0000 to 0.0714 (7.14%)**.
   - Under enterprise MCP operation, a 7.14% false alarm rate on benign tool execution is unacceptable and violates Sentinel's core design requirement of sub-0.1% FPR.
2. **CUSUM / Cumulative Residual Scoring**:
   Accumulating reconstruction error residuals over a sliding window detects the monotonic ramp, but requires persistent session state. Under stateless or rotating sessions, the cumulative state resets.

---

## 3. Abnormal Sequence

### Root Cause
1. **Session-Local Markov Transitions**:
   `SequenceModel` maintains transition counters partitioned strictly per session: `self.transitions[session_id]`.
2. **High Normal Marginal Frequency of Transition**:
   In `normal_workload`, benign traffic consists of `safe_read` (80%) and `calculate` (20%). Out of 5,000 normal training events, the bigram transition `(safe_read, calculate)` occurs 701 times (representing 17.8% of all transitions following `safe_read`).
3. **Session Smoothing**:
   When an attack session begins with an anchor read and transitions to calculate, Laplace smoothing on the new session produces an anomaly score of $0.50$. In fusion, $0.10 \times 0.50 = 0.05$, leaving overall risk at $\approx 0.15 \ll 0.50$.
4. **Why Complex Baselines Succeed**:
   The LSTM and Transformer baselines condition on full historical window contexts (length $L=10$), allowing them to detect long-range sequence context where a simple bigram model lacks statistical state. However, they suffer roughly 7.9% FPR.

---

## 4. Methodological Conclusion & Publication Treatment

In adherence to non-negotiable research integrity guidelines:
1. **Negative & Null Results Retained**: The architectural upper bound ($0.36 < 0.50$) on single-channel behavioral anomalies explains why pure parameter stealth attacks require high FPR to detect under fixed linear fusion.
2. **Paper Limitations Section**: The four families are explicitly reported in the master per-attack evaluation table and documented in `docs/final_limitations.md`.
3. **Future Work**: Higher-order sequence modeling with hierarchical transition priors and dynamic, context-aware fusion weights are proposed for future work.
