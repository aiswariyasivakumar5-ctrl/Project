# Proposed research contributions

These are implemented or evaluated contribution candidates. “Novel” is not used in the patent/legal sense; prior-art validation is still required.

1. **MCP-specific runtime enforcement architecture.** A transparent JSON-RPC gateway maps MCP tool calls and responses into security analysis, proportional decisions, and evidence-linked audit records.
2. **Intent-conditioned enforcement.** Declared user intent is compared with tool/argument behavior and participates in both preflight destructive-action controls and runtime scoring.
3. **Cross-server causal behavioral reasoning.** Bounded temporal provenance links response-derived tokens and server transitions, producing traceable causal evidence.
4. **Dynamic trust and proportional actions.** Runtime evidence updates server trust and selects allow, observe, confirm, sandbox, or isolate behavior.
5. **Active capability attestation experiment.** Uncertainty/risk can trigger a side-effect-free nonce challenge tied to an enrolled capability digest. This is experimental and not hardware-bound.
6. **Quarantine-protected online learning.** Suspicious observations are prevented from updating behavioral baselines; the adaptive experiment directly compares baseline-update behavior.
7. **Evidence-linked evaluation methodology.** Seeded TRAIN/VALIDATION/TEST separation, fixed validation calibration, matched-seed inference, ablations, adaptive phases, and diagnostic replays expose both strengths and weaknesses.
8. **Empirical calibration finding.** The work identifies how a discrete causal hard floor can dominate high-quantile validation calibration under strict threshold semantics.

The combined mechanism is a claimed contribution requiring prior-art validation. Individual ingredients—autoencoders, anomaly thresholds, trust scores, attestation, provenance graphs, and quarantine—are established concepts and should not independently be presented as novel without evidence.
