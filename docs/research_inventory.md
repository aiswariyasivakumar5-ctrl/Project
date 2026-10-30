# Master research inventory

## Status vocabulary

- **Approved/retained:** source for final quantitative reporting.
- **Diagnostic:** explains behavior; not a replacement publication baseline.
- **Exploratory/smoke:** development evidence; excluded from final headline tables.
- **Historical:** valid earlier measurement retained for provenance.

## A. System implementation milestones

| Evidence | Source | Status | Final use |
|---|---|---|---|
| Runtime engine: behavior, intent, sequence, causal graph, trust, uncertainty, attestation, quarantine | `sentinel/engine.py` and unit tests | Approved implementation | Architecture and mechanism claims |
| HTTP JSON-RPC gateway, validation, forwarding, preflight/post-response enforcement and audit | `sentinel/gateway.py`, `sentinel/jsonrpc.py`, gateway tests | Approved implementation | Gateway functionality claims |
| Safe server and integration environment | `sentinel/mock_server.py` | Research fixture | Method description only |
| Scenario generator | `sentinel/scenarios.py`, `sentinel/workload.py` | Approved synthetic workload | Evaluation scope, not enterprise validation |

## B. Evaluation milestones

| Result | Source | Seeds / sizes | Status | Final report |
|---|---|---|---|---|
| Early real-gateway research scenario | `results/research_milestone` | seed 42; smaller experiment-specific sizes | Exploratory | Implementation evidence only |
| Smoke classical comparison | `results/baselines_smoke` | 1 seed; reduced sizes | Smoke | No headline metrics |
| Earlier multiseed comparison | `results/baselines_multiseed` | 5 seeds; publication sizes | Superseded by approved publication directory | No |
| Classical/Sentinel publication comparison | `results/baselines_publication` | 5 seeds; TRAIN 5,000, VALIDATION 1,000, requested TEST 3,000 | Approved/retained | Yes |
| Sequence smoke | `results/sequence_smoke` | 1 seed; 200/50/100 | Smoke | Verification only |
| Sequence publication comparison | `results/baselines_sequence` | 5 seeds; 5,000/1,000/3,000 requested | Approved constrained comparison | Yes, with implementation caveat |

The workload adds benign causal context for some families, so realized TEST length may exceed the requested count. This is established framework behavior, not a discrepancy.

## C. Baseline models

| Model | Source/result | Status |
|---|---|---|
| Full Sentinel | `results/baselines_publication/sentinel` | Approved control |
| Isolation Forest | `results/baselines_publication/isolation_forest` | Approved baseline |
| RFF One-Class SVM | `results/baselines_publication/one_class_svm` | Approved approximation baseline |
| Dense NumPy autoencoder | `results/baselines_publication/dense_autoencoder` | Approved baseline |
| Constrained NumPy LSTM | `results/baselines_sequence/lstm` | Approved comparison; fixed encoder limitation |
| Constrained NumPy Transformer | `results/baselines_sequence/transformer` | Approved comparison; fixed encoder limitation |

## D. Ablations

`results/ablations_publication` contains Full, without intent, without causal, without attestation, without uncertainty, and without quarantine for all five seeds and publication sizes. Frozen TEST metrics are approved. `aggregate/adaptive_curves.json` and `adaptive_statistics.json` separately contain legitimate drift and gradual-poisoning learning behavior. Both appear in the final report, never merged.

## E. Statistical analyses

`results/statistical_analysis/baseline_statistics.json` contains five-seed cluster bootstrap intervals and matched exact sign-flip tests for classical baselines. `results/ablations_publication/aggregate/statistics.json` contains corresponding ablation inference. `results/sequence_publication/sequence_analysis.json` applies the same seed-paired methodology to sequence comparisons. Approved for descriptive uncertainty/inference; no p < 0.05 finding.

## F. Fusion/calibration studies

| Study | Source | Seeds / sizes | Status | Final use |
|---|---|---|---|---|
| Threshold/component diagnosis | `results/tradeoff_diagnostics` | 5 seeds, publication sizes; adaptive trajectories use documented smaller auxiliary setup | Diagnostic | Explain causal floor/ties and misses |
| Validation-only fusion candidates | `results/fusion_study` | 5 seeds, publication sizes; gateway 100 requests | Approved diagnostic comparison | Reject replacement candidates |

Later replay ranking metrics are not substituted for approved publication AUROC/AUPRC.

## G. Sequence studies

`results/baselines_sequence` is the retained five-seed result. `results/sequence_publication` contains combined six-model tables, session probes, legitimate-drift auxiliary analysis, and exact paired comparisons. `results/sequence_smoke` is excluded from headline metrics. The fixed-encoder constraint must accompany every interpretation.

## H. Gateway performance

- Historical figure-set benchmark: `results/figures/gateway_performance.json`, 100 requests.
- Latest retained benchmark: `results/fusion_study/results.json`, 100 requests, includes direct/gateway mean and p95 plus throughput.

Both are retained. The latest is used as the master measurement because of chronology, not because it is more favorable.

## I. Figures and tables

`results/tables` and `results/figures` are approved publication-oriented artifacts generated before sequence baselines. The ROC/PR/F1/FPR figures therefore compare only the four approved original models. They must not be labeled as six-model figures. `results/tradeoff_diagnostics/figures` are diagnostic and not part of the minimum final figure set.

Minimum retained figure set:

1. Architecture: use `docs/final_architecture.md` to redraw for venue format; no existing architecture SVG.
2. F1: `results/figures/f1_comparison.svg` (four-model historical figure; master table supplements sequence models).
3. FPR: `results/figures/false_positive_rate.svg` (same scope caveat).
4. Precision-recall: `results/figures/precision_recall.svg` (seed 42, four models—not five-seed aggregate).
5. Ablation: `results/figures/ablation_f1.svg`.
6. Per-attack recall: no retained SVG; use `results/final/master_per_attack.md` rather than generate an unnecessary plot.
7. Poisoning resistance: `results/figures/poisoning_resistance.svg`.
8. Gateway latency: `results/figures/gateway_latency.svg`, tied to the historical benchmark; master gateway document supplies latest values.

## Known limitations

The consolidated limitations are in `docs/final_limitations.md`. Key boundaries are synthetic traffic, five seeds, constrained sequence training, calibration ties, session-local evidence, weak difficult-family recall, experimental attestation, local unauthenticated audit, incomplete MCP transports, in-memory state, and no production deployment validation.
