# MCP Runtime Sentinel Project Assessment & Architecture Review

**Assessment Date**: October 25, 2026  
**Target Milestone**: Proposed Springer proceedings submission (*AI-SEC workshop at AINA-2027; workshop listing and deadline not yet confirmed*)
**Scope**: Complete repository code, test suite, documentation, and reproduced experimental packages.

---

## 1. Executive Summary & Current Status

The **MCP Runtime Sentinel** project is a comprehensive Python/NumPy research prototype providing intent-conditioned runtime enforcement, trust tracking, and anomaly detection for Model Context Protocol (MCP) servers.

All core developmental and scientific objectives outlined for publication readiness are achieved:
- **Test Suite**: **304 passing tests** (`python -m unittest discover -s tests`, 100% pass rate in ~120 seconds).
- **Statistical Evidence (Phase 1)**: Expanded from 5 seeds to **20 seeds** (20001–20020) with exact Wilcoxon signed-rank tests, exact sign-flip tests, Holm multiple-testing corrections, and 95% bootstrap confidence intervals.
- **Novelty Matrix (Phase 2)**: **330/330 cells completed** across 22 scenarios, 5 variants, 2 phases, and 5 legacy seeds (`results/novelty/publication_scale_complete/`).
- **Detector Hardening (Phase 3)**: Fixed autoencoder PRNG initialization via deterministic SHA-256 seed hashing; implemented semantic intent benchmark; documented tie-handling and mathematical zero-recall properties.
- **Matched Poisoning Study (Phase 4)**: **700 cells evaluated** (5 streams × 7 policies × 20 seeds) in `results/adaptation/matched_poisoning_20seed/`. Documented colluding identities failure modes and exact transactional baseline parity.
- **Enforcement Architecture (Phase 5)**: Implemented human-in-the-loop pending action queue (`PendingAction`), explicit sandbox containment headers, fail-closed bearer token authentication, and atomic state persistence.
- **Reproducibility Package (Phase 6)**: Implemented unified `scripts/reproduce_all.py` (with `Makefile` and `scripts/reproduce_all.ps1`), 480 dataset shard SHA-256 verification, and `docs/paper_numbers.md`.
- **Repository Cleanup (Phase 7)**: Removed nested duplicate checkouts, purged legacy zip archives, refreshed documentation, and established formal licensing and citation files.

---

## 2. Verification & Integrity Audit

| Verification Check | Audited Result | Status |
|---|---|---|
| **Full Unit & Integration Suite** | **304 tests passed** in 121.766 seconds | **PASS** |
| **Synthetic Dataset Manifest** | 480/480 gzip shards verified by SHA-256 (`datasets/synthetic-expanded-v1/manifest.json`) | **PASS** |
| **Legacy Research Package** | 43 retained baseline files verified without inconsistency (`sentinel.final_verification`) | **PASS** |
| **20-Seed Primary Artifacts** | 574 files checked across baselines, ablations, novelty (330), and poisoning (700) | **PASS** |
| **Execution Environment** | CPython 3.14.3 AMD64, `numpy==2.5.2` (no PyTorch, TensorFlow, Scikit-learn required) | **PASS** |
| **Reproduction Pipeline Speed** | Fast re-derivation in **19.64 seconds**; full re-training in ~3–5 minutes | **PASS** |

---

## 3. System Architecture & Component Inventory

The Sentinel gateway operates as a transparent reverse proxy between the host LLM and untrusted upstream MCP tool servers.

### 3.1 Runtime & Transport Modules (`sentinel/`)
- `gateway.py`: Reverse proxy, JSON-RPC parsing, preflight intent check, enforcement routing, pending action queue, bearer authentication.
- `engine.py`: Multi-feature risk fusion, lightweight NumPy autoencoder with SHA-256 seeding, server profiles, state persistence.
- `detectors.py`: Welford online standardization, autoencoder forward/reconstruction logic, session transition models.
- `features.py`: Runtime feature extraction, payload metrics, and intent alignment vectors.
- `semantic_intent.py`: Tokenized semantic intent matching and benchmark validation.
- `approvals.py`: Operator review confirmation, human-in-the-loop lifecycle, expiration timers.
- `provenance.py`: Single-use capability token issuance, argument binding, cryptographic replay prevention.
- `attestation.py`: Server-bound manifest challenge verification with time-to-live expiration.
- `causal.py`: Directed interaction graph tracking cross-server precedence and token provenance.
- `novelty.py`: Capability-level trust matrix, dual-memory isolation (candidate vs. trusted memory).
- `retention.py`: Bounded capacity controls preventing memory exhaustion from unbounded servers.
- `http_limits.py`: Socket deadlines, read limits, and connection concurrency governors.

### 3.2 Evaluation & Scientific Pipeline Modules (`sentinel/` & `scripts/`)
- `scripts/reproduce_all.py`: Unified reproducibility orchestrator for dataset verification, table regeneration, and figure synthesis.
- `scripts/reproduce_main.py`: Full 20-seed baseline comparison, ablation matrix, and statistical testing runner.
- `sentinel/compare.py`: Baseline model comparison engine (Sentinel, Dense AE, Isolation Forest, LSTM, OC-SVM, Transformer).
- `sentinel/ablation.py`: Component ablation engine (Full vs. Without Attestation, Causal, Intent, Quarantine, Uncertainty).
- `sentinel/statistics.py`: Bootstrap percentile confidence intervals, exact Wilcoxon signed-rank tests, exact sign-flip tests, Holm adjustments.
- `sentinel/research_tables.py`: Machine-readable publication table generator (Markdown, CSV, JSON).
- `sentinel/plots.py`: Standalone SVG chart and diagram generator.
- `sentinel/matched_poisoning.py` & `matched_poisoning_stats.py`: 20-seed adaptive poisoning study runner and statistical analyzer.
- `sentinel/novelty_experiment.py` & `novelty_report.py`: 330-cell novelty study runner and bootstrap reporting tool.

---

## 4. Headline Empirical Metrics (20-Seed Benchmark)

### 4.1 Main Baseline Comparison (Table 1)
- **Sentinel**: $F_1 = 0.8000 \pm 0.0001$ [0.8000, 0.8000], $\text{Precision} = 1.0000$, $\text{Recall} = 0.6667$, $\text{FPR} = \mathbf{0.0000}$.
- **Dense Autoencoder**: $F_1 = 0.8815 \pm 0.0265$, $\text{FPR} = 0.0771$ ($p_{adj} = 0.000010$, $r = -1.0000$).
- **Transformer**: $F_1 = 0.8381 \pm 0.0101$, $\text{FPR} = 0.0778$ ($p_{adj} = 0.000010$, $r = -1.0000$).
- **LSTM**: $F_1 = 0.8250 \pm 0.0058$, $\text{FPR} = 0.0782$ ($p_{adj} = 0.000010$, $r = -1.0000$).
- **One-Class SVM**: $F_1 = 0.7904 \pm 0.1245$, $\text{FPR} = 0.0859$ ($p_{adj} = 0.927279$, $r = +0.0286$).
- **Isolation Forest**: $F_1 = 0.0000 \pm 0.0000$, $\text{FPR} = 0.0073$ ($p_{adj} = 0.000010$, $r = +1.0000$).

### 4.2 Gateway Overhead
- Direct Mock MCP Server: **0.42 ms**
- Sentinel Intercepted Gateway Call: **1.25 ms**
- Net Proxy Latency Overhead: **0.83 ms**

---

## 5. Non-Negotiable Disclosures & Known Boundaries

1. **Synthetic Evidence**: All evaluations are conducted against synthetic mock MCP workloads generated by PRNG seeds. No claims of production or real-world validity are made.
2. **Zero-Recall Detector Blind Spots**: The order-invariant feature representation exhibits zero recall on 4 attack families (`abnormal_sequence`, `capability_drift`, `gradual_poisoning`, `low_and_slow`).
3. **Withhold-Only Post-Response Enforcement**: Upstream side-effects (e.g. database updates, webhooks) executed prior to response withholding cannot be rolled back.
4. **Colluding Adversaries in Adaptive Poisoning**: Adversaries rotating identities bypass quarantine (12.0 malicious updates under `gated`), showing identity accounting alone does not prevent distributed Sybil poisoning.
5. **Transactional Parity**: Event-bound learning admission offers exact metric parity with transactional baselines on static tasks (zero algorithmic advantage).
