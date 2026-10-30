# Reproducibility Guide: MCP Runtime Sentinel

This document provides complete instructions to verify, re-derive, and independently validate all findings, metrics, tables, and figures reported in the Springer LNCS paper submission (*AI-SEC workshop at AINA-2027*).

---

## 1. Quickstart (Reproduction Sequence)

Synthetic dataset shards (`datasets/`) are included in the repository. The evaluation traces and metrics (`results/`) are generated artifacts. On a fresh repository checkout:

### Step 1: Full 20-Seed Generation (Run First)
Generate the baseline models, ablations, and evaluation traces across all 20 seeds (20001–20020):

```bash
python scripts/reproduce_all.py --full
```

This trains all 6 models, evaluates all ablations, executes the statistical tests, and populates `results/` (~3–5 minutes).

### Step 2: Fast Re-Derivation of All Outputs
Once `results/` is populated:

```bash
# Using Python directly (cross-platform):
python scripts/reproduce_all.py

# Using Makefile (Linux / macOS / Windows with make):
make all

# Using PowerShell (Windows native):
.\scripts\reproduce_all.ps1
```

**Total Execution Time**: ~20 seconds from raw artifact traces.

To run integrity verification only (checks all 480 dataset shards, and evaluation artifacts when present):
```bash
python scripts/reproduce_all.py --verify-only
```

---

## 2. Audited Hardware and Software Environment

The primary evaluation was audited and verified on the following reference system:

| Parameter | Audited Reference Environment | Minimum Requirements |
|---|---|---|
| **Operating System** | Windows 11 Enterprise (build 26100, 64-bit AMD64) | Windows 10+, Linux (Ubuntu 22.04+), macOS 13+ |
| **Python Runtime** | CPython 3.14.3 (tags/v3.14.3:323c59a, Feb 3 2026) | Python >= 3.11 |
| **C/C++ Compiler / ABI** | MSC v.1944 64 bit (AMD64) | Compatible C runtime |
| **Numeric Dependency** | `numpy==2.5.2` | `numpy>=1.24` |
| **Deep Learning Frameworks**| **None** (Pure NumPy lightweight autoencoder & baselines) | None |
| **CPU Requirements** | Modern multi-core x86_64 (audited on 18 logical cores / 32 threads) | Modern dual-core processor |
| **Memory (RAM)** | 32 GB physical RAM (peak per-worker usage < 512 MB) | 2 GB RAM |
| **Disk Footprint** | ~75 MB core repo; raw multi-seed novelty matrix logs ~8 GB | 200 MB free space (core); 10 GB (full raw traces) |

### Experiment Benchmark Runtimes (Audited on Reference Machine)
| Experiment Campaign | Seeds / Workload | Source Script | Wall Clock Runtime | Output Directory |
|---|---|---|---|---|
| **Novelty Matrix v3** | 20 seeds (30001–30020), 1,320 phases | `scripts/run_novelty_matrix_v3.py` | 1,994.4 s (~33.2 min) | `results/novelty/publication_scale_v3/` |
| **Novelty Report v3** | Aggregation & Exact Permutation Tests | `scripts/finish_novelty_v3.py` | 5.2 s | `results/novelty/publication_scale_v3_report/` |
| **Capability Trust D1 Held-Out** | 20 seeds + 2 new held-out scenarios + sensitivity | `scripts/evaluate_capability_trust_d1.py` | 1.8 s | `results/capability_trust_held_out/` |
| **Matched-FPR v2 Reconciliation** | 20 seeds (20001–20020), 70,000 events | `scripts/reconcile_matched_fpr.py` | 1.1 s | `results/matched_fpr_v2/` |
| **Baseline Calibration Diagnosis** | 20 seeds, token feature variance analysis | `scripts/diagnose_calibration_gap.py` | 1.4 s | `docs/baseline_calibration_gap.md` |
| **Publication Pipeline Reproduction** | Verification + Tables + Figures | `scripts/reproduce_all.py` | 19.6 s | `results/tables_20seed/`, `results/figures_20seed/` |

### Clean Virtual Environment Setup
```bash
# 1. Create isolated virtual environment
python -m venv .venv

# 2. Activate virtual environment
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

# 3. Install audited dependencies and editable package
python -m pip install -r requirements-repro.txt -e .
```

---

## 3. Reproduction Pipeline Architecture

The reproduction suite is orchestrated via `scripts/reproduce_all.py` across two formal stages:

### Stage 1: Integrity Verification (`--verify-only`)
1. **Synthetic Dataset Manifest Check**:
   - Reads `datasets/synthetic-expanded-v1/manifest.json`.
   - Re-computes SHA-256 digests across all 480 gzip shards across 20 evaluation seeds (20001–20020) and 22 scenarios.
   - Verifies 0 bitwise discrepancies.
2. **Legacy Research Package Check**:
   - Executes `sentinel.final_verification.verify_research_package()`.
   - Validates 43 retained historical baseline files across 6 baseline models and 5 legacy seeds (42, 123, 456, 789, 1001).
3. **20-Seed Evaluation Artifacts Check**:
   - Verifies 120 baseline per-seed files (`results/baselines_20seed/`).
   - Verifies 120 ablation per-seed files (`results/ablations_20seed/`).
   - Verifies 330 completed novelty matrix evaluations (`results/novelty/publication_scale_complete/`).
   - Verifies 700 matched poisoning simulation cells (`results/adaptation/matched_poisoning_20seed/`).

### Stage 2: Fast Re-Derivation of All Publication Outputs
All paper outputs are derived strictly from raw evaluation logs without re-fitting thresholds or re-running slow inference:

| Stage Component | Output Directory / Files | Derivation Script | Execution Time |
|---|---|---|---|
| **Publication Tables** | `results/tables_20seed/` (12 files: MD, CSV, JSON) | `sentinel.research_tables` | ~2.1 s |
| **Vector Figures** | `results/figures_20seed/` (9 SVG charts) | `sentinel.plots` | ~0.3 s |
| **Novelty Matrix Report** | `results/novelty/publication_scale_report/REPORT.md` (330 cells) | `sentinel.novelty_report` | ~16.1 s |
| **Poisoning Statistics** | `results/adaptation/matched_poisoning_20seed/tables_20seed.md` (700 cells) | `sentinel.matched_poisoning_stats` | ~0.6 s |
| **Total** | | | **~19.6 s** |

---

## 4. Full Re-Training & Re-Evaluation from Scratch (`--full`)

If the reviewer wishes to bypass pre-computed evaluation traces and re-train all models and ablations from scratch across all 20 seeds (20001–20020):

```bash
python scripts/reproduce_all.py --full
```

This runs:
1. `CompareConfig(seeds=20001..20020, train_size=5000, validation_size=1000, test_size=3000)`:
   - Evaluates all 6 models: Sentinel (Lightweight Autoencoder), Isolation Forest, One-Class SVM, Dense Autoencoder, LSTM, and Transformer.
2. `AblationConfig(seeds=20001..20020, bootstrap_resamples=20000)`:
   - Evaluates Sentinel full model vs. 5 ablations (without attestation, without causal, without intent, without quarantine, without uncertainty).
3. Statistical significance battery (exact paired Wilcoxon signed-rank tests, exact sign-flip tests, and Holm multiple-testing adjustments).
4. Full table and figure generation.

*Expected runtime*: ~3 to 5 minutes on modern multi-core systems.

---

## 5. Non-Negotiable Scientific Integrity Guarantees

Every claim and figure in the paper complies with strict open-science rules:
1. **No Data Fabrication**: No metrics or numbers are hand-edited or estimated. Every number is generated by deterministic scripts from raw outputs.
2. **Validation-Only Threshold Calibration**: Decision thresholds ($\tau$) are fitted solely on validation splits; the test split is never observed during calibration.
3. **Deterministic Seeding**: Autoencoder weights and NumPy PRNGs are seeded via explicit SHA-256 digest mapping (`sentinel/engine.py`), ensuring bitwise reproducibility across runs.
4. **Preservation of Negative / Null Results**:
   - Zero-recall failure modes (delayed causal misuse, schema-stable poisoning, capability laundering) are fully documented.
   - Matched poisoning limitations (colluding identities bypassing quarantine with 12.0 malicious updates) are reported without suppression.
   - Transactional baseline parity (0/6 ineligible, 0/2 eligible) is explicitly reported.
5. **Synthetic Workload Disclosure**: All evaluation workloads are generated from synthetic mock MCP servers. No claims of production or real-world validity are made.
