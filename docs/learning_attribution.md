# Learning attribution — October 4, 2026

The adaptation runner now observes successful `learn_approved` calls and associates
each learned event with its original fixture index, request hash and private label.
The label lookup is held by the research observer, outside the detector and candidate
memory. Promotion replay therefore attributes each buffered event to its own label,
even when a later benign request triggers the batch.

Matching uses server, session, tool, exact arguments and intent. Response and runtime
metadata are excluded because the gateway constructs those fields. Ambiguous fixture
identities are rejected before observation; unknown sources are recorded explicitly.
This observer is scoped to the sequential research runner and restored on exit. It
is not a production concurrent audit API. Fixture identities are unique per stream;
source indexes are scoped by the containing seed/policy/stream artifact.

Every row contains `learned_events`. Attribution counts must equal that row's actual
model-update delta. Contamination is malicious learning updates divided by total
adaptive updates, including replay multiplicity. It is undefined when no updates
occur or attribution is incomplete. This measures update admissions, not malicious
fraction of model weights or unique retained memory entries. Enrollment is excluded.
Unknown source records and missing update records invalidate completeness; inspect
the update delta and attributed count together.

## Verification and result

Full suite: 206 tests passed in 92.354 seconds. Retained research verification
passed for 43 files.

Regression coverage includes malicious buffered replay triggered by a benign call,
duplicate source rejection, failed update handling, method restoration, undefined
metrics and unchanged model parameters with observation enabled.

The separate live run `results/adaptation/attribution-20261004` completed all 16
cells at the same seed 20001, 100 enrollment and 30 adaptive events with scoped read
permissions. Attribution is complete in every cell. Every adaptive policy had zero
malicious learning updates (contamination 0 among its admitted updates). Frozen
policies had no updates, so contamination is undefined. This does not distinguish
gated learning from immediate eligible learning: both admitted the same number of
updates. Malicious intervention remains zero in the attack-bearing streams.

No poisoning-resistance superiority follows from this run. The current fixtures
exercise hidden intent and the general learning eligibility filter; broader
experiments must cause meaningful candidate promotion, add reviewer timing, and
measure benign recovery alongside observable harmful actions.
