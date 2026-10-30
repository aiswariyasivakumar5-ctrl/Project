# Scoped flow permissions and trust evidence — October 3, 2026

The trusted application can call `TemporalCausalGraph.authorize_read` to authorize
an exact source server/tool, destination server/tool, session and argument object.
The grant has a bounded TTL (at most one hour), an opaque identifier, explicit
revocation and a capacity limit. Expiry uses the graph's monotonic clock, not the
client event timestamp. There is no client header or tool argument that grants
permission. Trusted application code must ensure the selected operation is read-only;
events marked as side-effecting cannot use a grant. Arbitrary server metadata is
not permission authority. This API is currently configured in-process, not through
a production operator UI.

Matching flow edges remain auditable as `authorized_cross_server_read`. Only the
overlap risk of that exact permitted edge is suppressed. Injection detection,
other unauthorized source edges, intent, anomaly, provenance and capability checks
remain active. Grants cover repeated matching reads until expiry or revocation;
they are not single-use provenance claims, and they do not attest source integrity.
Changing tool arguments or adding fields requires a separate grant.

Capability action selection still uses current risk and historical trust. Restricted
calls increment the restriction counter, but trust decreases only when current
risk (including side-effect uncertainty) independently requires restriction.
Low-risk calls restricted solely by historical trust hold trust constant. They do
not automatically recover or reset an isolated capability; reviewed recovery is
still required. This is a declared policy revision, not threshold fitting.

## Diagnostic scope

The optional `--authorize-reads` adaptation flag installs a trusted fixture policy
before enrollment: safe_read in either direction between the two mock servers,
record-1000 through record-1020, exact record_id-only arguments, and each enrollment
session. It does not consult attack labels or observed detector results. Grants
expire after 3600 seconds and survive checkpoint restore with their original expiry.
The workload and seed remain identical to the previous diagnostic. A run without
the flag provides a control under the revised trust rule.

Artifacts:
- `results/adaptation/flow-policy-20261003`: revised trust plus read grants.
- `results/adaptation/trust-policy-only-20261003`: revised trust, no grants.
- `results/adaptation/payload-fix-20261003`: earlier policy reference.

With grants, all 16 cells completed. Benign intervention rates ranged from 1/30
(3.33%) to 4/24 (16.67%). Frozen clean drift had 1/30 benign interventions;
the three adaptive policies each had 3/30. All attack-bearing cells had zero
malicious intervention rate. Adaptive policies learned 10 or 20 events per cell;
frozen policies learned zero. Updates on malicious steps were zero, which cannot
establish contamination rate because buffered updates need individual attribution.
The gated and immediate-eligible policies did not demonstrate an advantage over
one another in these summaries. These are one-seed diagnostics with hidden-intent,
observationally equivalent attacks, not significance tests or evidence of real-world
security improvement. Recovery, attribution and observable harmful-effect scenarios
remain necessary.

The no-grant control completed all 16 cells with benign intervention rate 1.0
and zero updates. Thus the revised trust rule alone did not restore utility in
this diagnostic. The comparison isolates enabling grants under the revised rule;
it is not a full factorial study of both changes.

Verification: all 201 tests passed in 90.268 seconds, including six permission and
trust-policy tests. Tests cover expiry, revocation, argument/tool/server scope,
side effects, injection preservation and repeated restrictions. Broader evaluation
and independent traces remain outstanding.
