# Reproducible research evaluation

## Methodology

Security experiments execute JSON-RPC `tools/call` traffic through real in-process
HTTP MCP gateways and safe MCP servers. Two gateways share one Sentinel engine for
cross-server scenarios. Workload latency is seeded and injected into detector
telemetry for reproducible behavioral scores; separately measured wall-clock latency
is retained for performance reporting.

The split is explicit:

1. **TRAIN** uses labeled-normal traffic and trusted enrollment. It may update the
   baseline. This is an experimental enrollment control, not a public gateway header.
2. **VALIDATION** never learns. Metrics are reported, and the engine is restored to
   its post-training state before TEST. No test thresholds are tuned today.
3. **TEST** never learns for held-out security scenarios. Legitimate drift and
   gradual poisoning are explicitly labeled adaptive phases because adaptation or
   poisoning resistance cannot be studied with learning disabled.

The same seed reproduces workload order, parameters, sessions, server choice,
telemetry latency, model initialization, experiment ID, risks, and decisions.
Wall-clock latency naturally varies.

## Workloads and scenarios

Normal workloads vary tool frequency, sessions, servers, parameters, response types,
and latency, with `calculate` used as a legitimate rarer operation.

Implemented scenarios:

| Scenario | Purpose |
|---|---|
| `normal` | Diverse legitimate traffic |
| `legitimate_drift` | Shift from reads toward calculations |
| `intent_mismatch` | Destructive tool conflicts with read intent |
| `abnormal_sequence` | Unseen/rare tool transition |
| `tool_poisoning` | Policy-bearing tool response |
| `policy_injection` | Embedded instruction injection |
| `data_exfiltration` | Token-bearing export behavior |
| `schema_mutation` | Mutated response structure |
| `capability_drift` | Changed `tools/list` fingerprint |
| `destructive_operation` | Simulated privileged action |
| `cross_server` | Response-derived argument crosses servers |
| `delayed_malicious` | Attack after a benign delay |
| `low_and_slow` | Slowly increasing abnormal parameters |
| `gradual_poisoning` | Adaptive baseline-contamination attempt |

Each scenario declares its description, attack start, expected behavior, labels,
and cases. Labels do not override detector decisions, so misses remain visible.

## Commands

Run one scenario:

```powershell
python -m sentinel.cli experiment --seed 42 --scenario cross_server `
  --training-events 100 --validation-events 40 --test-events 40 `
  --output results/cross_server
```

Run all scenarios:

```powershell
python -m sentinel.cli experiment --seed 42 --scenario all --output results/all
```

Compare the lightweight rules baseline:

```powershell
python -m sentinel.cli experiment --seed 42 --scenario all --baseline rules --output results/rules
```

Real ablations are selected without source edits:

```powershell
python -m sentinel.cli experiment --scenario cross_server --without-causal --output results/ablations/no-causal
python -m sentinel.cli experiment --scenario intent_mismatch --without-intent --output results/ablations/no-intent
python -m sentinel.cli experiment --scenario capability_drift --without-attestation --output results/ablations/no-attestation
python -m sentinel.cli experiment --scenario gradual_poisoning --without-quarantine --output results/ablations/no-quarantine
```

Performance is kept separate:

```powershell
python -m sentinel.cli gateway-benchmark --requests 100
```

## Metrics and outputs

Every JSON result contains TP, TN, FP, FN, precision, recall, F1, false-positive
rate, attack detection rate, detection delay, risk/trust/intervention means,
evaluation and end-to-end latency, sequential throughput, AUROC, average precision
(reported as AUPRC), risk ECE, ROC/PR points, distributions, per-event decisions,
baseline state counts, configuration, and failures.

AUROC/AUPRC are `null` when both positive and negative labels are not present. The
framework reports risk calibration ECE; it does not claim that the current
uncertainty value is a calibrated attack probability.

Results are written under `<output>/<scenario>/<experiment-id>.json`, plus
`summary.json` and `summary.txt`. These fields directly support later risk, trust,
ROC, PR, drift, poisoning, ablation, and latency plots.

## Baselines and ablations

Implemented now:

- complete Sentinel adapter;
- stateless sensitive-argument/destructive-intent rule baseline.

The common offline comparison now executes Isolation Forest, One-Class SVM, dense
autoencoder, and constrained NumPy LSTM/Transformer baselines. The sequence encoders
are fixed after deterministic initialization and only their reconstruction heads are
optimized; they must not be described as fully end-to-end trained deep networks.

Engine switches provide real ablations for intent, causal reasoning, active
attestation, uncertainty, and protected quarantine learning. Disabling quarantine
allows adaptive observations to enter learning, which enables direct poisoning-
resistance comparison.

## Current limitations

- The safe MCP servers are representative mocks, not enterprise workloads.
- Scenario sizes are small by default and are not a publication-scale benchmark.
- Legitimate drift currently changes tool frequency and sequence; adaptation-time
  analysis is recorded through per-event decisions but needs a dedicated aggregate.
- The rules baseline is intentionally simple; learned comparative baselines remain.
- Transport latency varies by host even though security telemetry is seeded.
- AUROC/AUPRC from small or highly imbalanced scenarios are unstable.
- Offline comparisons use a model-wide p99 normal-validation threshold. The real-
  gateway scenario runner retains its separate enforcement-band methodology.
- Cross-server labels rely on a deterministic canary, not sensitive production data.
