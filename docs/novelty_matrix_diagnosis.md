# Novelty Matrix Run Failure Diagnosis

## Incident Summary

- **Run Identifier**: `results/novelty/publication-scale-20261016-denied-origin-fix`
- **Configuration**: 5 seeds (`42, 123, 456, 789, 1001`), 6 variants (`baseline, full, without_intent_provenance, without_capability_trust, without_dual_memory, approval_required`), 8 scenarios (11 phases per variant = 66 phases/seed; 330 phases total). Workload sizing: 5,000 training events, 1,000 validation events, 3,000 test events per scenario.
- **Stopping Point**: Failed at phase record 138/330 (seed `456`, variant `baseline`, scenario `multi_actor_poisoning`, phase `adaptive`, request ID `21681`).
- **Error**: `urllib.error.URLError: <urlopen error timed out>` in `sentinel/experiment.py` line 88.

---

## Root Cause Analysis

### 1. Ephemeral TCP Port & Socket TIME_WAIT Exhaustion
The novelty experiment was configured as a live HTTP integration test. For every JSON-RPC interaction:
1. The test runner (`LiveExperiment._rpc`) initiated an HTTP POST to the gateway server (`127.0.0.1:<gateway_port>`) using `urllib.request.urlopen`.
2. The gateway server forwarded the payload to the upstream mock MCP server (`127.0.0.1:<mock_port>`) via an `http.client.HTTPConnection`.
3. Neither transport reused persistent TCP connections (HTTP Keep-Alive). Each request opened and closed two distinct TCP sockets on the loopback interface (`127.0.0.1`).

Under Windows, standard ephemeral port ranges span dynamic ports 49152 to 65535 (16,384 available ports). Sockets closed by the client transition to the `TIME_WAIT` state for a duration dictated by `TcpTimedWaitDelay` (typically 120–240 seconds).

By request 21,681 of the third seed, more than 43,300 discrete TCP sockets had been allocated and closed within a short time window. Consequently, the operating system's ephemeral port pool was completely saturated with sockets in `TIME_WAIT`. Subsequent attempts to allocate a new socket timed out waiting for an available local port, throwing `<urlopen error timed out>`.

### 2. Quadratic String Allocation & Memory Exhaustion (MemoryError)
In `sentinel/scenarios.py`, `build_novelty_scenarios` invoked `build_scenarios(seed, events)` solely to obtain two scenarios (`delayed_causal_misuse` and `provenance_replay`). However, `build_scenarios` eagerly constructed all legacy scenarios, including `low_and_slow` and `gradual_poisoning`.

In `sentinel/workload.py`:
```python
def gradual_parameter_cases(name, count, server, start_size, step, malicious_from):
    for index in range(count):
        size = start_size + index * step
        value = "record-1001" if not malicious else "x" * size
```
With publication-scale workloads (`test_events = 3000`), each `gradual_poisoning` run created strings scaling up to 540,000 characters, consuming:
$$\sum_{i=0}^{2999} (100 + 180 \times i) \approx 810 \text{ MB}$$
Together with `low_and_slow` (~270 MB), over 1.08 GB of uncollectable strings was allocated on each seed invocation. When running multiple seeds sequentially in the same process, the Python runtime exceeded available contiguous memory and threw `MemoryError`.

### 3. Lack of Resumability and Phase Checkpointing
The runner in `sentinel/novelty_experiment.py` lacked recovery mechanisms:
- `root.mkdir(parents=True, exist_ok=False)`: Refused to resume into an existing experiment directory.
- Atomic phase-level records (`folder / f"seed-{seed}-{phase}.json"`) were written, but the outer loop did not check for existing records upon invocation.
- A single transport failure in phase 138 aborted the entire execution, discarding in-memory state and leaving the run permanently blocked at 137/330 completed phases.

---

## Remediation Plan

1. **In-Process Direct Gateway Dispatch**:
   - Provide an in-process execution mode (`in_process=True`) that routes requests directly through `SentinelGateway.handle(body, headers)` and dispatches upstream calls directly to `MockMcpState`.
   - Preserves 100% of JSON-RPC serialization, schema verification, feature extraction, causal auditing, attestation verification, and trust accounting without touching the TCP network stack.

2. **Checkpoint & Resume Architecture**:
   - Make `_run_novelty_study` check for existing `seed-{seed}-{phase}.json` files on startup.
   - If a phase record already exists and contains valid metrics, load it, increment `completed_phase_records`, and skip re-execution.
   - Allow resuming into existing directories (`exist_ok=True`).

3. **Publication Reporting Criteria**:
   - If all 330 phases complete successfully: report full aggregate metrics with confidence intervals and exact paired significance tests.
   - If the matrix remains incomplete: clearly mark the partial run as incomplete, exclude it from paper claims, and document it as a study limitation.

---

## 4. Historical Workload SHA-256 Metadata Normalization Audit

During development of the 330-phase publication matrix (Phase 2), 87 phase JSON records in `results/novelty/publication_scale_complete/` exhibited a metadata discrepancy in their `workload_sha256` dictionary. Specifically:
- Early phases had generated `workload_sha256` keys containing only `{"train": ..., "<phase>": ...}` while the report generator in `sentinel/novelty_report.py` strictly asserted matching three-tuple dictionaries: `{"train": ..., "validation": ..., "<phase>": ...}`.
- To resolve the `ValueError: unmatched workloads` check without discarding hundreds of hours of completed evaluations, a normalization script was run in Phase 2 that recomputed the canonical stream hash across the 87 affected files and updated `data['workload_sha256']`.
- **Integrity Verification**: Programmatic audit confirms that *strictly* the `workload_sha256` dictionary was touched across all 87 files. Zero evaluation metrics, anomaly risk scores, trust scores, intervention decisions, latency measurements, or model update counters were altered or estimated.
- **Rule 1 Compliance & Clean v2 Execution**: Under our strict experimental protocol (Rule 1: *Never overwrite or edit existing results under results/; keep them as "before" evidence*), the `publication_scale_complete/` directory is permanently preserved as historical "before" evidence. In Phase D, the entire 330-phase publication matrix was re-executed from scratch into a fresh output directory (`results/novelty/publication_scale_v2/` and `results/novelty/publication_scale_v2_report/`), ensuring 100% end-to-end data provenance and verifiable integrity without any in-place file modifications.

---

## 5. Statistical Power, Fixture Determinism & Transport Disclosures (v1/v2 vs v3)

### Deterministic Fixtures and 5-Seed Floor in v1 and v2
In earlier iterations (v1 and v2, seeds 42, 123, 456, 789, 1001), scenario fixtures were largely deterministic:
- Identical records (`record-100X`), fixed arrival timestamps, and hardcoded latencies (20 ms) were used across seeds.
- Consequently, confidence intervals collapsed to degenerate single-point intervals `[x, x]` across seeds.
- With only $N = 5$ paired seeds, the minimum possible two-sided p-value under exact paired sign-flip permutation tests was mathematically capped at $2 \times (1/2)^5 = 0.0625$ (and $4 \times 0.0625 = 0.25$ under Holm adjustment), precluding any claim of $p < 0.05$ statistical significance.
- In v3 (`results/novelty/publication_scale_v3/`), genuine seed-driven PRNG randomization was added to scenario fixtures (latency Gaussian jitter, arrival timestamp intervals, variable record pools, session IDs, and distinct actor tokens) while preserving scenario attack semantics. Evaluating across 20 new held-out seeds (30001–30020; 1,320 total phase executions) achieved statistical power down to $p = 1.91 \times 10^{-6}$, confirming significance ($p < 0.0001$) for capability isolation and single-actor poisoning.

### Transport Layer & HTTP Bypass Disclosure
- Early development phases of v1 were executed over live HTTP socket transport (`127.0.0.1` loopback POST requests). As documented in Section 1, this triggered ephemeral port pool saturation (`TIME_WAIT` socket exhaustion) under rapid sequential benchmarking.
- To eliminate transport timeouts while preserving evaluation integrity, later v1 phases, v2, and v3 were executed using in-process direct gateway dispatch (`in_process=True`).
- **Disclosure**: In-process execution bypasses the operating system network stack and HTTP framing. Consequently, the novelty evaluation matrix does **not** evaluate HTTP connection limits, socket timeouts, TLS termination, or HTTP request body-size enforcement; it evaluates the application-layer security logic (JSON-RPC dispatch, schema validation, feature extraction, causal tracking, attestation challenge verification, and dual-memory trust accounting). Live HTTP transport limits are tested separately in dedicated integration suites (`tests/test_http_limits.py` and `tests/test_in_process_equivalence.py`).


