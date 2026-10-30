# Novelty evidence checklist — October 16, 2026

The implementation and focused validation milestones below are complete locally.
The broader novelty/security claim is **not yet established**. Test success verifies
implemented behavior; it does not establish research superiority or patentability.

| Milestone | Status | Evidence |
| --- | --- | --- |
| Existing intent/provenance, capability trust and learning gates | Implemented | Existing engine/gateway tests |
| Trained-model benign promotion | Verified in narrow fixture | 20-cell promotion factorial; replay attribution and changed weights |
| Matched malicious-event ingestion | Complete; adverse outcomes retained | 105-cell matched study |
| Feature-changing poisoning and isolated probes | Complete; no recall loss observed | 45-cell degradation study |
| Single-identity candidate safeguard | Narrow benefit observed | Zero malicious updates versus 12 for immediate learning |
| Collusion and post-promotion poisoning resistance | Not demonstrated | Gated policies accepted malicious-source updates |
| Application-verified learning | Narrow synthetic control complete | 100 cells; simple verified-immediate matches combined protection with less delay; not response blocking |
| Limited verification-budget pilot | 480/480 offline cells complete; no significant superiority | `verification_budget.md`; first-available has lower mean malicious ingestion than uncertainty; probe recall has floor effect |
| Independent reviewer evidence | Pending | Current review policies are simulated/oracle or blanket approvals |
| Publication-scale novelty ablations and paired inference | Pending | Prior full-scale attempt failed; small diagnostics do not replace it |
| Independent real MCP trace validation | Pending: no permissioned source available | User confirmed no traces/test server; synthetic controls do not replace them |
| Targeted prior-art comparison | Updated; independent/legal review pending | `prior_art_comparison_20261016.md` records inspected sections and retrieval limits |

Do not describe the project as closing the entire runtime-security gap. The current
defensible claim is an implemented, inspectable evidence-gated learning framework
with reproducible demonstrations of both successful promotion and important failure
modes. Strengthening the claim requires a mechanism that addresses those failures,
then frozen evaluation, not more favorable wording or selective results.

See [promotion](promotion_factorial.md), [matched poisoning](matched_poisoning.md),
and [model effects](degradation_study.md). Historical results and evaluation splits
remain unchanged. No human review, inventorship decision, or conference acceptance
is implied by completion of these local milestones.

October 16 full-scale attempt: stopped after 20/330 phases on denied provenance
issuance. The runner now records denial without minting authority; the failed
evidence is retained. A separate corrected rerun is underway, not yet complete.
See `independent_review_packet.md` for the human handoff and `verified_learning.md`
for the most recent controlled comparison.
