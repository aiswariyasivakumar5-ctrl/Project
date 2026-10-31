# Final implemented architecture

```text
MCP Client
    |
    v
Sentinel HTTP Gateway
    |
    +--> bounded JSON parsing and JSON-RPC validation
    |
    +--> context, session, intent, tool metadata extraction
    |
    +--> PREFLIGHT ENFORCEMENT
    |       destructive-intent mismatch / trust policy
    |       block before upstream where evidence is available
    |
    v
MCP Server
    |
    v
Upstream response validation
    |
    v
SentinelEngine runtime analysis
    +-- behavioral autoencoder
    +-- intent mismatch
    +-- session-local sequence model
    +-- bounded temporal/cross-server causal graph
    +-- capability attestation evidence
    +-- uncertainty calculation
    +-- quarantine-protected learning
    +-- dynamic server trust
    |
    v
POST-RESPONSE ENFORCEMENT
    allow / observe / confirm / sandbox / isolate
    forward or withhold response
    |
    +--> causal trace and in-memory fingerprinted audit
    |
    v
MCP Client
```

## Enforcement boundaries

Preflight can prevent known destructive intent mismatches before the server executes. Most behavioral/response evidence exists only after the upstream call; post-response enforcement can withhold output but cannot undo an upstream side effect.

The gateway supports bounded HTTP JSON-RPC and Streamable HTTP initialize/session mapping for its documented MCP methods. It parses bounded upstream SSE JSON-RPC responses, validates IDs and response shape, enforces sizes and timeouts, and rejects unsupported methods. Monitoring exceptions fail closed by default.

## State and evidence

Profiles, causal history, trust, quarantine, challenges, and audit records are in memory. Traces contain content-derived identifiers and risk evidence. Audit payloads use fingerprints and a hash chain, but records are not signed or durable. Audit and operator routes require a separate operator Bearer credential; liveness/readiness endpoints are public.

## Attestation boundary

The non-standard `sentinel/attest` challenge proves response freshness relative to an enrolled capability digest in the mock-aware environment. It does not establish hardware identity, signed workload identity, TPM/TEE state, or deployment integrity.

## Explicit non-components

The Isolation Forest, OCSVM, Dense AE, LSTM, and Transformer are offline comparison baselines and are not inserted into the production gateway. No GNN, reinforcement learner, distributed state service, or hardware attestation component exists.
