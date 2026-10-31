# Deployment guide

This guide runs the HTTP gateway between an MCP client and an HTTP(S) upstream.
Stdio upstreams are not supported. Review the [production limits](production_gaps.md)
and [production threat model](threat_model_production.md) before enabling tools.

## 1. Install and enroll a baseline

Use Python 3.11 or newer. Install the package in a virtual environment and
generate separate client, operator, and state-integrity secrets. Keep them in a
secret manager or service environment; do not put values in command arguments.
The service constraint file pins the sole runtime dependency, NumPy, to the
tested version; NumPy has no required runtime dependencies of its own. The
research reproduction environment uses its separate `requirements-repro.txt`.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --constraint requirements-service.txt .
export MCP_SENTINEL_CLIENT_TOKEN="$(openssl rand -hex 32)"
export MCP_SENTINEL_OPERATOR_TOKEN="$(openssl rand -hex 32)"
export MCP_SENTINEL_STATE_KEY="$(openssl rand -hex 32)"
```

Enroll only known-benign calls against the intended upstream. Protect the state
file because it contains learned profiles and may contain approved response
payloads after runtime operation.

```sh
umask 077
python -m sentinel_research.cli baseline \
  --upstream https://mcp-upstream.example/api \
  --server-id inventory-prod \
  --state-file /var/lib/mcp-sentinel/state.json
```

If the upstream requires a credential, pass only the header mapping name and
environment variable name; set its secret value in the service environment:

```sh
export MCP_UPSTREAM_TOKEN="..."
python -m sentinel_research.cli baseline --upstream https://mcp-upstream.example/api \
  --server-id inventory-prod --state-file /var/lib/mcp-sentinel/state.json \
  --upstream-header Authorization=MCP_UPSTREAM_TOKEN
```

## 2. Start with TLS and explicit permissions

Provision a TLS certificate whose names match the endpoint clients use. Set
`--allowed-host` to the expected public Host value when binding beyond loopback.
Use `--allowed-origin` only for browser clients that need it.

```sh
python -m sentinel_research.cli gateway \
  --upstream https://mcp-upstream.example/api \
  --server-id inventory-prod \
  --host 0.0.0.0 --port 8788 \
  --state-file /var/lib/mcp-sentinel/state.json \
  --tls-cert /etc/mcp-sentinel/tls/server.crt \
  --tls-key /etc/mcp-sentinel/tls/server.key \
  --allowed-host sentinel.example:8788 \
  --allow-tool lookup_item --allow-tool calculate \
  --audit-log /var/log/mcp-sentinel/audit.jsonl \
  --rate-limit 20 --rate-burst 40
```

Only explicitly allowlisted tools can execute. Keep `--allow-method` unset unless
the deployment needs MCP `ping`, resources, or prompts methods. These methods
are audited but currently unscored. Use `--tls-client-ca` to require mTLS client
certificates. When TLS terminates at a reverse proxy, set explicit Host/Origin
allowlists, enable `--trust-proxy-headers`, and block direct network access to
the gateway.

For multiple clients, create a JSON object mapping each lowercase SHA-256 hash
of a high-entropy client token to a stable client ID, then configure
`--client-credentials /etc/mcp-sentinel/credentials.json`. For example, compute
a hash in a protected provisioning script with Python's `hashlib.sha256`.
Authenticated client IDs bind MCP sessions, so caller-controlled
`X-Sentinel-Session` values cannot cross client boundaries. The single-token
`MCP_SENTINEL_CLIENT_TOKEN` setting remains supported.

## 3. Run under a supervisor or Docker

For systemd, use a dedicated unprivileged account, `UMask=0077`, a read-only
application installation, and writable state/audit directories only. Store
secrets in a root-owned `EnvironmentFile` or a systemd credential store. Restart
on failure and stop with SIGTERM; the gateway stops accepting requests, drains
admitted handlers up to its configured request timeout, and saves state.

The repository includes a non-root multi-stage [`Dockerfile`](../Dockerfile) and
[`docker-compose.example.yml`](../docker-compose.example.yml). The compose sample
expects a `certs/server.crt` and `certs/server.key` mounted read-only, uses a
named data volume, enrolls the bundled mock upstream, and binds the published
port to loopback. Replace the mock upstream, credentials, TLS assets, and sample
tool allowlist before deployment. The gateway healthcheck trusts the mounted
server certificate and verifies TLS; the one-shot enrollment service disables
the inherited gateway healthcheck, and the mock upstream uses its own TCP probe.

Liveness is `GET /livez`. Readiness is `GET /readyz` and requires a loaded trained
baseline plus a reachable upstream endpoint. Authenticated operators can read
Prometheus metrics at `GET /metrics`; control and audit routes use the separate
operator bearer credential.

## 4. Back up, rotate, and upgrade

- Back up `/var/lib/mcp-sentinel/state.json`, credentials, policy, and TLS
  configuration using access-controlled encrypted backups. The optional state
  HMAC detects tampering but does not encrypt state.
- Preserve audit JSONL files and their `.1` rotation segment. Verify each
  retained segment with `python -m sentinel_research.cli verify-audit PATH` before and
  after transfer. Rotation discards older segments; ship them to durable storage
  before that happens if retention is required.
  Active and rotated audit log files are created with restricted file mode `0600` (`-rw-------`).
  If a pre-existing audit log has looser permissions, Sentinel tightens it to `0600` on open
  and logs a `tightened_audit_permissions` security warning event (skipped gracefully on Windows).
- To rotate client credentials, atomically replace the credentials JSON and
  send SIGHUP. Invalid replacement files leave the prior in-memory credential
  set active and emit a redacted error log.
- Back up state before upgrading. Install the new version, run the full test and
  deployment smoke checks, then restart. Restore the previous package and
  state snapshot if health/readiness checks fail.
- Keep client and operator credentials different. Rotate either token through
  the deployment secret manager and restart unless using the reloadable client
  credentials file.

## 5. Required pre-execution tool policy

The serving command refuses to start without `--policy-file`. Every allowlisted
tool must have an operator-assigned risk class and JSON Schema. Unclassified
tools are denied. Object schemas reject unknown fields by default; set explicit
properties and argument size/depth bounds:

```json
{
  "tools": {
    "lookup_item": {
      "risk_class": "read",
      "input_schema": {
        "type": "object",
        "properties": {"record_id": {"type": "string"}},
        "required": ["record_id"]
      },
      "max_argument_bytes": 4096,
      "max_argument_depth": 16,
      "forbidden_patterns": ["(?i)include_secret"],
      "forbidden_paths": ["admin_override"],
      "rate_limit": 5,
      "rate_burst": 10
    }
  }
}
```

`read` tools are allowed by default and detector decisions may withhold their
responses after upstream execution. `write` tools require operator approval by
default. `destructive` tools are denied unless the policy explicitly sets
`approval_required: true`; that approval is requested before dispatch. For
`write`, an explicit `approval_required: false` allows dispatch without human
approval. Intent metadata never changes these policy outcomes.

The detector is advisory only for `write` and `destructive` tools. Its role,
execution stage, and whether a response was withheld are in response headers and
audit records. Detector analysis happens after upstream execution; withholding
the response does not prevent the upstream action.

Online learning is frozen unless the gateway is started with
`--enable-learning`. Enrollment creates an unapproved baseline. Approve it with
an operator identity and durable audit sink before serving:

```sh
python -m sentinel.cli baseline approve --state-file state.json --actor change-123 --audit-log audit.jsonl
python -m sentinel.cli baseline export --state-file state.json --output approved-baseline.json --actor change-123 --audit-log audit.jsonl
python -m sentinel.cli baseline rollback --state-file state.json --version-file approved-baseline.json --actor incident-456 --audit-log audit.jsonl
```

Each online model update records actor, time, version, and diff summary, and
marks the changed state unapproved for the next startup.

## 6. Making a release archive

To create a clean distribution archive excluding virtual environments (`.venv/`, `.venv-repro/`), caches (`__pycache__/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`), temporary files, build outputs (`build/`, `dist/`), certificates, and local state/log files:

```sh
python scripts/make_release_archive.py
```

This builds `dist/mcp-runtime-sentinel-0.2.0.zip` (or `.tar.gz` via `--format tar.gz`), pruning all non-distributable local artifacts.
