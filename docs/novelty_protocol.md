# Novelty evaluation protocol — draft v1

Prepared September 17, 2026. **Draft for team review, not a preregistration or
release approval.** Earlier development outcomes are already known; they are not
confirmatory evidence for this protocol. No publication-scale run is authorized
as a frozen, preregistered experiment by this document alone.

## Scope and hypotheses

Evaluate the existing runtime gateway and six existing variants. No new detector,
identity mechanism or runtime enforcement threshold is introduced.

| Hypothesis | Prespecified comparison | Primary outcome |
|---|---|---|
| Capability isolation limits collateral denial | `full` vs `without_capability_trust`, capability_laundering TEST | Difference in benign false-positive rate |
| Evidence-gated memory reduces single-actor poisoning | `full` vs `without_dual_memory`, distributed_poisoning ADAPTIVE | Difference in model-update count |
| Intent consistency improves misuse detection | `full` vs `without_intent_provenance`, coordinated_servers TEST | Difference in malicious-call recall |
| Review requirement prevents unapproved promotion | `approval_required` vs `full`, multi_actor_poisoning ADAPTIVE | Difference in model-update count |

These are falsifiable tests, not conclusions. Some fixtures may provide weak or
uninformative differences. Report null and adverse outcomes without replacing
scenarios or changing thresholds. Approval-required runs receive no operator
review fixtures, so legitimate_upgrade is an unapproved benign control expected
to withhold learning as well. Live regression tests separately cover reviewed
positive promotion and recovery; this study does not estimate recovery efficacy.

## Fixed configuration for proposed larger run

- Seeds: 42, 123, 456, 789, 1001, matching the retained study convention. These are
  proposed reproducibility seeds, not a claim that they were unseen during development.
- All six variants and all eight scenarios in `novelty_experiment.py` and
  `novelty_scenarios.py`; record component settings per result.
- Per variant/seed: 5,000 trusted TRAIN events, 1,000 benign VALIDATION events,
  scenario size 3,000 for TEST and separately declared ADAPTIVE phases. Some
  generators emit a different actual number; report recorded counts, not this input.
- One shared post-TRAIN checkpoint for each variant/seed; VALIDATION is frozen.
  Each scenario/phase independently restores the complete post-TRAIN checkpoint.
  TEST never learns. Security trust/history still evolves within a phase.
- Seeded workload latency drives features; separately measured transport and
  analysis latency are descriptive performance data.
- Record Git revision, dirty status, Python/NumPy/platform, source hashes,
  configuration, workload hashes, learning-state hashes and event decisions.
- Require a new output directory. Retain partial failed-run artifacts. Do not
  overwrite prior results; report failures and any rerun reason. Never silently
  discard a failed seed or choose a replacement based on observed outcomes.

## Validation-only threshold workflow

Primary security outcomes use **actual gateway interventions under the existing
fixed action bands**. They do not use an optimized test threshold.

The prespecified secondary score evaluation uses a normal-validation quantile:
select the 99th percentile with NumPy `method="higher"`, then predict positive
only for scores **strictly greater** than that threshold. This is the same rule
already used by the offline comparison. Ties at the boundary are negative. Fit
one scalar per variant/seed, across validation servers, and freeze it before any
scenario TEST or ADAPTIVE observations. No per-scenario fitting, attack-label
selection, test-set tuning or runtime gateway policy change is allowed.

The runner's optional `--validation-fpr 0.01` enables this secondary report. The
default omits score calibration to preserve earlier development commands. Save a
calibration artifact before scenario execution, including the validation scores,
their hash, the workload hash, threshold, target and observed validation FPR.
Reject empty, malicious-labeled, nonfinite or out-of-range validation data.
The target is an empirical validation operating point, not a population FPR guarantee.

Report calibrated score metrics separately from actual interventions: a low score
does not override authorization or trust blocks. For ADAPTIVE scores, label results
as online evaluation under a threshold frozen before adaptation, not frozen TEST.

## Analysis plan

- Unit of inference: seed. Pair the same seed IDs across variants. Report all
  per-seed values and mean paired differences for the four primary comparisons.
- Use the existing exact two-sided paired sign-flip test; apply Holm correction
  across the four primary hypotheses as one family. Use existing seed-cluster
  bootstrap mean/difference intervals (95%, 20,000 resamples, RNG seed 2026).
- Five seeds have low statistical resolution: the smallest two-sided exact
  sign-flip p-value with five nonzero pairs is 0.0625. Do not claim p<0.05
  significance, even before multiplicity correction. Descriptive effect sizes
  and limitations are required; increasing seeds requires a protocol amendment
  before additional results are inspected.
- Secondary outcomes: confusion counts, precision/recall/F1 where defined,
  benign FPR, AUROC/AUPRC when both labels occur, gateway intervention rate,
  model-update counts, and latency distributions. Do not average undefined
  recall/FPR as zeros just because the generic metric schema uses zero denominators.
- The runner's existing exploratory F1 comparisons are not the four primary
  hypothesis tests. The eventual reporting step must label and separate them.
- No causal claim that zero model updates means an attack was denied. Independent
  compromised actors can remain behaviorally indistinguishable from benign users.

## External data and release gates

Independent MCP traces need a dataset identifier, source URL/path, license or
permission, collection provenance, redaction policy, labels and a session/server
split plan established before evaluation. No such dataset has been supplied or
verified for this milestone; synthetic fixtures do not satisfy this requirement.

Before the larger run is called final: technical owners review mechanisms and
threat assumptions; the team approves configuration and primary comparisons;
register the protocol at a selected registry or institutional system; record its
identifier/time; approve a clean tested Git commit and release tag. None of those
human approvals are asserted here. No registry submission or teammate message
has been sent. Independent prior-art review and final figures/claims audit remain
separate checklist items.
