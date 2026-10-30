# Enrollment trust investigation — October 3, 2026

## Findings

The seed-20001 adaptation failure was reproduced with an instrumented 100-event
enrollment trace. The diagnostic records actual calls, base component scores,
capability trust before/after each decision and final capability states. Its wrapper
delegates to the existing controller once and returns its result unchanged.

Benign reads reuse record identifiers across two mock servers in the same reused
session. The graph interprets matching prior response values as unexplained flow.
For the primary safe_read capability, event 85 has base causal risk 0.8 and fused
risk 0.548125. Later repetitions at events 94, 95, 97 and 98 repeat the restriction.
This is a mismatch between the fixture's benign label and the conservative flow
policy: matching values alone do not prove unauthorized transfer.

The controller also penalizes restricted actions even when the current risk is
low, because action selection includes historical trust. At event 96, risk is
about 0.26, but historical trust about 0.44 forces confirmation and another trust
decrement. This positive feedback accelerates loss. Final primary safe_read trust
is 0.14976499321885733, below preflight's 0.15 isolation threshold. Subsequent calls
cannot execute or accumulate ordinary recovery evidence. Explicit reviewed recovery
is an existing separate mechanism; this diagnostic does not invoke it.

## Narrow implementation correction

Code inspection also found JSON object field names included in flow-token matching.
Two unrelated payload values under the same schema key could create a false edge.
The correction extracts tokens recursively from payload values and excludes object
keys. Numeric scalar tokens remain supported; booleans/null do not supply meaningful
flow identifiers. Tests cover shared schema keys, nested copied values, numeric
values, session separation and embedded instruction detection.

This defect is real, but it was NOT the cause of the reproduced seed's read
isolation. The first rerun after the payload correction still produced the same
final primary trust and all 16 adaptation cells still had 100% benign intervention
and zero updates. Payload overlap persists; its normalized graph weight can even
increase when schema tokens leave the denominator. No performance improvement is
claimed. The final numeric-scalar compatibility addition followed the diagnostic;
source hashes identify the exact code used by each artifact.

## Evidence

Full suite: 195 tests passed in 122.918 seconds, including five payload-flow
regressions. Retained research verification passed for 43 files.

- Original trace: `results/adaptation/enrollment-trace-20261003`.
- Payload correction trace: `results/adaptation/enrollment-payload-fix-20261003`.
- Separate repeated matrix: `results/adaptation/payload-fix-20261003`.
- Original matrix remains at `results/adaptation/diagnostic-20261003`.

## Next design decision

Define an explicit authorization policy for legitimate repeated cross-server reads,
then test benign and malicious transfers with matched values. Distinguish observed
payload overlap from established unauthorized flow. Separately evaluate whether
historical trust should itself count as new negative evidence. That is a policy
revision requiring declared threat assumptions and paired evaluation, not a reason
to lower thresholds or reset this seed's trust. Include failure-preserving tests and
reviewed recovery experiments. Until then the full adaptation objective is unresolved.
