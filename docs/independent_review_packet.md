# Independent review handoff

Prepared October 16, 2026. **No reviews or approvals have been collected.**

Review the exact candidate Git commit, record reviewer identity and date, and
retain disagreements. Do not count the implementing assistant's tests as an
independent human review. Do not substitute simulated approval schedules for people.

## Mechanism reviewer

- Check atomic claim consumption, expiry, argument/session/tool binding and
  invalidation when causal evidence is evicted.
- Verify capability isolation does not silently widen authority for other tools.
- Check promotion replay, evidence revocation and post-promotion poisoning.
- Read `verified_learning.md`: withholding learning does not block responses;
  the trusted callback is a new trust assumption, not remote attestation.
- Record a reproducible issue or a pass with the relevant test and code path.

## Evaluation reviewer

- Check all required variant/seed/scenario/phase cells before aggregation.
- Confirm train/validation/test separation, frozen thresholds and no test tuning.
- Examine failed executions, not just successful output folders.
- Separate denial due to rejected origins from demonstrated stale/replay detection.
- Validate seed pairing and undefined/censored metrics. Five-pair exact tests
  cannot yield two-sided p < 0.05; events are not independent replicates.
- Preserve adverse results and the verified-immediate comparison.

## Research reviewer

- Verify `prior_art_comparison_20261016.md` against the linked original sources.
- Narrow claims to demonstrated technical effects; mark unverified distinctions.
- Do not claim production readiness, general poisoning resistance or patentability.

## External validation admission checklist

The user has no permissioned real traces or test server available. Before any
future collection, record permission/license, server versions, collection dates,
redaction, labels and labeler disagreements. Establish a session/server-based
held-out split before evaluation. Do not copy private traces into Git history.
Public prompt benchmarks are not automatically runtime trace datasets.

## Sign-off record (unfilled)

For each reviewer record: commit SHA; role; date; reviewed files/tests; findings;
unresolved concerns; approve/request changes; and any competing interests.
The team must choose the venue, authorship, protocol registry and patent counsel.
No external messages, registrations or submissions are authorized by this file.
