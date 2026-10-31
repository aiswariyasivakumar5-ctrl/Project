# Runtime correctness and capability-gateway continuation

Local implementation branch: `fix/runtime-correctness-and-novelty`, based on
`4f21bcc`. This milestone is pending human review; it is not an experiment freeze.

## Implemented

- Ordinary warm-up traffic obeys the same risk cutoff for learning as later traffic.
  Explicit trusted enrollment and the research quarantine ablation remain distinct
  in-process controls. Neither may override invalid provenance or failed execution.
- Only `notifications/initialized` is accepted without a request ID. Invalid tool
  requests are rejected before dispatch. Tool-level `isError` prevents learning.
- Supplied provenance is validated, causally checked and atomically consumed before
  forwarding. Expired/replayed/context-mismatched requests have `forwarded=false`
  and no fabricated post-execution trace. Consumption is permanent after dispatch
  failure because the gateway cannot know whether the server executed an action.
- `--require-provenance` makes provenance mandatory for every tool call. Without
  it, legacy calls can omit a claim, so optional mode is not mandatory authorization.
- `--novelty` connects capability trust, counterfactual intent scoring and dual
  memory to the gateway. The audit record includes capability trust, claim ID,
  memory disposition and promoted-event count. Capability trust replaces the
  server-wide preflight isolation check in this mode.
- Approved model updates do not evaluate events again. Promotion of stored events
  cannot create duplicate causal nodes or rewind the current session transition.
- `NoveltyConfig` provides independent in-process switches for intent provenance,
  capability trust and dual memory. `learn=False` disables baseline/memory updates;
  runtime evidence and enforcement state still advance.
- A shared engine lock protects gateway/evaluation-service model updates. This is
  local synchronization, not distributed coordination or a full concurrency proof.
- ROC computation includes the empty-selection endpoint even when scores tie at 1.
  `python -m sentinel_research.correct_metrics --output <new-file.json>` recomputes retained
  percentile-score AUROC without changing thresholds or overwriting existing files.
- CI configuration runs the suite on Windows/Linux with Python 3.11/3.14. The local
  audited NumPy version is pinned in `requirements-repro.txt` for Python 3.14.5.
  Hosted CI has not run until these changes are pushed.

## Trusted integration boundary

The gateway exposes no enrollment, identity-creation or claim-issuance HTTP route.
An embedding application must enroll a known manifest through
`gateway.engine.attestation.enroll(server_id, digest)` and provide
`gateway.session_identity`, a resolver returning an authenticated independent
session identity or `None`. It must not simply echo an untrusted header. A resolver
can also be passed to `SentinelGateway(..., session_identity=resolver)`.

With an identity and enrolled manifest, the gateway performs challenge verification
and supplies the evidence to dual memory. A client cannot claim attestation by
sending a boolean or rotate raw session strings to satisfy promotion. Without a
resolver, the CLI still scores/enforces traffic, but new fingerprints remain
candidates. Trusted bootstrap traffic can be enrolled through the in-process
`trusted_enrollment` control; this must be turned off after bootstrap.

The direct `NoveltySentinelEngine` API is for trusted application/research callers:
its default session identity and `attested` argument are assertions by that caller.
The challenge remains an experimental hash-echo mechanism, not workload identity
or hardware-backed attestation. Manifest upgrades require explicit trusted enrollment
policy; this milestone does not supply an identity provider or upgrade service.

## Verification and evidence

New regression cases cover warm-up injection, ROC ties, tool errors, missing tool
names, notification bypass, expiry, concurrent replay, timeout consumption,
required claims, capability isolation, frozen learning, candidate independence,
exactly-once promotion and a real HTTP gateway/mock-server promotion/replay flow.
The original provenance experiment assertions now require attacks to be blocked
before forwarding instead of requiring an executed trace for every attack.

`results/corrections/auroc-v1.json` contains ten sequence-model recalculations and
source hashes. Twenty classical baseline seed files lack saved event outcomes and
are explicitly listed as unavailable for this recalculation. Historical tables
remain evidence from the original implementation; use the correction artifact for
sequence AUROC. Runtime-policy metrics still differ from the offline calibrated
threshold policy and must be reported separately.

## Next milestone

1. Teammate review of the correctness and provenance boundary changes; complete
   human contribution attribution and merge through the repository review workflow.
2. Wire novelty ablations into the experiment CLI, add the remaining laundering,
   coordinated-server, distributed-poisoning and legitimate-upgrade workloads,
   and define the authenticated-session/manifest threat assumptions.
3. Resolve remaining audit items: bounded state retention, fuller input validation,
   attestation server/expiry binding, baseline training corrections and recovery policy.
4. Preregister metrics and seeds, approve a frozen commit, then run novelty results
   under a new output tree. Do not overwrite the retained historical control.

No production deployment, publication-scale novelty run or GitHub push is included
in this local implementation milestone.
