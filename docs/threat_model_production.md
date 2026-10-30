# Production threat model

## What Sentinel enforces

- The HTTP gateway authenticates MCP callers and management operators with
  separate credentials. An optional hashed credentials file maps callers to
  client IDs used to bind downstream MCP sessions.
- Tool calls are deny-by-default and require an explicit tool allowlist.
- Optional JSON policies can bound argument size, reject configured patterns or
  paths, apply per-tool rates, or require approval before dispatch.
- Gateway transport can use TLS or mTLS. State writes use an atomic replacement
  and can be HMAC authenticated. Audit records can be written to a hash-chained
  JSONL file.
- Detector decisions can withhold a result from the MCP caller and produce
  structured audit evidence.

## What Sentinel does not enforce

- A detector decision made after an upstream tool call cannot undo the tool's
  side effects. The upstream may already have changed a database, sent a message,
  or called an external API before Sentinel withholds its response.
- The legacy `sandbox` model action does not create an operating-system,
  container, filesystem, or network sandbox. The current response decision is
  `contained-withheld`; old sandbox headers and payload fields remain as
  one-release compatibility aliases.
- The `X-Sentinel-Intent` value is supplied by the client. It is context for
  scoring, not a trustworthy authorization statement.
- Quorum and independent-session evidence do not provide Sybil resistance if an
  attacker can enroll or control multiple identities.
- MCP tool annotations originate from the upstream and are advisory. The
  gateway's authorization decision is based on the operator allowlist and
  policy, never on upstream annotations.
- The gateway does not support stdio upstreams, distributed rate limiting,
  horizontal scaling, replicated state, or high availability.
- The included detector has no demonstrated validation on representative real
  traffic and has zero recall on the synthetic `abnormal_sequence`,
  `capability_drift`, `gradual_poisoning`, and `low_and_slow` families. See
  [`production_gaps.md`](production_gaps.md).

## Trust boundaries

The client, upstream server, tool annotations, request arguments, intent text,
and response content are untrusted inputs. Operators control credentials,
allowlists, policy files, TLS termination, and state/audit storage. A reverse
proxy is trusted for forwarded scheme metadata only when
`--trust-proxy-headers` is enabled and the gateway is not directly reachable by
untrusted networks. The gateway is a single process; process compromise exposes
in-memory credentials and state.
