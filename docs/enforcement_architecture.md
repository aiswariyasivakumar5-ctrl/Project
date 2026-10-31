# MCP Runtime Sentinel: Enforcement Architecture & Protocol Scope

**Publication Architecture & Security Audit for AI-SEC @ AINA-2027**  
**Document Version**: October 25, 2026 (Phase 5 Hardening)

---

## 1. Enforcement Reality: Preflight vs. Post-Response

MCP Runtime Sentinel enforces security decisions at two distinct inspection boundaries:

```text
Client Request
      │
      ▼
┌────────────────────────────────────────┐
│  Boundary 1: Preflight Enforcement     │
│  - Static intent-mismatch validation   │
│  - Tool authorization & capacity       │
│  - Capability/Server trust threshold   │
└──────────────────┬─────────────────────┘
                   │
         [Allowed] │ [Blocked] ──► 200 JSON-RPC Error (-32041) (No upstream call)
                   ▼
┌────────────────────────────────────────┐
│      Upstream MCP Server Call          │
│   (Side effects execute upstream!)     │
└──────────────────┬─────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────┐
│  Boundary 2: Post-Response Enforcement │
│  - Online autoencoder reconstruction   │
│  - Intent paraphrase / lexical match   │
│  - Causal graph propagation & echo     │
│  - Dynamic attestation verification    │
└──────────────────┬─────────────────────┘
                   │
         [Allowed] │ [Withheld: confirm / sandbox / isolate]
                   ▼
             Client Result
```

### Critical Security Limitation: Irreversibility of Upstream Side Effects
Preflight enforcement occurs *before* upstream dispatch and can prevent execution. However, **post-response enforcement occurs *after* the upstream MCP server has already processed the request**. 
- If an upstream tool call performs state-changing operations (such as database mutations, file writes, or external API calls), Sentinel's post-response withholding prevents the upstream return payload from reaching the client.
- **Sentinel cannot rewind, rollback, or undo upstream external side effects**.
- Deployers must configure destructive or high-impact tools with preflight policy checks; post-response anomaly detection is an information-withholding boundary, not a distributed rollback mechanism.

---

## 2. Action Lifecycle: Confirm, Sandbox, and Isolate

Sentinel categorizes post-response interventions into three distinct actions:

### A. Confirmation Flow (`Action.CONFIRM`)
When a tool interaction exhibits intermediate risk ($\text{risk} \in [0.45, 0.65)$), Sentinel initiates an explicit confirmation flow:
1. **Withhold & Register**: The gateway withholds the upstream response and creates a `PendingAction` in the `SentinelGateway.pending_actions` queue.
2. **Client Error Response**: The client receives a standard JSON-RPC error `-32042` with metadata:
   ```json
   {
     "jsonrpc": "2.0",
     "id": 1,
     "error": {
       "code": -32042,
       "message": "Sentinel confirmation required",
       "data": {
         "decision": "confirm",
         "action_id": "act-3f48a9b2c1d0",
         "trace_id": "tr-20261025-001",
         "expires_at": 1729864200.0,
         "reasons": ["behavioral anomaly above confirmation threshold"]
       }
     }
   }
   ```
3. **Approval Lifecycle**:
   - `GET /v1/pending` (Authenticated): Returns list of active pending actions.
   - `POST /v1/pending/{action_id}/approve` (Authenticated): Marks the action as `"approved"` and releases the withheld upstream response payload to the operator.
   - `POST /v1/pending/{action_id}/deny` (Authenticated): Marks the action as `"denied"` and purges the withheld payload from memory.
   - **Timeout Expiration**: If `now >= expires_at` (default 60s), the action is marked `"expired"` and the withheld payload is purged. Attempts to approve an expired action fail with HTTP 409 Conflict.

### B. Response Withholding (`Action.SANDBOX`)
When risk falls in the containment bracket ($\text{risk} \in [0.65, 0.82)$):
1. The gateway flags response headers:
   - `X-Sentinel-Decision: contained-withheld`
   - `X-Sentinel-Containment: response-withheld`
   - The deprecated `X-Sentinel-Sandbox` headers remain for one release.
2. The upstream tool has already executed. Sentinel withholds its response from the client; it does not isolate the process or undo upstream effects. The legacy `sandbox_contained` payload field remains for one release only.

### C. Isolation (`Action.ISOLATE`)
When risk exceeds the severe threshold ($\text{risk} \ge 0.82$):
- The response is permanently withheld (JSON-RPC error `-32042`).
- The session is quarantined to prevent baseline model updates.
- Attestation challenge may be triggered to verify server integrity.

---

## 3. Gateway Authentication & Security Boundary

### Operator Tool Allowlist

Every `tools/call` is checked against the operator-configured `allowed_tools` list before dispatch. The CLI exposes this as repeatable `--allow-tool NAME`; an empty list denies all tool calls. The allowlist is based on exact tool names and is independent of upstream MCP annotations, which are advisory metadata supplied by the server. Operators should allow only tools whose effects they accept. This is a coarse per-tool permission boundary; it does not provide argument-level authorization or undo side effects.

### MCP Caller Authentication

The serving CLI refuses to start without a client Bearer credential, a distinct operator credential (both at least 32 characters), and a trained baseline state file. Configure the credentials through `MCP_SENTINEL_CLIENT_TOKEN` and `MCP_SENTINEL_OPERATOR_TOKEN`; callers must send the client token on every MCP HTTP POST. The operator token protects audit and approval routes. These are shared service credentials, not per-user OAuth or role-based authorization. Deployments needing user-level decisions must validate identity at a trusted gateway and pass verified identity into an embedding integration. Put remote deployments behind TLS and configure `--allowed-host` and `--allowed-origin`; do not expose the plain HTTP listener directly to an untrusted network.

To protect operational telemetry and control APIs:
- **Bearer Token Authentication**: The gateway enforces HTTP Bearer token authentication via constant-time credential comparison (`hmac.compare_digest`) on:
  - Audit log endpoint: `GET /v1/audit`
  - Pending actions queue: `GET /v1/pending`, `GET /v1/pending/{id}`
  - Operator approval/denial: `POST /v1/pending/{id}/approve`, `POST /v1/pending/{id}/deny`
- **Fail-Closed by Default**:
  - If a request is received without a valid `Authorization: Bearer <token>` header, the gateway returns **HTTP 401 Unauthorized**.
  - If the gateway is instantiated without a configured `auth_token` (`auth_token=None`), all audit and control endpoints fail closed by default (HTTP 401), preventing accidental exposure of sensitive telemetry or approval routes.
- **Public Endpoints**: `GET /livez`, its compatibility alias `GET /health`, and `GET /readyz` are unauthenticated; Host/Origin validation still applies. `/metrics` and every audit/control route require the operator credential.

---

## 4. State Persistence (Trust and Quarantine)

Sentinel provides explicit atomic file-based persistence for runtime state across gateway restarts:
- `gateway.save_state(filepath)`: Exports engine server profiles (trusted call counts, trust scores, error variance statistics), quarantined session IDs, capability trust levels, and tool metadata into an atomic JSON snapshot (written via temporary file swap).
- `gateway.load_state(filepath)`: Restores state atomically under coordinator locks, allowing gateway restarts without resetting server warmup counts or losing quarantine trust history.
- **Limitation**: Persistence is process-local and file-based. Distributed clustering, cross-process replication, and durable transaction logs are not implemented.

---

## 5. Supported vs. Unsupported MCP Protocol Scope

| Protocol Feature | Status in MCP Runtime Sentinel | Handling & Limitation |
|---|---|---|
| **JSON-RPC Request/Response** | **Supported** | `tools/call`, `tools/list`, `initialize` over HTTP POST. |
| **JSON-RPC Notifications** | **Supported** | `notifications/initialized` over HTTP POST. |
| **Batch JSON-RPC Requests** | **Unsupported** | Sentinel enforces strict single-request framing; batch arrays (`[{...}, {...}]`) are rejected (`fail-closed`). |
| **Streamable HTTP sessions** | **Supported** | `initialize` maps downstream and upstream session IDs; subsequent HTTP POST requests reuse the mapped upstream session. |
| **Upstream SSE responses** | **Supported** | Bounded `text/event-stream` JSON-RPC responses are parsed for the matching request ID. Downstream SSE subscriptions are not implemented. |
| **stdio Transport** | **Unsupported** | Process-pipe stdio transport is not implemented; gateway operates exclusively via HTTP. |
| **MCP Resources** | **Unsupported** | `resources/list`, `resources/read`, and `resources/subscribe` are rejected with JSON-RPC error `-32601`. |
| **MCP Prompts** | **Unsupported** | `prompts/list` and `prompts/get` are rejected with `-32601`. |
| **MCP Sampling** | **Unsupported** | `sampling/createMessage` is rejected with `-32601`. |
| **Request Cancellation** | **Unsupported** | `notifications/cancelled` is not tracked; dispatched requests run to completion. |
