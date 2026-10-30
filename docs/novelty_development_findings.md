# Novelty development verification — September 17

Implementation branch: `feature/novelty-experiment-framework`, based on `52f5451`.
These are development observations, not final publication evidence.

## Verification

- Full local suite: 112 tests passed.
- Live development matrix: seeds 42 and 123, five variants, eight scenarios,
  40 training events, eight validation events, scenario-size parameter six.
- Each seed/variant produced eight frozen TEST rows and three separate ADAPTIVE
  rows: 110 evaluations total. All frozen learning-state checks passed.
- Existing retained research verification: PASS, 43 files checked; no historical
  result files were changed.
- New-run output protection, repeat-run workload/decision determinism, complete
  state restoration and seed-ID pairing have regression coverage.

Full generated evidence is local under
`artifacts/novelty-development-20260917/` (ignored by Git), including protocol,
source/workload hashes, per-event records, summary and Markdown report. Regenerate
it with the documented CLI command using the parameters above and a new path.

## Observed behavior

| Observation | Full novelty | Relevant comparison |
|---|---|---|
| One actor rotates sessions, ADAPTIVE | Zero model updates | Baseline and no-dual-memory each average six updates |
| Independent legitimate sessions, ADAPTIVE | Six model updates, no interventions | Demonstrates the intended promotion path in this fixture |
| Distinct compromised identities, ADAPTIVE | Six model updates, no interventions | Current independent-identity requirement does not stop this coordinated case |
| Schema-stable injection, TEST | Attack recall 1.0; mean benign FPR 0.3333 | Disabling capability trust gives FPR 0.0 in this short fixture |
| Replay and expired authorization, TEST | Attack recall 1.0, FPR 0.0 | Uses existing pre-dispatch authorization checks |

Zero model updates is not equivalent to denying an attack: the single-actor
poisoning calls were allowed but did not promote their candidate. The compromised
multi-actor fixture intentionally presents the same observable low-risk behavior
as the legitimate-upgrade fixture. The present evidence cannot distinguish those
intents, even when the server answers the manifest challenge correctly.

The schema-stable scenario alternates attacks and benign calls on the same read
capability. Historical capability penalties can restrict subsequent benign calls;
the counterfactual-score ablation reduces but does not eliminate that effect.
Do not infer a population false-positive rate from six calls and two seeds.

## Next implementation priorities

1. Define and implement trusted promotion/upgrade approval evidence for cases that
   session independence and manifest echo cannot distinguish. Keep the coordinated
   fixture as a negative control; do not add scenario-label shortcuts to detection.
2. Specify a capability recovery policy and evaluate benign recovery after an
   incident on new held-out sessions.
3. Finish runtime hardening from the audit: retention bounds, input validation and
   attestation server/expiry binding; review baseline-training corrections in their
   own controlled study.
4. Team-review the hypotheses, metrics and workload assumptions, preregister a
   final protocol and freeze a release before larger novelty experiments.
