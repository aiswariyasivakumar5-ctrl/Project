# Runtime controls and reviewed adaptation

This milestone follows runtime boundary hardening (`2bed1af`). It implements
retention, network limits, promotion review and capability recovery. These are
engineering controls; teammate review and publication-scale evaluation remain open.

## Retention and capacity

Configure `SentinelEngine(retention=RetentionConfig(...))` before serving traffic.
Defaults are 10,000 audit records, 10,000 causal nodes, 256 quarantined events per
server, 10,000 authorization/evidence claims, 256 server identities, 4,096 sessions,
256 tools per server, 1,024 sequence transitions per session, and 4,096 candidate
plus trusted-memory entries per novelty wrapper. Each candidate holds at most 32
events and the required number of independent identities (three by default).

Audit/quarantine windows retain recent records, while cumulative quarantine counts
remain in the server profile. Removing causal nodes also removes touching edges
and stale history references. A claim whose supporting evidence is missing fails
closed. Claim eviction deletes all associated replay/timestamp/evidence maps;
the ID then becomes unknown, never valid again. Expired and consumed claims may
remain for diagnostics until capacity eviction.

Server/session/tool admission rejects new identities at capacity. It never evicts
existing trust, model weights, or a rejected candidate to create fresh warm-up
authority. The gateway performs admission before tool dispatch. Sequence learning
stops adding new transition pairs at capacity but retains existing counts.
Candidate capacity blocks new learning candidates; it does not itself deny calls.
These limits bound record cardinality, not an operating-system memory budget.
Large payloads still consume substantial memory; deployment-specific sizing and
durable audit export are future work. Retention narrows the available evidence
window and can invalidate otherwise unexpired authorizations.

## HTTP deadlines and connection limits

Both `gateway` and `serve` expose `--request-timeout` (default 10 seconds) and
`--max-connections` (default 32). Gateway `--timeout` (default five seconds) caps
each upstream exchange within the shared request budget. Excess connections are
closed before handler-thread creation, with a best-effort HTTP 503 response; some
platforms reset unread connections before that response reaches the client.

A monotonic deadline covers accepted client connections, including headers and
body. Socket interruption defeats trickle traffic. Gateway upstream IO and engine
lock waits use the remaining budget. The semaphore is released on handler exit.
The mock research server is intentionally unchanged.

Limitations: Python cannot safely preempt arbitrary CPU work, platform DNS lookup,
or an embedding application's callback. Those can hold an admitted worker beyond
the deadline even after its client socket closes. The connection cap still limits
handler count. A request timing out does not roll back upstream side effects or
restore consumed provenance. This remains a synchronous research HTTP service,
not a replacement for deployment-level process/resource controls.

## Reviewed promotion

`NoveltyConfig.require_promotion_approval` defaults to true. A novel candidate needs
low risk, independent identities, attestation and a current operator review before
it can update the model. Missing review yields `awaiting-approval`, with no model
updates; it does not mean the tool call was blocked.

The embedding application's trusted control plane calls:

```python
novelty.approve_promotion(
    reviewed_interaction, reviewer="operator-id", evidence_ref="change-review-17", ttl=300
)
```

The interaction must reference the enrolled manifest. Approval binds server, tool,
argument shape, manifest and exact intent. It is consumed at promotion and recorded
in verdict/audit provenance. Expiry or clock rollback prevents its use. A promoted
shape thereafter uses existing trusted-memory behavior; the review is not a
per-invocation content authorization. `revoke_promotion(reviewed_interaction)`
removes that shape from trusted memory and rejects its candidate. Revocation does
not unlearn historical model weights. Conflicting candidate intents are rejected.

Review operations have no client-header or HTTP route. Reviewer names and evidence
references document a trusted in-process assertion; they are not digital signatures.
An authenticated control plane and genuine independent-identity resolver remain
the embedding application's responsibility. Reviewed shapes can still be abused:
approval is a learning control, not proof of benign server behavior.

## Reviewed capability recovery

Normal clients cannot recover an isolated capability by flooding benign calls.
After investigating an incident, the trusted embedding application may run:

```python
gateway.begin_recovery("safe_read", {"record_id": "reviewed-canary"},
    "Read reviewed canary", reviewer="operator-id", evidence_ref="incident-17")
gateway.probe_recovery("safe_read", {"record_id": "reviewed-canary"},
    "Read reviewed canary", independent_identity="authenticated-probe-identity")
```

Each distinct probe identity must come from a trusted resolver. The grant binds
exact arguments and intent as well as capability and manifest. The gateway also
requires read-only metadata, absence of a destructive hint, and compatible intent;
the operator must independently verify that the probe is safe because server hints
alone are not trustworthy. Probes still execute upstream, but their tool response
is withheld from ordinary clients. Recovery is not exposed through MCP methods.

Three independent, low-risk, successful, freshly attested probes restore only the
selected capability to trust 0.65. Any unsafe response, failed attestation or
transport failure cancels the review. Grants expire and are consumed on recovery.
No probe trains the model, resets another capability, or clears rejected learning
candidates. Recovery evidence is recorded in the engine and gateway audit windows.

### Review evidence lifecycle

Reviewed promotion requires a successful attestation on the invocation that
actually promotes the candidate. An older buffered attestation alone yields
`awaiting-attestation`; the historical no-review experiment variants retain their
original accumulated-attestation policy.

A new failed invocation, material fused risk (at least 0.42), provenance failure,
or manifest/attestation failure revokes pending promotion and recovery reviews
for that server/tool. Recovery identity progress is cleared; where reviews were
revoked, buffered candidate evidence for that capability is cleared too. Reviews
for other capabilities survive. This security invalidation also runs with
`learn=False`: frozen model weights do not imply frozen authorization state.
Failed recovery probes and recovery transport/analysis failures invalidate all
reviews for the affected capability, preventing reuse of a second older grant.
The ordinary evaluation verdict records counts of revoked reviews in provenance.

Novelty enrollment cannot train on a failed manifest/attestation check, even when
the embedding application marks traffic as trusted enrollment. A new review is
required after an incident; re-review does not clear sticky candidate rejection.

The base engine also quarantines failed attestation or changed-manifest events
without updating its model, including trusted enrollment and quarantine-disabled
paths. Explicit attestation ablation retains its existing behavior. Novelty
enrollment only updates the model when memory accepts the enrollment; a `capacity`
disposition cannot train an unrecorded shape. Already-enrolled shapes still learn
at capacity. These are consistency fixes to existing guards, not new detection
mechanisms or thresholds. Future reruns may reflect corrected learning behavior;
retained historical results are unchanged.

Lifecycle correction validation: all 154 tests passed on Windows/Python 3.14,
including six new regressions; dependency and 43-file retained-package checks
passed. The stale-attestation and intervening-incident tests failed before the fix.

## Research compatibility and remaining gates

The study's historical `full` and three component ablations explicitly retain the
old no-review promotion policy. New variant `approval_required` exercises the new
default. The original five CLI default variants remain unchanged; request the new
variant explicitly. With no review fixtures, it is expected to prevent learning
for both coordinated attackers and legitimate new shapes. Reviewed positive
controls are covered by live regression tests, not hidden scenario-label logic.

Before a release freeze: teammates must review these policies, validate default
capacity/latency budgets, approve a preregistered protocol and select a commit hash.
Independent trace evaluation, calibration and publication-scale evidence remain
outstanding. Retained historical results must not be overwritten.

## Development verification — 2026-09-17

- Windows/Python 3.14: all 148 tests pass, including 23 new retention, socket,
  approval and recovery tests. Dependency checks pass. Read-only retained-package
  verification passes for 43 files; no tracked historical result files changed.
- Two-seed smoke (42, 123): `full` versus `approval_required`, three adaptation
  scenarios, 40 training events, eight validation events and six scenario events;
  24 scenario/phase/seed evaluations. Outputs are under the ignored local directory
  `artifacts/runtime-controls-20260917/`. These are development diagnostics.
- Historical `full` learned six events per seed in both the distinct-compromised-
  identities and legitimate-upgrade scenarios. `approval_required` learned zero
  without operator approval in both. Single-actor session rotation learned zero
  under either policy. Frozen TEST learning-state checks passed throughout.
- These calls were allowed: no attack-detection improvement is claimed. Reviewed
  positive promotion and post-incident recovery are separately exercised by live
  regression tests. Recovery is not yet a publication-scale evaluated policy.
