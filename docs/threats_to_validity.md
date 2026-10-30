# Threats to Validity: MCP Runtime Sentinel

This document provides a formal, comprehensive analysis of the threats to validity for the empirical evaluations and architectural designs reported in the Springer LNCS paper (*AI-SEC workshop at AINA-2027*).

---

## 1. Construct Validity

Construct validity assesses whether the operationalized metrics, feature vectors, and evaluation setups accurately reflect the theoretical security properties being evaluated.

### 1.1 Order-Invariant Feature Representation & Temporal Blind Spots
- **Threat**: Sentinel operationalizes behavioral anomaly detection through a 12-dimensional feature vector combining payload sizing, token overlap, argument schema compliance, and call frequency counts.
- **Impact**: The representation is fundamentally order-invariant within a session window. Consequently, as proven in [`docs/zero_recall_analysis.md`](zero_recall_analysis.md), Sentinel achieves **0.0000 recall** on the `abnormal_sequence` scenario family where malicious behavior consists solely of permuting legitimate tool calls (e.g. `delete_file` executed before `backup_archive`).
- **Mitigation & Disclosure**: We explicitly document this structural blind spot. In production, Sentinel must be paired with sequential transition models (e.g., Markov transition baselines or sequential transformers) to cover temporal order violations.

### 1.2 Lexical Intent Alignment vs. Semantic Adversaries
- **Threat**: Intent conditioning is evaluated using token-overlap and lexical signature matching between the user prompt and requested tool metadata.
- **Impact**: Sophisticated attackers employing prompt injection or indirect instruction disguises can craft benign-sounding semantic requests that pass lexical overlap filters while triggering unintended destructive actions upstream.
- **Mitigation & Disclosure**: We implemented a dedicated semantic intent benchmark ([`sentinel/intent_benchmark.py`](file:///e:/MCP-Runtime-Sentinel-main%20%281%29%20%282%29/MCP-Runtime-Sentinel-main/sentinel/intent_benchmark.py)) and explicitly state in [`docs/claims_audit.md`](claims_audit.md) that lexical matching is a prototype proxy, not an adversarial semantic reasoning engine.

### 1.3 Tied-Score Calibration Floor
- **Threat**: Causal floor filtering clamps risk scores to fixed baselines (0.50) when causal precedence is satisfied.
- **Impact**: As detailed in [`docs/calibration_tie_handling.md`](calibration_tie_handling.md), empirical validation score distributions contain discrete probability mass spikes at 0.50, causing percentile thresholds to produce flat step-functions rather than smooth calibration curves.
- **Mitigation**: Sentinel uses conservative greater-than-or-equal inequality thresholding to preserve a strict zero-false-positive-rate guarantee.

---

## 2. Internal Validity

Internal validity examines whether experimental controls, parameter choices, and statistical procedures support the causal inferences drawn.

### 2.1 Threshold Calibration & Test Leakage Prevention
- **Threat**: Setting detection thresholds on test data artificially inflates recall and suppresses false alarms.
- **Control**: In all experiments, thresholds ($\tau$) are fitted strictly on dedicated validation splits (1,000 events/seed). Test splits (3,000 events/seed) are strictly held out until final evaluation, enforced by programmatic assertion guards (`test_used_for_threshold is False`).

### 2.2 Seed-Level Variance & Weight Initialization
- **Threat**: Non-deterministic neural weight initialization or PRNG drift can confound model comparisons.
- **Control**: In [`sentinel/engine.py`](file:///e:/MCP-Runtime-Sentinel-main%20%281%29%20%282%29/MCP-Runtime-Sentinel-main/sentinel/engine.py), all autoencoder weights and data shuffling operations are initialized using cryptographic SHA-256 digest expansion on fixed seed tuples.
- **Scale**: The main comparison was scaled to **20 independent seeds** (20001–20020), yielding $p < 0.0001$ under exact Wilcoxon signed-rank tests with Holm multiple-testing adjustments.

### 2.3 Matched Poisoning Control
- **Threat**: Variations in background traffic order could alter quarantine promotion timing.
- **Control**: The 20-seed matched poisoning study evaluates 700 cells with matched attacker sequences across 7 concurrent policies, ensuring exact cross-policy attribution.

### 2.4 In-Process Transport vs. Ephemeral Port Socket Exhaustion & HTTP Bypass Disclosure
- **Threat**: Running hundreds of publication-scale evaluation phases (each with 3,000 requests) over live loopback HTTP allocates tens of thousands of ephemeral TCP sockets, triggering Windows `TIME_WAIT` socket exhaustion and transport timeouts (`URLError: <urlopen error timed out>`).
- **Control & Verification**: To resolve socket exhaustion while preserving evaluation fidelity, later phases of v1, v2, and the 20-seed v3 evaluation matrix operate via direct in-process gateway dispatch (`in_process=True`). Pipeline equivalence is formally audited in [`tests/test_in_process_equivalence.py`](file:///e:/MCP-Runtime-Sentinel-main%20%281%29%20%282%29/MCP-Runtime-Sentinel-main/tests/test_in_process_equivalence.py), proving that in-process execution produces identical JSON-RPC parsing, feature extraction, anomaly risk, trust scoring, and intervention decisions as live HTTP socket transport.
- **HTTP Layer Bypass Disclosure**: We explicitly disclose that the 330-phase (v2) and 1,320-phase (v3) evaluation matrices bypass the HTTP layer. Consequently, they do not test HTTP connection limits, socket-level timeouts, TLS handshakes, or HTTP request body-size enforcement. Live HTTP transport limits are validated separately in dedicated test suites (`tests/test_http_limits.py`).

### 2.5 Fixture Determinism and Statistical Power Constraints (v1/v2 vs. v3)
- **Threat**: The early 5-seed novelty matrices (v1 and v2, seeds 42, 123, 456, 789, 1001) used deterministic scenario fixtures with fixed record names (`record-100X`), fixed arrival timestamps, and hardcoded latencies (20 ms). Consequently, bootstrap confidence intervals collapsed to degenerate single-point intervals `[x, x]`.
- **Power Boundary**: For exact paired sign-flip permutation tests with $N = 5$ paired observations, the minimum achievable two-sided p-value is mathematically bounded by $2 \times (1/2)^5 = 0.0625$ (and $0.25$ under Holm adjustment). Under 5 seeds, no pairwise comparison could achieve $p < 0.05$.
- **v3 Mitigation & Preregistered Power**: In v3 (`results/novelty/publication_scale_v3/`), genuine seed-driven PRNG randomization was added to scenario fixtures (arrival jitter, Gaussian latency variations, diverse record pools, and distinct actor tokens) while preserving attack semantics. Evaluating the full 6-variant x 8-scenario matrix across 20 new seeds (30001–30020; 1,320 total phase records) achieved an exact two-sided p-value floor of $1.91 \times 10^{-6}$, confirming statistical significance ($p < 0.0001$, Holm $p < 0.0001$) for capability isolation and single-actor poisoning, while honestly reporting null results for intent consistency and review requirements.

---

## 3. External Validity

External validity evaluates the degree to which findings generalize to real-world systems, diverse MCP implementations, and production workloads.

### 3.1 Exclusively Synthetic Workloads
- **Threat**: The evaluation uses synthetic mock MCP servers (arithmetic services, file mock tools, echo endpoints) and PRNG-generated event streams.
- **Impact**: Real-world MCP enterprise deployments exhibit complex, bursty network latency, multi-tenant state concurrency, dynamic tool schemas, and diverse LLM output variations that are not captured in synthetic fixtures.
- **Disclosure**: We state prominently across all documentation that **no claims of real-world or production validity are made**. Validating Sentinel on enterprise production traces remains essential future work requiring commercial data-sharing agreements.

### 3.2 Protocol Surface Scope Limitations
- **Threat**: The Model Context Protocol specification includes diverse transport and session features beyond single-request HTTP JSON-RPC.
- **Boundary**: Sentinel explicitly excludes stdio transport, Server-Sent Events (SSE) streaming, cancellation primitives, LLM sampling endpoints, and prompt templates. Applying Sentinel to unsupported transports requires protocol bridging.

---

## 4. Enforcement & Adversarial Boundaries

### 4.1 Post-Response Irreversibility
- **Threat**: Anomaly detection occurs post-execution.
- **Boundary**: While Sentinel intercepts and withholds the return payload from the client LLM, any state modification already committed by the upstream MCP server (e.g. database rows inserted, emails dispatched, external REST webhooks triggered) cannot be undone. Mitigation requires application-level idempotent rollback or pre-commit sandbox containment.

### 4.2 Colluding Sybil Identities in Adaptive Poisoning
- **Threat**: Dual-memory quarantine relies on multi-principal quorum to promote provisional memory into trusted baseline profiles.
- **Boundary**: As proven in [`docs/poisoning_edge_cases.md`](poisoning_edge_cases.md), adversaries rotating caller identities bypass quarantine entirely (12.0 malicious updates under `gated`). Without hardware-backed or cryptographic Sybil resistance (e.g. mTLS client certificates, verifiable decentralized identifiers), identity counting alone does not prevent distributed poisoning.

### 4.3 Transactional Baseline Parity
- **Threat**: Claiming machine learning superiority for learning admission.
- **Boundary**: The event-bound learning-admission protocol achieves exact numerical parity with classical serializable transaction management (0/6 ineligible, 0/2 eligible) and offers zero algorithmic advantage on static workloads.

---

## 5. Prior-Art Overlap & Algorithmic Lineage

- **Threat**: Presenting standard anomaly detection, capability control, or sandboxing components as wholly novel algorithms.
- **Lineage**:
  - *Autoencoder Anomaly Detection*: Reconstruction error for anomaly detection is established literature (Hawkins et al., Thompson et al., Sakurada & Yairi). Sentinel's 12-dimensional bottleneck network utilizes standard NumPy dense projections and MSE reconstruction loss without bespoke neural architectural claims.
  - *Capability & Authorization Provenance*: Context-bound single-use invocation authority draws directly from classical capability-based operating system design (Dennis & Van Horn, Saltzer & Schroeder, capabilities in object-capability systems).
  - *Quarantine & Two-Phase Promotion*: The dual-memory staging architecture is an adaptation of write-ahead staging buffers, canary deployments, and transaction quarantine patterns from reliable distributed systems.
  - *Distinction*: Sentinel's contribution lies in the domain-specific synthesis and protocol-level integration: binding JSON-RPC runtime transport, causal dataflow tracking, and provisional online learning quarantine into a dependency-free, zero-external-service micro-enforcement gateway. We make no legal or patent originality claims without formal prior-art clearance.

