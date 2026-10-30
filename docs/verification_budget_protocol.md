# Verification-budget study — exploratory protocol v1

Frozen design before this study's outcomes are inspected, October 16, 2026.
Not externally preregistered; earlier arithmetic fixture results are known.
Historical experiments and the running publication matrix are not modified.

Question: at equal verification budgets, does selecting the most uncertain eligible
observations improve benign adaptation without increasing malicious learning,
compared with first-available, periodic and random verification?

## Fixed design

- Offline prequential research harness using the existing Sentinel engine and
  trusted `learn_approved` hook, not an HTTP gateway deployment benchmark.
- Five seeds 51001–51005; 100 existing varied integer enrollment observations;
  96 adaptive observations per stream. Fresh order seeds, not independent real tasks.
- Streams: clean numeric drift; coordinated same-shape incorrect responses;
  mixed correct/incorrect responses; gradual feature-changing wrong responses.
- Six policies: never learn, verify every eligible event, first-available,
  periodic, random and uncertainty-ranked. Every eligible event has the same
  verification cost. First/random/periodic/uncertainty get at most two checks
  per eight observed events, with no carry-over. Never/every are reference
  floor/ceiling policies, not budget-matched competitors.
- All budgeted selectors decide at the end of each eight-event window. Uncertainty
  ranks descending with arrival-order ties; random samples without replacement;
  periodic selects window positions 0 and 4; first selects the first two eligible.
  No policy sees labels or future windows. Unused periodic slots are not reassigned.
- Eligibility uses the existing fixed risk < 0.42 learning band, successful
  side-effect-free responses, and no provenance/attestation violation.
- Feedback conditions: exact; four-event delay; deterministic 10% flipped answers;
  deterministic 25% unavailable answers. Feedback faults are assigned by seed and
  source index, independent of labels and selection policy. Failed/unavailable
  queries consume budget. Correctness comes from the trusted arithmetic verifier,
  not fixture labels. Faulty feedback deliberately violates that trust assumption.
- Selected events are deep-copied and bound to server/tool/capability digest.
  Before learning, enforce matching current digest, evidence TTL of 16 event steps,
  and at-most-once delivery. Deferred learning does not rewind sequence history.
  No indefinite post-stream drain: outstanding feedback is reported as pending.

## Outcomes and inference

Retain per-event selections, feedback, eligibility, update source index and delay.
Report query counts, malicious-source updates, benign-source updates, benign
learning coverage and delay, pending feedback, and prequential intervention FPR.
Fixed independent-history probes measure fitted-model effects before/after; do not
call training ingestion a security intervention or changes in risk a recall loss.
Latency is local offline compute only, not network overhead or human verifier cost.

Across each seed, average malicious and benign update counts equally over the four
streams and four feedback conditions. Primary family: uncertainty minus each of
first, periodic and random for each of those two outcomes (six comparisons).
Use existing 95% seed-bootstrap mean/difference intervals (20,000, RNG 2026), exact
two-sided paired sign-flip tests and Holm correction across all six. Five nonzero
pairs cannot yield two-sided p < 0.05. These are exploratory synthetic comparisons,
not population guarantees. Retain all cells and null/adverse results; no tuning,
seed replacement, partial-matrix aggregation or favorable scenario selection.

## Boundaries and next gate

Uncertainty may be a poor correctness signal. No advantage is assumed. Coordinated
identities are synthetic session labels, not authenticated independent actors.
Arithmetic verification is unusually easy. The harness does not implement human
review, production asynchronous callbacks, remote identity or response blocking.
An unavailable exact verifier is not magically replaced with ground-truth labels.
Before claiming novelty, compare the exact scheduler against budgeted active
learning/query selection and delayed-label online learning prior work, and obtain
independent review. Initial execution is a development pilot; a later held-out
evaluation requires an independently chosen workload and frozen revision.
