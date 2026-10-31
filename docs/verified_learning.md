# Application-verified learning diagnostic

October 16, 2026. Exploratory synthetic development evidence, not a held-out
real-world evaluation or a patentability conclusion.

## Mechanism and boundary

`VerifiedLearningEngine` is an opt-in wrapper. A trusted application-side callback
must explicitly return `True` before an event can enter learning. Missing,
unsupported, failed, or exception-producing verification withholds learning.
Buffered candidate events are reverified before replay; already-promoted shapes
do not bypass per-event verification. Callbacks receive copies of events.

The supplied reference verifier only checks the mock calculator's addition result.
It is independent of attack labels, but relies on an available trusted reference
implementation. It does not generalize to arbitrary tools, validate user intent,
or authenticate the application's verifier. It **does not block bad responses**.
Callbacks must be bounded and trusted: this wrapper provides no hard callback
timeout. Revoked queued evidence can stall a candidate and requires operator
handling. Existing production defaults and historical variants are unchanged.

## Completed comparison

Artifacts: `results/adaptation/verified-learning-20261016/` contains the protocol,
source/workload hashes, execution record, individual event evidence, summary,
and `tables.md`. All 100 cells completed: five training-order seeds, four policies,
five streams, 12 adaptive calls per stream. Enrollment uses 100 integer calls;
adaptive streams use the same existing synthetic arithmetic workload family.
These are not five independent real-world datasets.

Every seed had the following malicious-source learning update counts:

| Stream | Immediate | Dual-memory gated | Verified immediate | Verified gated |
| --- | ---: | ---: | ---: | ---: |
| Clean | 0 | 0 | 0 | 0 |
| Single identity | 12 | 0 | 0 | 0 |
| Colluding identities | 12 | 12 | 0 | 0 |
| Mixed | 4 | 4 | 0 | 0 |
| Late sparse | 3 | 3 | 0 | 0 |

Both verified policies learned all benign events in these streams. Verified
immediate started benign learning at event step 0. Verified gated started at
step 2 for clean and late-sparse streams, and step 3 for mixed streams.
Neither verified policy blocked malicious responses: malicious intervention
rates remained zero. Ingestion prevention is not response protection or measured
downstream model-degradation prevention.

**The simple verifier explains the observed protection.** Dual memory added no
malicious-ingestion advantage over verified immediate in this diagnostic and
delayed benign adaptation. This does not support claiming the combination is
superior or novel. The protocol specified descriptive analysis; no confidence
intervals, p-values, or significance claims are inferred from these counts.
The reused generic protocol/report mentions oracle review; none of these four
selected policies received review grants.

## Reproduce

```powershell
python -m sentinel_research.verified_learning_study --output results/adaptation/verified-learning-new
python -m sentinel_research.matched_poisoning_report --output results/adaptation/verified-learning-new
python -m unittest discover -s tests -v
```

Use a new output directory; do not overwrite retained runs. No test-driven
threshold selection or baseline result replacement was performed.

Initial local verification: all 231 tests passed in 71.167 seconds on October 16,
2026. After the experiment runner/reporting fixes, all 235 tests passed in 227.487
seconds. The retained-research verifier reported PASS for 43 files. Commit
`4e5cdb3` passed all four Windows/Ubuntu and Python 3.11/3.14 CI jobs in
[run 38915893770](https://github.com/snehathesingh-stack/MCP-Runtime-Sentinel/actions/runs/38915893770).

## Remaining evidence

- User confirmed no permissioned real MCP traces/test server are available.
  Independent real-world validation remains pending, not replaced by these runs.
- Assess verifier coverage, cost, mistakes, unavailability, and semantic attacks
  on tools without a simple exact reference implementation.
- Complete the unchanged publication-scale novelty matrix and its planned
  statistical analysis; this small diagnostic is not that matrix.
- Complete primary-source prior-art comparison, independent team review, and
  claim drafting with qualified patent advice before claiming patentability.
