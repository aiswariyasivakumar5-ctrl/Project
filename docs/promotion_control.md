# Promotion reachability diagnostic — October 5, 2026

At this October 5 checkpoint, step 1 was **not complete**: the new attempted
positive control failed. This is retained evidence, not a successful adaptation
benchmark. No production code, risk thresholds, historical results, or evaluation
splits were changed.

Follow-up: the [October 6 fixed-factor diagnostic](promotion_factorial.md) obtains
a successful trained-model positive control with varied enrollment. The failures
reported below remain unchanged and are not superseded as observations.

## Construction and reproducibility

`sentinel.promotion_control` reuses `NoveltyLiveExperiment`, the real local HTTP
mock/gateway path, existing policy variants, and `LearningAttribution`. Each policy
starts a fresh experiment with the same 100 integer-addition enrollment calls,
then receives six calls using equivalent floating-point arguments. Both argument
types satisfy the calculator's `number` schema. The manifest stays unchanged;
the candidate fingerprint changes because it distinguishes Python argument types.
Adaptive calls use six distinct fixture principals and sessions. Latency input is
fixed at 20 ms using the existing research telemetry override.

The reviewed policy receives one real, scoped approval before the adaptive phase.
Attestation is performed through the gateway, not mocked as successful. Labels are
used only by the research observer. Output directories cannot be overwritten.
Protocol files retain source/workload hashes; event files retain verdicts,
attestation, memory dispositions, and actual learning-source attribution.

```powershell
python -m sentinel.promotion_control --output results/adaptation/new-control
python -m sentinel.promotion_control --output results/adaptation/new-explicit-control --explicit-intent
```

## Retained outcomes

Both runs completed five policies, each with six adaptive events:

| Policy | Short-intent updates | Explicit-intent updates | New shape promoted |
| --- | ---: | ---: | --- |
| Frozen | 0 | 0 | No |
| Immediate eligible | 0 | 0 | No |
| Gated, no review required | 0 | 0 | No |
| Reviewed | 0 | 0 | No |
| Review withheld | 0 | 0 | No |

Artifacts: `results/adaptation/promotion-control-20261005` and
`results/adaptation/promotion-control-explicit-20261005`. All adaptive calls were
intervened on. First gated-call risks were approximately 0.492934 and 0.493034,
respectively, exceeding the unchanged 0.42 learning gate and 0.45 confirmation
threshold. Attestation was verified, but approval did not override risk eligibility.
Attribution is complete; contamination is undefined because no updates occurred.

The second wording was deliberately added **after observing the first failure**:
it is a development diagnostic, not held-out or confirmatory evidence. Additional
intent words improve overlap in the provenance layer but also affect the separate
base intent-mismatch calculation. Neither wording establishes general adaptation.
The homogeneous enrollment is an intentionally narrow fixture and may itself
make small feature changes unusually large relative to its learned distribution.
This hypothesis needs a separately specified diagnostic, not favorable-seed search.

## What is established and what remains

The existing `LiveNoveltyTests` regression tests live cold-start promotion with
verified attestation and operator approval. That does not establish adaptation of
an already-trained model. The new failed controls expose this distinction.

Next: isolate the contributions of enrollment variance, behavioral scoring, and
intent scoring in a predefined diagnostic. Obtain a live trained-model positive
control without bypassing eligibility before claiming adaptive poisoning benefits.
Then test poisoning and legitimate change under matched conditions and on fresh
held-out workloads. Do not rewrite these failures or calibrate on held-out tests.

There are no attack events, independent research seeds, confidence intervals,
p-values, statistical superiority claims, or real-world/patentability conclusions
from this small constructed diagnostic. The identities and reviewer are trusted
simulation inputs, not evaluated authentication or human decision systems.
