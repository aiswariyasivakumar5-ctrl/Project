# Consolidated limitations

## Evidence and generalization

- Workloads and MCP servers are synthetic/safe mocks; there are no independently sourced or enterprise MCP traces.
- Main baseline and ablation comparisons use 20 evaluation seeds (20001–20020), providing sufficient power to detect differences in F1 and recall against deep sequential baselines ($p < 0.0001$).
- The 330-cell exploratory novelty matrix retains 5 legacy seeds (42, 123, 456, 789, 1001), giving lower statistical power where none of the 4 planned primary comparisons achieve $p < 0.05$ under exact paired sign-flip tests.
- The 330-cell novelty matrix executes via direct in-process gateway dispatch (`in_process=True`) to prevent ephemeral port TIME_WAIT socket exhaustion under Windows loopback networking; exact decision and score equivalence with live HTTP socket transport is programmatically verified.
- Scenario templates do not establish prevalence, severity distributions, or resilience to adaptive real attackers.
- No production-scale, multi-tenant, distributed, or long-duration deployment validation exists.

## Detection and calibration

- Full Sentinel has zero held-out recall on capability drift, low-and-slow, gradual poisoning, and abnormal sequence in the publication comparison.
- Sequence evidence is session-local and does not generalize transition counts across sessions.
- The causal hard floor creates tied validation scores at 0.50 and dominates p99 thresholding.
- Evaluated validation-only fusion alternatives either raise FPR substantially or leave decisions unchanged.
- Isolation Forest ranks attacks but detects none at its retained operating threshold.
- Dual-memory quarantine only isolates single-identity poisoning; colluding identities (12/12 attacks admitted across 20 seeds), mixed traffic (4/4 attacks admitted), and post-promotion shape-equivalent drift (3/3 attacks admitted) still succeed in ingesting malicious updates into production memory.
- Learning-admission coordination matches standard transactional concurrency control identically (0/6 ineligible admitted, 0/2 eligible withheld) and provides no algorithmic or security advantage over classical transaction serializability.
- Stable hash buckets can collide, and current synthetic features may make some attacks easier than real semantic attacks.

## Sequence baselines

- LSTM and Transformer implementations are constrained NumPy baselines with fixed seeded encoders and optimized reconstruction heads, not fully end-to-end trained networks.
- Many short/new sessions create heavily padded windows.
- Current-event reconstruction may emphasize event anomalies rather than subtle transitions.

## Gateway and enforcement

- Post-response enforcement cannot undo upstream side effects: once a tool request is forwarded upstream, state modifications have already executed. Information withholding only prevents the response payload from reaching the client.
- Preflight depends on tool metadata and intent quality; incomplete or deceptive metadata weakens it.
- Audit and control endpoints require Bearer token authentication and fail closed by default; unauthenticated network exposure is prevented, but TLS termination and network access control remain external operational requirements.
- State persistence is process-local and file-based (`save_state`/`load_state`); distributed clustering, cross-process replication, and durable transaction logs are not implemented.
- No TLS pinning, workload identity, distributed locking, or signed audit chain is implemented. An in-process single-use provenance ledger now rejects replay before gateway dispatch; it is not durable across restarts. Optional required-provenance mode depends on a trusted application issuer.
- Supported MCP scope includes HTTP JSON-RPC, Streamable HTTP initialize/session
  mapping, and bounded upstream SSE JSON-RPC response parsing. Batch JSON-RPC,
  stdio, downstream SSE subscriptions, resources, prompts, sampling, and
  cancellation are unsupported; resource methods are rejected by default.
- Performance benchmarks are sequential local-host measurements, not concurrency or capacity studies.

## Attestation

- `sentinel/attest` is an experimental non-standard extension.
- There is no hardware-bound attestation, TPM/TEE evidence, signed manifest, or independently trusted identity root.
- Capability fingerprint detection can produce evidence below the global enforcement threshold.

## Research and legal scope

- Bootstrap intervals over five seeds are descriptive and not definitive population coverage.
- No comparison supports p < 0.05 under the implemented exact tests.
- No formal security proof, poisoning-resistance proof, patent novelty determination, or production-readiness assessment has been performed.
