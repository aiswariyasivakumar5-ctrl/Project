# Matched learning and poisoning diagnostic — October 6, 2026

All **105 runs** completed: seven policies, five streams, three fixed
training-order seeds (31001, 31002, 31003). This is development evidence, not a
publication-scale or confirmatory evaluation. Production thresholds, detector
logic and historical experiment splits/results were not changed.

Verification: all **223 tests passed locally in 134.934 seconds**, including six
new fixture, matching, attribution-delay, review-schedule and failure-retention
tests. Retained research verification passed for 43 files. Remote CI was not run
for this local milestone.

## Protocol and implementation

The study reuses the live HTTP mock/gateway runner, varied integer enrollment,
checkpoint/restore and successful-update source attribution. Each policy has 100
enrollment calls; every stream restores its policy's enrolled checkpoint. Seeds
shuffle the same training inventory; they do not create independent real tasks.
Each stream contains 12 decimal-input calculator calls with matched arguments,
intent, sessions and fixed telemetry latency. No adaptive call is trusted enrollment.

The attacker controls the mock tool response, returning 3.1 instead of 3.0 while
keeping the manifest and response structure unchanged. The sparse stream returns
3.1, 3.2 and 3.3 at indices 6, 8 and 10. These are objectively wrong arithmetic
answers, not merely relabelled correct events. The malicious fixture labels are
used for research attribution, never as detector input.

- Clean: all 12 correct, with independent fixture identities.
- Single identity: 12 wrong answers attributed to one trusted fixture identity.
- Colluding: 12 wrong answers attributed to 12 distinct fixture identities.
- Mixed: wrong answers at indices 2, 5, 8, 11; other answers correct.
- Late sparse: six initially correct calls before sparse wrong answers begin.

Policies are frozen learning, immediate eligible learning, gated learning without
review, oracle review, delayed oracle review, blanket initial review (named
`mistaken_review`), and review withheld. Oracle grants only for the clean stream,
at index 0 or 3. It knows the entire scenario, including future contamination;
this is an unrealistic upper-bound control, not a deployable reviewer. Blanket
review grants at index 0 in every stream. In the late-sparse stream, the initial
calls are legitimate, so this also tests an approval followed by later compromise,
not necessarily an initially mistaken human decision.

The protocol and source/workload hashes are saved before the run. Event JSONL is
flushed after every call; failures retain status and do not produce a complete
summary. Existing output directories and rendered reports cannot be overwritten.

```powershell
python -m sentinel.matched_poisoning --output results/adaptation/new-matched-study
python -m sentinel.matched_poisoning_report --output results/adaptation/new-matched-study
```

## Findings

Exact per-seed tables: [retained results](../results/adaptation/matched-poisoning-20261006/tables.md).
The following counts were identical in all three seeds; they are **per seed**, not
confidence intervals or independent replications of real-world effectiveness.

| Stream | Immediate malicious-source updates | Gated malicious-source updates | Blanket-review malicious-source updates |
| --- | ---: | ---: | ---: |
| Single identity | 12 | 0 | 0 |
| Colluding | 12 | 12 | 12 |
| Mixed | 4 | 4 | 4 |
| Late sparse | 3 | 3 | 3 |

In clean streams, immediate, gated, oracle, delayed-oracle and blanket-review
policies each learned all 12 events. First learning occurred at index 0 for
immediate, 2 for gated/oracle/blanket-review, and 3 for delayed oracle. Frozen and
withheld policies learned nothing. Immediate learning is faster in this benign
control; delay is the cost of the other learning gates.

Oracle policies avoided malicious updates by withholding approval for every
attack-bearing stream, but also learned **no benign events** in mixed/late-sparse
streams. This is not successful selective adaptation. Frozen and withheld policies
also had zero malicious updates because they performed no adaptive learning.

All benign and malicious intervention rates were zero where applicable. A learning
restriction is not response blocking: even the single-identity control allowed
incorrect answers through. Manifest attestation does not establish answer correctness.

## Important measurement limit

The wrong responses have exactly the same extracted feature vector as correct
responses; a test verifies that equivalence. The current model uses response
structure/length rather than arithmetic semantics. Source-attributed malicious
updates therefore measure **ingestion of attacker-controlled events**, not induced
model degradation. This negative control exposes an observability boundary; it
does not establish resistance to feature-changing or model-degrading poisoning.

These are simulated trusted principals, not evidence that independent identities
are honest. Buffered replay counts are attributed to their original events rather
than to the label of the call that triggered promotion. Attribution was complete
for the rendered tables. Undefined contamination with zero updates remains null.

No p-values, confidence intervals, statistical superiority, patentability or broad
real-world security claims are made. Identical outcomes across three training-order
seeds are not grounds for declaring significance.

## Next work

1. Add a separately fixed feature-changing poisoning stream and frozen downstream
   probes to measure actual model degradation, while retaining this shape-equivalent
   negative control.
2. Evaluate reviewers that use available evidence rather than scenario labels or
   future knowledge, including approval followed by compromise.
3. Define and test additional independent correctness evidence before proposing a
   new defense; identity count and manifest attestation alone do not solve this case.
4. Only then freeze the mechanism for full ablations, independent traces and
   statistically justified evaluation. Keep these adverse results in the paper.
