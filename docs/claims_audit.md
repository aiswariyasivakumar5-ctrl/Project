# Claims audit

## A. Supported by current evidence

These are descriptive experimental or implementation claims, not universal production claims:

- The prototype implements preflight and post-response enforcement for its documented HTTP JSON-RPC MCP subset.
- In-process direct gateway dispatch produces exact numerical, verdict, and trust equivalence with live loopback HTTP socket transport while preventing OS TCP port exhaustion.
- The engine combines behavioral deviation, intent mismatch, session sequence evidence, causal propagation, attestation evidence, uncertainty, quarantine, and dynamic trust.
- Twenty-seed synthetic experiments (20001–20020) reproduce the retained metrics in the master publication tables.
- At the evaluated operating point, Sentinel achieves an empirical FPR of 0.0000286 (observed 1 false positive across 35,000 normal test events across 20 comparison seeds 20001–20020; exact Clopper-Pearson 95% binomial upper bound $\le 0.0159\%$) and an aggregate recall of 0.6667 on the publication test workload.
- **All-or-Nothing Recall Profile (8 of 12 detected, 4 missed entirely):**
  - Exactly 8 attack families are fully detected with 1.0000 recall (125/125 detected each = 1,000/1,000 events): `intent_mismatch`, `tool_poisoning`, `policy_injection`, `data_exfiltration`, `schema_mutation`, `destructive_operation`, `cross_server`, and `delayed_malicious`.
  - Exactly 4 attack families are not detected at all with 0.0000 recall (0/125 detected each = 0/500 events): `abnormal_sequence` (order-invariant feature representation blind spot), `capability_drift` (client-controlled capability digest), `low_and_slow` (sub-threshold gradual parameter growth), and `gradual_poisoning` (gradual baseline contamination without threshold breach). Total recall: $1,000 / 1,500 = 0.6667$.
- Dense Autoencoder, Transformer, and LSTM baselines achieve statistically significantly higher recall (1.0000) and F1 than Sentinel ($p = 0.000002$, Holm-adjusted $p = 0.000010 < 0.05$), but at the cost of high false positive rates ($7.71\% - 7.82\%$).
- One-Class SVM does not achieve a statistically significant difference against Sentinel on this workload ($p = 0.927279$).
- Isolation Forest collapses completely under validation-calibrated thresholds ($F_1 = 0.0000 \pm 0.0000$).
- **Scenario-Level Test FPR Breakdown (v2 & v3 Novelty Matrices):**
  Full Sentinel achieves an empirical FPR of 0.0000 in specific named scenarios only. In `schema_stable_response`, test FPR is 0.9997 (baseline is 1.0000) because policy-injection payloads are present on every call:

| Scenario | Full Sentinel Test FPR | Without Capability Trust FPR | Baseline Test FPR | Mechanism / Explanation |
| :--- | :---: | :---: | :---: | :--- |
| `capability_laundering` | **0.0000** | **0.9952** | 0.0000 | Per-capability trust isolates export tool; read tool remains benign. Without capability trust, server-wide trust collapses. |
| `coordinated_servers` | **0.0000** | 0.0000 | 0.0000 | Causal graph isolates server B export; benign server A reads remain unhindered. |
| `delayed_causal_misuse` | **0.0000** | 0.0000 | 0.0000 | Expired provenance token isolates delayed delete; legitimate reads at $t=105$ allowed. |
| `legitimate_upgrade` | **0.0000** | 0.0000 | 0.0000 | Benign argument extension promoted automatically under dual memory. |
| `provenance_replay` | **0.0000** | 0.0000 | 0.0000 | Consumed provenance token blocks replay; initial authorized use allowed. |
| `schema_stable_response` | **0.9997** | 0.9997 | **1.0000** | Embedded instruction in response payload triggers policy rule on every call. |

- **Novelty Matrix Statistical Power (v1/v2 vs v3):**
  The 5-seed novelty matrices (v1 and v2, seeds 42, 123, 456, 789, 1001) were strictly exploratory with deterministic fixtures and an exact sign-flip floor of $p = 0.0625$. The 20-seed novelty matrix v3 (seeds 30001–30020, 1,320 total phase records) adds genuine seed-driven randomization and establishes confirmatory significance ($p = 1.91 \times 10^{-6}$, Holm $p = 7.63 \times 10^{-6} < 0.0001$) for capability isolation and single-actor poisoning, while confirming null results ($p = 1.0000$) for intent consistency and review requirements. The 5-seed (42..1001) and 20-seed (30001..30020) matrices evaluate separate seed sets and are never framed as before/after improvements.
- **Adaptive Poisoning & Dual Memory Caveats (v3):**
  In these synthetic scenarios, dual memory successfully blocks single-actor promotion (0.0 updates admitted vs 3,000 updates without dual memory). However:
  1. Colluding identities rotating caller identities bypass quarantine (12.0 updates admitted in matched poisoning).
  2. Mixed traffic bypasses quarantine (4.0 updates admitted).
  3. Shape-equivalent drift is not blocked (3.0 updates admitted).
  4. `legitimate_upgrade` is promoted automatically without review unless `approval_required` is enabled.
- Learning-admission coordination matches a standard transactional baseline identically (0/6 ineligible admitted, 0/2 eligible withheld) and provides no algorithmic or security advantage over classical transaction serializability.
- The causal hard floor creates a tied-score validation calibration effect.
- The evaluated fusion candidates did not justify replacing production fusion.
- The constrained sequence baselines trade increased recall for roughly 7.9% FPR.

## B. Plausible hypotheses requiring additional validation

- Intent-conditioned and cross-server causal evidence may improve security on independently sourced MCP traffic.
- Quarantine may improve resistance to broader adaptive poisoning strategies when combined with cryptographic sybil-resistance.
- Hardware-bound attestation could strengthen server identity and capability assurance.
- Hierarchical/cross-session temporal models may improve subtle sequence detection.
- Alternative preregistered calibration may reduce causal-floor ties without sacrificing low FPR.
- The combined MCP-specific mechanism may be technically distinctive; prior-art and patent counsel review are required.

## C. Claims that must not be made

- “Statistically significantly better than all baselines.”
- “Production-ready,” “enterprise validated,” or “validated on real enterprise traffic.”
- “Zero false positives,” “100% attack detection,” or “works on all MCP attacks.”
- “Fully trained LSTM/Transformer superiority” or a general conclusion about end-to-end temporal deep learning.
- “Formally proven poisoning resistance” or general immunity to distributed/colluding poisoning.
- “Algorithmic or machine learning advantage for learning admission over classical transactional concurrency control.”
- “Hardware-backed attestation” or cryptographically proven server identity.
- “Complete MCP protocol support.”
- “Post-response enforcement reverses side effects.”
- “Patentable” or “novel” as a legal conclusion.

## Claim taxonomy

| Type | Meaning | Acceptable phrasing |
|---|---|---|
| Descriptive result | Number observed in retained experiment | “Mean recall was 0.6667 across five seeds.” |
| Experimental evidence | Reproducible behavior within declared setup | “The synthetic adaptive workload provides evidence of quarantine preventing baseline updates.” |
| Research hypothesis | Proposed generalization needing new evidence | “Cross-session temporal modeling may improve sequence detection.” |
| Production claim | Reliability/security in deployment | Not supported by current evidence. |
