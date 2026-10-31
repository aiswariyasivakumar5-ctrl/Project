# MCP Runtime Sentinel

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Runtime dependencies](https://img.shields.io/badge/runtime-NumPy%20%2B%20jsonschema-green.svg)](pyproject.toml)
[![Reproducibility](https://img.shields.io/badge/reproducibility-verified%2020--seed-blueviolet.svg)](docs/reproducibility.md)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

> A self-hosted MCP HTTP gateway with a separately packaged research toolkit. The runtime wheel contains gateway code only; publication studies and synthetic evaluation workflows live under `research/`.

---

## 1. Overview & Threat Model

The **Model Context Protocol (MCP)** enables Large Language Models (LLMs) to query external tools, local files, databases, and APIs. However, MCP clients currently execute tool responses with implicit trust, making them vulnerable to tool poisoning, prompt injection, capability laundering, and unauthorized resource access.

**MCP Runtime Sentinel** is a self-hosted gateway between MCP clients and upstream servers. Its operator allowlist and configured pre-execution policy determine whether a tool request is dispatched. The learned detector is a secondary signal; its response withholding happens after upstream execution and is not validated on real customer traffic.

```
+----------------+      JSON-RPC      +----------------------------+      JSON-RPC      +------------------+
|   Host LLM     | =================> |    MCP Runtime Sentinel    | =================> |   Upstream MCP   |
|   Client /     | <================= |      (Reverse Proxy)       | <================= |     Servers      |
| Orchestrator   |   Withhold/Pending |                            |   Direct Response  |  (Files, DB, AP) |
+----------------+                    +----------------------------+                    +------------------+
                                        | - Intent Verification
                                        | - Anomaly Autoencoder
                                        | - Quarantine Memory
                                        | - Bearer Auth & Auditing
                                        | - Human Confirmation Queue
```

### Key Capabilities
- **Lightweight NumPy Autoencoder**: Pure NumPy neural autoencoder with explicit SHA-256 seed expansion; requires zero heavy ML frameworks (no PyTorch, TensorFlow, or Scikit-learn).
- **Dual-Memory Quarantine Architecture**: Separates untrusted new capabilities into a provisional buffer, requiring multi-principal quorum or operator approval before promotion to trusted production memory.
- **Fail-Closed Bearer Authentication**: Protects sensitive administrative interfaces (`/v1/audit`, `/v1/pending`, `/v1/pending/{id}/approve`) against unauthenticated access.
- **Operator Review Queue**: Persists review actions with gateway state. Detector confirmation happens after upstream execution; optional policy approval can hold a request before execution.
- **Response Withholding**: Marks withheld responses with Sentinel headers. This is not an OS, container, filesystem, or network sandbox for upstream tools.
- **Atomic State Persistence**: Preserves server profiles, capability trust matrices, pending actions, and behavioral statistics across gateway reboots.
- **Operator-Defined Tool Allowlist**: Tool calls are denied before dispatch unless the operator explicitly enables the exact upstream tool name with `--allow-tool`.

The serving CLI refuses to start without separate client and operator credentials, an operator-approved baseline, a per-tool risk/schema policy, and an explicit tool allowlist. Online learning is disabled unless `--enable-learning` is passed.

```bash
export MCP_SENTINEL_CLIENT_TOKEN='replace-with-a-random-secret-of-at-least-32-characters'
export MCP_SENTINEL_OPERATOR_TOKEN='use-a-different-random-secret-of-at-least-32-characters'
python -m sentinel.cli baseline --upstream http://127.0.0.1:8790 --server-id local-mcp --state-file sentinel-state.json --policy-file examples/production-policy.json
python -m sentinel.cli baseline approve --state-file sentinel-state.json --actor operator-id --audit-log audit.jsonl
python -m sentinel.cli gateway --upstream http://127.0.0.1:8790 --server-id local-mcp --state-file sentinel-state.json --policy-file examples/production-policy.json --audit-log audit.jsonl \
  --allow-tool safe_read --allow-tool calculate
```

Treat each allowlisted tool as permission for the upstream server to execute it. MCP tool annotations are not used as authorization because the upstream server controls them.

---

## 2. Synthetic Research Findings (20 Seeds, 95% Confidence Intervals)

The numbers below describe the retained synthetic evaluation only. They do not measure production attack detection or customer traffic behavior.

All numbers are derived across **20 independent evaluation seeds** (20001–20020) on 5,000 train, 1,000 validation, and **3,250 test synthetic events per seed** (1,750 benign and 1,500 attack events):

| Model Architecture | $F_1$ Score (Mean ± Std) | 95% Bootstrap CI | Precision | Recall | False Positive Rate | Wilcoxon $p$ (Holm-adj) |
|---|---|---|---|---|---|---|
| **Sentinel (Ours)** | **0.8000 ± 0.0001** | **[0.8000, 0.8000]** | **0.99995** | **0.6667** | **0.0000286** | Reference |
| **Dense Autoencoder** | 0.8815 ± 0.0265 | [0.8704, 0.8931] | 0.9051 | 0.8601 | 0.0771 | $p = 0.000010$ |
| **Transformer (Sequential)** | 0.8381 ± 0.0101 | [0.8338, 0.8422] | 0.8965 | 0.7869 | 0.0778 | $p = 0.000010$ |
| **LSTM (Sequential)** | 0.8250 ± 0.0058 | [0.8227, 0.8274] | 0.8936 | 0.7663 | 0.0782 | $p = 0.000010$ |
| **One-Class SVM** | 0.7904 ± 0.1245 | [0.7350, 0.8391] | 0.8849 | 0.7364 | 0.0859 | $p = 0.927279$ |
| **Isolation Forest** | 0.0000 ± 0.0000 | [0.0000, 0.0000] | 0.0000 | 0.0000 | 0.0073 | $p = 0.000010$ |

### Trade-Off Highlights
1. **Low False Alarm Rate**: Across 35,000 normal test events (20 seeds), Sentinel observed an empirical FPR of $0.0000286$ (1 false alarm total; 19 seeds at 0.0), establishing an exact 95% Clopper-Pearson upper bound of **0.0159%** (less than 1.6 false alarms per 10,000 calls).
2. **All-or-Nothing Recall Profile**: Sentinel's 0.6667 recall reflects full detection (1.0000 recall, 125/125 detected each = 1,000/1,000 events) on 8 attack families (`intent_mismatch`, `tool_poisoning`, `policy_injection`, `data_exfiltration`, `schema_mutation`, `destructive_operation`, `cross_server`, `delayed_malicious`) and zero detection (0.0000 recall, 0/125 detected each = 0/500 events) on 4 subtle/temporal families (`abnormal_sequence`, `capability_drift`, `gradual_poisoning`, `low_and_slow`), yielding exactly $1,000 / 1,500 = 0.6667$ aggregate recall.
3. **Matched-FPR Trade-Off**: In a descriptive continuous raw-score ROC sweep, neural baseline recall is **0.5000** at FPR ≤1%; thresholds are selected using benign scores from the same test split, so this is not an operational held-out estimate. A separate stored-percentile sweep reports **0.0000** recall at FPR ≤1% because of discrete score ties; the minimum FPR at which those percentile curves achieve nonzero recall is 7.14%. See [docs/matched_fpr_reconciliation.md](docs/matched_fpr_reconciliation.md).
4. **Low Gateway Overhead**: Sentinel introduces only **0.83 ms** of net proxy inspection latency ($1.25 \text{ ms}$ total gateway response vs. $0.42 \text{ ms}$ direct mock server latency).

---

## 3. Production Deployment

Install the package, enroll a known-benign baseline, and start the gateway with
separate secrets, TLS, a state file, and an explicit tool allowlist. The
deployment guide includes upstream credentials, client credential rotation,
Docker/systemd operation, backups, health checks, audit verification, and
pre-execution policy examples.

```bash
python -m pip install .
export MCP_SENTINEL_CLIENT_TOKEN="$(openssl rand -hex 32)"
export MCP_SENTINEL_OPERATOR_TOKEN="$(openssl rand -hex 32)"
export MCP_SENTINEL_STATE_KEY="$(openssl rand -hex 32)"
python -m sentinel.cli baseline --upstream https://mcp-upstream.example/api \
  --server-id inventory-prod --state-file /var/lib/mcp-sentinel/state.json \
  --policy-file /etc/mcp-sentinel/policy.json
python -m sentinel.cli baseline approve --state-file /var/lib/mcp-sentinel/state.json \
  --actor deployment-change-id --audit-log /var/log/mcp-sentinel/audit.jsonl
python -m sentinel.cli gateway --upstream https://mcp-upstream.example/api \
  --server-id inventory-prod --host 0.0.0.0 --port 8788 \
  --state-file /var/lib/mcp-sentinel/state.json \
  --policy-file /etc/mcp-sentinel/policy.json \
  --tls-cert /etc/mcp-sentinel/server.crt --tls-key /etc/mcp-sentinel/server.key \
  --allowed-host sentinel.example:8788 --allow-tool lookup_item
```

Treat every allowlisted tool according to its configured risk class. Detector
response withholding occurs after execution and does not prevent upstream
actions. Review
[`docs/deployment.md`](docs/deployment.md),
[`docs/threat_model_production.md`](docs/threat_model_production.md), and
[`docs/production_gaps.md`](docs/production_gaps.md) before deployment.

## 4. Research Reproduction

### Requirements
- Python >= 3.11 (audited on CPython 3.14.3 AMD64).
- Runtime dependencies: NumPy and `jsonschema`; the optional research distribution adds its own dependencies.

### Setup
```bash
# 1. Clone repository
git clone <repo-url>
cd <repository-directory>

# 2. Create and activate virtual environment
python -m venv .venv
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

# 3. Install dependencies
python -m pip install -r requirements-repro.txt -e . -e research
```

### Reproduce All Tables & Figures (Recommended Order)

The synthetic dataset shards (`datasets/`) are shipped with the repository. Because raw evaluation outputs (`results/`) are generated artifacts, use the following sequence on a fresh clone or release archive:

#### 1. Full 20-Seed Training & Evaluation (Initial Generation)
Generate the baseline models, ablations, and evaluation traces across all 20 seeds (20001–20020):

```bash
python scripts/reproduce_all.py --full
```

This trains all 6 models, evaluates all ablations, runs the statistical significance battery, and populates `results/` (~3–5 minutes on modern multi-core systems).

#### 2. Fast Re-Derivation of All Tables & Figures
Once `results/` is populated, re-derive all publication artifacts in **~20 seconds**:

```bash
# Using Python:
python scripts/reproduce_all.py

# Using Makefile (Linux / macOS):
make all

# Using PowerShell (Windows native):
.\scripts\reproduce_all.ps1
```

This verifies all 480 dataset shards by SHA-256 and regenerates all 12 publication tables, 9 figures, the 1,320-phase novelty v3 report, and 700-cell matched poisoning statistics strictly from verified raw outputs.

To run integrity verification only (verifies dataset shards, and evaluation artifacts if present):
```bash
python scripts/reproduce_all.py --verify-only
```

---

## 5. Scientific Disclosures & Limitations

In accordance with strict open-science practices, all negative and null results are preserved and explicitly reported:

1. **Synthetic Workload Disclaimer**: All training and test datasets are synthetic mock MCP interactions generated via controlled PRNG seeds. No claim of real-world or production validity is made without permissioned enterprise traces.
2. **Zero-Recall Detector Blind Spots**: Sentinel achieves **0.0000 recall** on 4 specific attack families:
   - `abnormal_sequence`: Order-invariant bag-of-calls representation cannot detect call order permutations.
   - `capability_drift`: Subtle, step-by-step parameter drift within legitimate tool ranges.
   - `gradual_poisoning`: Incremental metric manipulation that stays beneath the autoencoder reconstruction threshold per step.
   - `low_and_slow`: Infrequent, sparse tool invocations that fall below cumulative variance thresholds.
   *(See [docs/zero_recall_analysis.md](docs/zero_recall_analysis.md) for full mathematical analysis).*
3. **Upstream Side-Effect Irreversibility**: Sentinel intercepts and withholds payloads returned to the LLM client, but cannot undo destructive side-effects (e.g. database deletions or external webhooks) already executed by upstream MCP servers.
4. **Colluding Adversary Limitation**: In matched poisoning simulations (700 cells), adversaries rotating across distinct caller identities bypass quarantine (12.0 malicious updates under `gated`), proving that identity counting without cryptographic Sybil resistance cannot defend against distributed poisoning.
5. **Transactional Parity**: The learning-admission prototype exhibits exact parity with the standard transactional baseline (0/6 ineligible, 0/2 eligible) and offers zero algorithmic advantage on static workloads.

---

## 6. Documentation Sitemap

- [docs/reproducibility.md](docs/reproducibility.md): Audited environment, hardware requirements, and reproduction commands.
- [docs/paper_numbers.md](docs/paper_numbers.md): Cell-by-cell traceability mapping every reported number to raw JSON files.
- [docs/enforcement_architecture.md](docs/enforcement_architecture.md): Confirmation queue, sandbox containment, and HTTP API specifications.
- [docs/zero_recall_analysis.md](docs/zero_recall_analysis.md): Mathematical breakdown of the 4 detector blind spots.
- [docs/poisoning_edge_cases.md](docs/poisoning_edge_cases.md): 20-seed matched poisoning failure modes and Sybil limitations.
- [docs/final_limitations.md](docs/final_limitations.md): Complete catalog of engineering and theoretical boundaries.
- [docs/deployment.md](docs/deployment.md): Production setup, operations, backups, and policy.
- [docs/threat_model_production.md](docs/threat_model_production.md): Production security boundaries and assumptions.
- [docs/production_gaps.md](docs/production_gaps.md): Remaining validation and deployment limits.
- [docs/data_archive.md](docs/data_archive.md): Open-science data archival manifest and artifact retention plan.
- [CHANGELOG.md](CHANGELOG.md): Historical milestone notes and research log.

---

## 7. Testing

Install both development packages from the repository root, then run either test runner:

```bash
python -m pip install -e '.[dev]' -e 'research[dev]'
python -m pytest
python -m unittest discover -s tests
```

The main `mcp-runtime-sentinel` wheel contains only runtime code. Reproduction,
dashboard, synthetic mock-server, plotting and study modules are in the separate
`mcp-runtime-sentinel-research` package under `research/`. The runtime CLI provides
gateway, baseline enrollment, API serving, and audit verification commands; install
the research package to use its separate research CLI. Research-artifact tests that
need generated `results/` remain skipped when those artifacts are absent.
See [docs/package_layout.md](docs/package_layout.md) for the package boundary and
the optional `research[paper]` dependency used by paper rendering.

---

## 8. Citation

If you use MCP Runtime Sentinel in your research, please cite:

```bibtex
@article{mcp_sentinel_2027,
  title   = {MCP Runtime Sentinel: Context-Bound Authorization and Evidence-Gated Runtime Adaptation for Model Context Protocol Gateways},
  author  = {Anonymous Authors},
  journal = {Preprint (under double-blind review)},
  year    = {2027}
}
```

---

## 9. License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.
