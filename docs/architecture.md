# Architecture and research boundary

## Runtime path

```text
MCP event
  -> structural and intent features
  -> per-server online autoencoder
  -> session transition model
  -> temporal causal provenance graph + context-bound intent provenance
  -> capability attestation manager
  -> uncertainty-aware risk fusion
  -> allow / confirm / sandbox / isolate
             |
             +-> trusted baseline or quarantine
```

## Gateway request and response flow

```text
HTTP MCP client
  -> bounded JSON parser and JSON-RPC validation
  -> supported-method and parameter validation
  -> preflight trust/destructive-intent enforcement
  -> unchanged JSON-RPC forwarding
  -> upstream timeout, size, and response-ID validation
  -> Interaction normalization
  -> existing SentinelEngine.evaluate
  -> causal trace + trust + uncertainty + quarantine
  -> optional active sentinel/attest challenge
  -> forward or withhold result + audit fingerprint
```

The gateway does not introduce a second detector. `SentinelGateway` adapts actual
`tools/call` traffic into the existing `Interaction` type. Tool annotations learned
from `tools/list` supply side-effect metadata, while a stable hash of the returned
tool list becomes the capability identity.

Normal JSON-RPC payloads are forwarded without argument rewriting. Preflight may
block a known destructive tool when its declared intent is inconsistent or when
server trust is below the isolation threshold. Post-response decisions can withhold
the result; every block creates an audit record.

## Gateway trace record

The in-memory gateway audit records timestamp, session/server IDs, method, request
ID, tool, parameter and response SHA-256 fingerprints, latency, forwarding status,
trace ID, risk components, uncertainty, trust, decision, reasons, challenge, and
attestation outcome. Raw parameters are not placed in the gateway audit. The engine's
research quarantine still retains raw suspicious `Interaction` objects in memory.

## Failure and security policy

- Requests and upstream responses default to a 1 MiB limit.
- Upstream calls default to a five-second timeout.
- Malformed JSON, invalid JSON-RPC, ID mismatch, and malformed responses receive
  explicit JSON-RPC errors.
- Sentinel analysis is fail-closed by default. It can be configured fail-open only
  through the Python API for availability experiments.
- Client disconnects do not crash the server.
- Trace and payload fingerprints use SHA-256 but are not signed or durable.
- MCP POST requests require the configured client Bearer credential. Audit,
  metrics, pending-action, and operator-control routes require the separate
  operator Bearer credential. Liveness is public; readiness is public but
  reveals only readiness state. Configure Host/Origin allowlists and TLS before
  exposing the listener beyond a trusted local network.
- Server identity is configuration-based. TLS certificate pinning, workload identity,
  durable replay caches, persistent state, authorization, and distributed locking remain future work.
- HTTP JSON-RPC and Streamable HTTP initialize/session mapping are implemented.
  The gateway also consumes bounded upstream `text/event-stream` JSON-RPC
  responses. Batch JSON-RPC, stdio, resources, prompts, sampling, cancellation,
  and downstream SSE subscriptions are not supported; resource methods are
  rejected by default.
- Post-response blocking cannot roll back upstream side effects. Production use needs
  stronger preflight policy, sandboxing, or transactional tool execution.

## Causal representation

Each evaluated interaction is a node identified by a content-derived trace ID.
Edges currently encode temporal precedence, parameter derivation, and cross-server
data flow. Embedded policy-like instructions and cross-server response-to-argument
propagation raise causal risk. Session history is bounded; the node/edge audit store
is not. Nodes also retain session and originating intent for provenance validation.

## Intent provenance and replay scenarios

The trusted application (the experiment runner in these demonstrations) calls
`engine.issue_provenance(origin_trace_id, target_interaction, ttl=10)` after a
successful originating event receives ALLOW or OBSERVE. Issuance authorizes the
specific target tool and arguments under that event's exact intent, session and
server. It does not infer authorization from natural language. The caller must
be trusted to decide which target is authorized. There is no HTTP issuance endpoint.

Each opaque random claim ID identifies an immutable snapshot of originating
event ID, intent, session, server, target tool, JSON argument digest, predecessor,
creation time and expiration. The engine's ledger uses the existing
`TemporalCausalGraph`, not a second graph. The origin must exist and match its
intent/session/server. The optional predecessor is selected from the origin's
incoming `precedes` edge, must exist in the same session/server, and must retain
that edge. Node snapshots are pinned at issuance to detect substitution. During
use, the origin must also be reachable from the current interaction through
same-session precedence edges. These are observed ordering relationships, not
proof of real-world causation. Standalone legacy ledgers without a graph retain
claim-to-claim linking only; engine ledgers always validate graph evidence.

The caller attaches the ID to `Interaction.provenance_id`. For HTTP experiments,
`LiveExperiment` sends it in `X-Sentinel-Provenance`; the gateway copies it into
the interaction and preserves validation evidence in its audit record. Calls
without claims keep their prior behavior; this is not mandatory authorization
for every MCP call. An empty or malformed supplied ID is rejected.

Freshness uses the trusted ledger clock (`time.time` by default), injectable via
`SentinelEngine(provenance_clock=...)`. Event timestamps cannot backdate this
clock; non-finite event timestamps are rejected when a claim is supplied.
Validity is `created_at <= now < expires_at`. The default TTL is 300 seconds;
finite positive TTLs are required when specified. A standalone caller may
explicitly use `ttl=None` for no expiration. Experiments always use finite TTLs.
NaN, infinity, invalid creation times and invalid TTLs are rejected. Validation
remembers the last checked time for each claim. Expiration or a detected clock
anomaly permanently invalidates that claim, including after time rolls backward.
Issuance itself does not consume a claim.

Successful consuming validation atomically marks a claim used. Every subsequent
use is replay, including use in another context. Non-consuming validation still
records freshness checks, but cannot authorize repeated engine use. Claims are
consumed at evaluation, even if later behavioral checks restrict the action;
retry requires a newly authorized claim. Invalid provenance forces ISOLATE and
cannot update the baseline, sequence learning, enrollment, or increase trust,
including during warmup, trusted enrollment, disabled quarantine, or successful
attestation. Unrelated risk scoring and legitimate learning remain unchanged.

Both scenarios are registered `Scenario`/`WorkloadCase` sequences with explicit
`ProvenanceStep` issue/use operations. The runner resolves IDs after issuance,
advances a trusted deterministic clock, and submits ordinary HTTP MCP calls
through the existing gateway, engine, audit and metrics path. IDs are assigned
at runtime, not embedded as fake claims in the scenario templates.
`run_provenance_scenario` is only a compatibility wrapper around that same runner.

| Scenario step | Time | Expected behavior |
|---|---:|---|
| Delayed: read context with intent "Delete record 1001"; authorize simulated delete | 100 | Original unused claim expires at 110 |
| Delayed: separate read intent; authorize read control | 100 | Original control claim also expires at 110 |
| Delayed: use original read control | 105 | Valid delayed use, accepted |
| Delayed: use original unused delete claim | 111 | ISOLATE specifically for stale provenance, not replay |
| Replay: read context; authorize subsequent read | 100 | Original claim expires at 110 |
| Replay: first use | 101 | Accepted and consumed |
| Replay: second use of the same ID | 102 | ISOLATE specifically for replay, before expiration |

Experiment JSON records issuance, claim ID, checked time, pre-use consumption
state, validation reason, causal trace, decision and forwarding status.
The existing gateway evaluates these claims after forwarding. Thus the safe
`simulated_delete` response is withheld, but this does **not** demonstrate
pre-execution prevention or rollback of a real destructive tool.

Run from the project root using Python 3.11+ and NumPy:

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -s tests -p test_provenance.py -v
python -m unittest tests.test_gateway_integration tests.test_gateway_errors tests.test_research_framework -v
python -m sentinel_research.cli experiment --scenario delayed_causal_misuse --output artifacts/provenance-delayed
python -m sentinel_research.cli experiment --scenario provenance_replay --output artifacts/provenance-replay
```

Tests cover exact context bindings, stale/future/non-finite time, sticky rollback,
claim/node/edge substitution, real HTTP scenario execution, concurrent consumption,
attestation/learning interactions and legacy callers. State and replay protection
are in-memory and single-process; they are not durable or distributed. Claims and
graph fingerprints are not signatures. A compromised host can alter both evidence
and its snapshots. Storage retention, authenticated user intents, mandatory claim
policy and pre-execution enforcement remain outside this contribution.

## Behavioral attestation

Trusted enrollment stores the server's capability digest. When causal risk,
behavioral risk, or uncertainty is high, the engine returns a nonce challenge.
The MCP integration layer must invoke a side-effect-free endpoint that returns the
current capability digest and `SHA-256(nonce + ':' + capability_digest)`. A mismatch
causes trust decay and enforcement escalation.

This proves freshness and detects capability drift; it does not by itself establish
hardware identity. A production version should bind the response to a workload
identity, signed manifest, TPM, TEE, or deployment attestation system.

## Novelty under investigation

The research contribution is the combined mechanism rather than the individual
autoencoder:

1. Intent-conditioned runtime anomaly detection.
2. Causal propagation analysis across multiple MCP servers.
3. Uncertainty-triggered active behavioral attestation.
4. Quarantine memory that prevents unverified behavior entering the baseline.
5. Evidence-linked, proportional enforcement with dynamic server trust.

Formal patent claims require a professional prior-art search before publication.
