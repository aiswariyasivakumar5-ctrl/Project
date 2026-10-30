# Novelty milestone: evidence-gated capability trust

Historical design milestone. The original promotion rule below remains the
historical experiment policy; current runtime defaults additionally require
operator review and fresh attestation. See [runtime_controls.md](runtime_controls.md)
and [project_status.md](project_status.md) for current behavior and remaining work.

This opt-in extension does not retune the approved Sentinel detector, thresholds,
baselines, or retained results.

Each MCP call creates a hash-linked provenance claim binding intent, capability,
input, output, server, and session. Counterfactual intent consistency is fused with
the approved verdict. Enforcement maintains trust per capability, allowing a benign
tool to remain usable when another tool on the same server is restricted.

Learning has trusted and candidate memories. A new behavioral fingerprint is
promoted only after observations from multiple independent sessions and at least one
attestation. High-risk or failed candidates are rejected.

Research hypotheses: capability-specific trust limits collateral denial; evidence
gating resists single-session poisoning; intent provenance detects unsupported side
effects. Costs include slower legitimate adaptation and dependence on session and
attestation independence. Evaluate capability laundering, delayed causal misuse,
coordinated servers, distributed poisoning, legitimate upgrades, and schema-stable
malicious responses under the existing train/validation/test rules. Store new results
separately under `results/novelty/`.

This implementation is not proof of patentability. Perform a professional prior-art
search, preserve conception records for all inventors, and keep it private until the
filing strategy is settled.
