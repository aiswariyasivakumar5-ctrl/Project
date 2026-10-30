# Research questions and evidence-based answers

## RQ1 — Can the gateway enforce runtime MCP security decisions?

- Experiments: real HTTP integration tests, failure-path tests, real-gateway scenarios.
- Evidence: request/response validation, destructive preflight blocking, response withholding, causal traces, capability challenges, and fail-closed analysis are exercised by tests.
- Answer: yes, for the implemented single-message HTTP JSON-RPC subset and safe local servers.
- Limitation: this is not proof for full MCP transport coverage or production adversaries.

## RQ2 — Does Sentinel occupy a different operating point from anomaly baselines?

- Experiments: five-seed publication baseline and sequence comparisons.
- Evidence: Sentinel recall 0.6667/FPR 0.0001; Dense AE 0.8837/0.0783; LSTM 0.7700/0.0792; Transformer 0.7819/0.0786.
- Answer: yes descriptively—Sentinel is substantially more conservative at the retained thresholds.
- Limitation: synthetic workloads provide no enterprise cost function, and no p < 0.05 comparison is available.

## RQ3 — What do intent and causal components contribute?

- Experiments: six-way held-out ablation and calibration diagnosis.
- Evidence: without intent produces zero operating detections; without causal raises recall to 0.9167 but FPR to 0.0789. The causal floor controls validation calibration.
- Answer: intent is essential to current threshold-level detections; causal logic supplies cross-server evidence and a conservative operating constraint, but its hard floor creates a calibration limitation.
- Limitation: component effects interact with thresholds, so ablation differences are not isolated causal effects in a statistical-causal sense.

## RQ4 — Does quarantine resist adaptive baseline poisoning?

- Experiments: five-seed adaptive gradual-poisoning curves.
- Evidence: Full has 0 malicious baseline-update rate; without quarantine has 1.0 in every seed (`p=0.0625`).
- Answer: the implemented quarantine prevents baseline updates in this synthetic adaptive workload.
- Limitation: not formal poisoning resistance and not validated against broader adaptive attackers.

## RQ5 — Where is Sentinel strongest and weakest?

- Evidence: held-out per-attack recall.
- Answer: strongest (recall 1.0) on intent mismatch, cross-server, exfiltration, destructive, policy/schema/tool poisoning, and delayed malicious behavior. Weakest (0.0) on capability drift, low-and-slow, gradual poisoning under frozen TEST, and abnormal sequence.
- Limitation: binary family templates do not measure severity or real-world prevalence.

## RQ6 — Do temporal sequence models add meaningful advantage?

- Experiments: five-seed constrained LSTM/Transformer comparison and session probes.
- Evidence: they improve aggregate recall over Sentinel and Transformer improves gradual-family recall, but both have ~7.9% FPR and zero abnormal-sequence/capability-drift recall; Dense AE remains stronger overall.
- Answer: not clearly under this setup. Benefits are family-specific and do not preserve Sentinel's low-FPR operating point.
- Limitation: fixed NumPy encoders are not equivalent to fully end-to-end trained deep networks.

## RQ7 — Can validation-only fusion fix the causal-floor calibration issue?

- Experiments: Milestones 6A/6B.
- Evidence: additive fusion raises recall but FPR to 0.0758; monotonic midrank preserves control decisions.
- Answer: no evaluated candidate justified replacement.
- Limitation: the small principled candidate set does not exhaust calibration methods.
