# Runtime boundary hardening

Implementation branch: `feature/runtime-hardening`, based on `734848c`.

## Implemented

- Attestation challenges bind verification to the consuming server and its enrolled
  capability digest. Verification requires the `server_id` keyword argument.
- Challenges expire after 30 seconds using a monotonic clock. Expiry is inclusive;
  a clock rollback or nonfinite clock clears pending challenges and fails verification.
  Exported challenge timestamps are process-local monotonic values, not UTC timestamps.
- Verification is atomic and single-use. A wrong-server attempt cannot consume
  another server's challenge; a wrong answer from the bound server consumes it.
- At most 1,024 challenges remain pending. Issuing beyond capacity invalidates the
  oldest challenge. Both lifetime and capacity are configurable on AttestationManager.
  Failed gateway attestation transport or decoding also discards its challenge.
- JSON boundaries reject duplicate keys, nonfinite values, invalid Unicode,
  nesting deeper than 64 levels, and structures exceeding 100,000 visited values
  and object keys. JSON-RPC IDs require exact type/value correlation and reject booleans.
- Both HTTP endpoints require one valid Content-Length and reject Transfer-Encoding.
  Evaluation requests have a 1 MiB limit and five-second socket read timeout;
  the gateway uses its configured size and timeout. These are per-read timeouts,
  not total request deadlines. Duplicate Sentinel headers are rejected.
- Oversized session and intent headers are rejected instead of silently truncated.
  Tool lists validate annotation types and duplicate names before replacing cached
  metadata; malformed tool results cannot enter learning.
- The evaluation API validates interaction field types, finite telemetry, identifier
  lengths, and nonnegative latency/timestamps before mutating engine state.

## Verification

`tests/test_http_hardening.py` covers expiry, server binding, replay races, capacity,
checkpoint deepcopy, failed attestation cleanup, JSON ambiguity, HTTP framing,
invalid interactions, metadata cache preservation, and rejection before forwarding.
The full suite also exercises live gateway novelty promotion and restored study
checkpoints. Retained research files must remain unchanged.

Local validation on 2026-09-17: all 125 tests passed on Windows/Python 3.14;
`pip check` passed, retained-package verification passed for 43 files, and no
tracked files under `results/` changed. Cross-platform CI has not run for this branch.

## Next execution steps

Update: steps 1 and 2 below are implemented in `runtime_controls.md`, along with
reviewed promotion and capability recovery. Review and research-freeze gates remain.

1. Add configurable audit, causal-graph, provenance and quarantine retention with
   explicit eviction semantics. Replay protection must fail closed after eviction;
   evicting identities must not reset adversarial trust into a trusted warm-up path.
2. Add total request deadlines and connection/concurrency limits for deployed HTTP
   service use. Current per-read timeouts do not prevent slow trickle clients.
3. Complete mechanism/threat-model review, including compromised independent
   identities and schema-stable response attacks documented in development findings.
4. Preregister the novelty protocol and validation-only threshold selection before
   freezing a release and running publication-scale experiments.

This change does not provide cryptographic server identity or hardware attestation.
The existing nonce/digest echo remains behavioral evidence. Pending challenges are
bounded. Later retention controls and their limitations are documented in
`runtime_controls.md`.
