# Limited-verification adaptation pilot

This is an isolated offline research extension, not a production gateway feature.
The [protocol](verification_budget_protocol.md) was written before pilot execution.
It tests an idea, not an established novelty claim. Historical thresholds and results
are unchanged; the separate live publication-scale experiment is unaffected.

## Implementation

`sentinel/verification_budget.py` selects from completed eight-event windows.
Budget-matched policies may request at most two verifications per window:
first-available, periodic, random and highest uncertainty. Never-learn and
verify-every-eligible-event are lower/upper-cost references. All policies, including
verify-every, dispatch at window boundaries in this pilot; it is not an
instant-on-arrival verification latency benchmark.

The trusted scheduler owns deep copies of evidence. It applies feedback only once,
checks server/tool/capability binding, and rejects expired evidence. Unknown or
failed verification never grants learning. Selected observations alone can reach
the existing `learn_approved` hook, without replaying historical sequence updates.
Faulty-verifier experiments intentionally test failure of the trusted verifier.

The offline runner measures prequential decisions, learning source counts, costs,
conditional adaptation delay and frozen fitted-model probes. It does not perform
HTTP requests, authenticate identities, implement a distributed verification service,
or block responses. Its callback still executes synchronously; delayed answers are
simulated by delaying application of feedback. Source labels are for measurement
only; a regression test flips them while checking identical choices and learning.

## Reproduce

```powershell
python -m unittest discover -s tests -p 'test_verification_budget*.py' -v
python -m sentinel_research.verification_budget_study --output results/adaptation/verification-budget-new
```

The output directory must not exist. The runner records the protocol text/hash,
source hashes, per-cell workload hashes, per-event selections/deliveries and
execution status. Only a complete 480-cell matrix produces `statistics.json`
and `REPORT.md`. Five matched seeds are the inference unit; six planned comparisons
share Holm correction. Do not treat 46,080 replayed adaptive observations as that
many independent experiments.

## Interpretation cautions

- A fixed maximum budget does not guarantee identical expenditure: eligibility
  and unused periodic slots can differ. Compare the recorded query counts too.
- The uncertainty quantity is Sentinel's existing heuristic, not calibrated
  probability of response incorrectness.
- Drift scales change deterministically; seed differences mainly change enrollment
  order, random selection and simulated feedback faults, not task diversity.
- Candidate TTL and scope checks have unit coverage. The pilot workloads do not
  themselves vary capability digests or exceed the TTL; do not claim measured
  benefits from those safeguards based on this matrix.
- Probe recall/FPR have only four attack and two benign probes. Mean learning delay
  conditions on learned benign events and must be read alongside coverage/censoring.
- Arithmetic has an unusually easy reference verifier. There are no permissioned
  real traces, independent reviewers or real asynchronous verifier measurements.

The [prior-art screen](verification_budget_prior_art.md) identifies substantial
existing work on uncertainty selection, verification latency and poisoning-aware
active learning. Those ideas are not claimed as inventions. Full-text comparison,
stronger published baselines and independent validation remain necessary.

## Completed pilot results

`results/adaptation/verification-budget-20261016` completed all 480 cells. Its
`REPORT.md` contains the full matrix and paired intervals/tests; `statistics.json`
contains per-seed outcomes. Across equally weighted stream/feedback cells:

| Budgeted policy | Queries | Malicious updates, mean [95% CI] | Benign updates, mean [95% CI] |
|---|---:|---|---|
| First available | 24 | 0.1625 [0.0625, 0.2875] | 13.2125 [12.8875, 13.4750] |
| Periodic | 24 | 0.3125 [0.1750, 0.4625] | 11.6000 [11.2750, 11.9625] |
| Random | 24 | 0.2875 [0.2000, 0.3750] | 13.1750 [12.7000, 13.6125] |
| Uncertainty | 24 | 0.2000 [0.0875, 0.3125] | 13.2875 [13.0000, 13.5750] |

Uncertainty minus first-available: malicious updates +0.0375, benign updates
+0.0750; both Holm-adjusted p=1.0. Against periodic, the benign-update difference
is +1.6875 [1.3250, 2.0250], but exact two-sided p=0.0625 and Holm p=0.375.
No comparison passes the planned 0.05 significance criterion. A percentile
bootstrap interval excluding zero does not override that paired test.

No malicious learning occurred with exact, delayed-exact or unavailable feedback.
All malicious learning occurred under intentionally flipped verifier answers.
Thus the reference verifier, rather than selection alone, remains the principal
protection in this fixture. First-available has lower aggregate malicious ingestion
than uncertainty; the proposed selector is not a demonstrated dominant policy.

All fixed-probe attack recalls were 0 before and after adaptation; probe FPRs also
did not change. This floor effect makes the probes uninformative for improved
detection or recall degradation. Do not replace them after seeing results and
present the replacement as prespecified evidence. A separate future protocol must
establish useful probe sensitivity before testing a new mechanism.

Verification: all 243 repository tests passed locally in 245.614 seconds;
dependency checks and retained-research verification of 43 files passed.
The research skill's evidence discipline informed the fixed comparisons and
explicit reporting of adverse/null results. No novelty or patentability is proven.
