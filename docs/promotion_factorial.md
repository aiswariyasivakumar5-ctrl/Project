# Trained-model promotion: fixed-factor diagnostic — October 6, 2026

The live trained-model positive control now succeeds under varied enrollment.
This completes **promotion reachability**, not the broader poisoning-resistance,
real-world adaptation, novelty, or patentability claims.

## Fixed design

Following the two retained failed controls, the next development diagnostic was
specified before observing its outcomes: constant versus varied integer enrollment,
crossed with the existing short versus explicit intent wording. All four conditions
run all five policies. No condition is dropped and no threshold or production
detector is changed. This is a post-hoc development study, not preregistered or
held-out confirmatory evidence.

There are 100 enrollment calls per policy. Constant enrollment adds 1 and 2 each
time. Varied enrollment cycles through integer pairs (1,2), (10,20), (100,200),
(1000,2000), 25 times each. Both leave the float argument fingerprint unseen.
The subsequent six calls add 1.0 and 2.0, using distinct trusted fixture identities.
Latency input remains fixed. Within each wording condition, adaptive calls are
identical across policies and training conditions. Every policy starts fresh.

The explicit wording is held unchanged even during varied enrollment, including
its literal numeric wording. This limits its semantic realism; it is a scoring
diagnostic, not a representative natural-language task corpus. The short wording
does not contain fixed operand values and independently shows the same promotion
pattern. Varying numeric inputs changes several feature distributions together;
this is not an isolated intervention on a single scaler dimension.

```powershell
python -m sentinel.promotion_factorial --output results/adaptation/new-factorial
```

Artifacts: `results/adaptation/promotion-factorial-20261006`. The root protocol is
written before execution; each cell retains source/workload hashes, events, actual
base score components, promotion dispositions and successful-update attribution.
Failures are retained and existing output directories are never overwritten.

## Complete outcome table

Each entry is the number of actual adaptive model updates across six calls.

| Training / wording | Frozen | Immediate eligible | Gated | Reviewed | Withheld |
| --- | ---: | ---: | ---: | ---: | ---: |
| Constant / short | 0 | 0 | 0 | 0 | 0 |
| Constant / explicit | 0 | 0 | 0 | 0 | 0 |
| Varied / short | 0 | 6 | 6 | 6 | 0 |
| Varied / explicit | 0 | 6 | 6 | 6 | 0 |

For both varied conditions, immediate learning starts at event index 0. Gated and
reviewed learning starts at index 2: the third independent identity triggers a
three-event replay, followed by one update for each remaining event. The reviewed
grant is consumed. Withheld review prevents promotion, despite admission of calls.
Thus immediate learning is faster in this benign control; gated learning has no
demonstrated security advantage here because there are no attacks.

First-call fused risks (identical across policies within each condition) are:

| Condition | Fused risk | Base behavior component |
| --- | ---: | ---: |
| Constant / short | 0.492934 | approximately 1 |
| Constant / explicit | 0.493034 | approximately 1 |
| Varied / short | 0.196828 | 0 |
| Varied / explicit | 0.153333 | 0 |

The observed change is consistent with narrow training coverage driving excessive
behavioral anomaly scores. The standardizer divides by empirical variance with a
small floor; repeated identical enrollment is especially sensitive to new serialized
lengths. These data do not isolate the standardizer from the autoencoder/error
distribution or prove that broader enrollment will resolve arbitrary drift.

## Regression protection and interpretation

Final local verification: all **217 tests passed in 158.801 seconds**; retained
research verification passed for 43 files. The six promotion-control tests also
passed separately. Remote CI is not implied by these local results.

`test_live_trained_model_promotes_reviewed_shape_and_replays_sources` uses the
real local HTTP gateway/mock path and unchanged engine. It verifies an initially
untrusted float shape, successful attestation, per-call update counts 0,0,3,1,1,1,
replay sources 0,1,2 without out-of-order sequence learning, all six final source
indices, changed autoencoder weights, trusted shape membership and single-use
approval consumption. This verifies learning rather than admission alone.

The original failures remain intact. There are no independent research seeds,
attack trials, human-reviewer evaluation, confidence intervals, p-values, or
statistical superiority claims here. Zero malicious updates in an all-benign
fixture is not evidence of poisoning resistance.

**Next research task:** freeze matched benign-change and poisoning streams that
exercise this reachable promotion path, compare all learning policies, and retain
both adaptation delay and source-attributed malicious updates. Then evaluate the
frozen design on fresh held-out workloads and independent runtime traces.
