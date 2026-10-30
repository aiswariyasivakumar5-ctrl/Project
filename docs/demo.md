# Local Windows demonstration

This demonstration sends real HTTP JSON-RPC traffic through `client → Sentinel gateway → mock MCP server`. All listeners bind to `127.0.0.1`; the audit endpoint is unauthenticated and must remain local.

## Prerequisites and installation

Use Python 3.11+ and follow `docs/dependencies.md`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## Automated local demo

```powershell
.\scripts\demo.ps1
```

The script starts hidden local processes, sends initialize/notification/tools/list/tool calls, prints decisions and audit evidence, then shuts both servers down. It never invokes a real destructive operation: `simulated_delete` only returns simulation text, and the mismatch demonstration is blocked before upstream.

## Manual three-terminal workflow

Terminal 1 — mock MCP server:

```powershell
.\.venv\Scripts\Activate.ps1
python -m sentinel.cli mock-server --host 127.0.0.1 --port 8790
```

Expected startup: `Test MCP server on http://127.0.0.1:8790`.

Terminal 2 — Sentinel gateway:

```powershell
.\.venv\Scripts\Activate.ps1
python -m sentinel.cli gateway --upstream http://127.0.0.1:8790 `
  --server-id demo-mcp --host 127.0.0.1 --port 8788
```

Expected startup: `Sentinel MCP gateway on http://127.0.0.1:8788 -> http://127.0.0.1:8790`.

Terminal 3 — client requests:

```powershell
$headers = @{"X-Sentinel-Intent"="List tools"; "X-Sentinel-Session"="demo"}
$body = @{jsonrpc="2.0"; id=1; method="initialize"; params=@{protocolVersion="2025-06-18"}} | ConvertTo-Json -Depth 6
Invoke-RestMethod http://127.0.0.1:8788 -Method Post -ContentType application/json -Headers $headers -Body $body

$body = @{jsonrpc="2.0"; id=2; method="tools/list"; params=@{}} | ConvertTo-Json -Depth 6
Invoke-RestMethod http://127.0.0.1:8788 -Method Post -ContentType application/json -Headers $headers -Body $body
```

Normal request:

```powershell
$headers = @{"X-Sentinel-Intent"="Read record demo-1001"; "X-Sentinel-Session"="safe-demo"}
$body = @{jsonrpc="2.0"; id=3; method="tools/call"; params=@{name="safe_read"; arguments=@{record_id="demo-1001"}}} | ConvertTo-Json -Depth 8
Invoke-WebRequest http://127.0.0.1:8788 -Method Post -ContentType application/json -Headers $headers -Body $body
```

Expect a matching ID, upstream record content, `X-Sentinel-Decision`, and `X-Sentinel-Trace`.

Blocked destructive mismatch:

```powershell
$headers = @{"X-Sentinel-Intent"="Read record demo-1001"; "X-Sentinel-Session"="blocked-demo"}
$body = @{jsonrpc="2.0"; id=4; method="tools/call"; params=@{name="simulated_delete"; arguments=@{record_id="demo-1001"}}} | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8788 -Method Post -ContentType application/json -Headers $headers -Body $body
```

Expect JSON-RPC error `-32041`; the audit record has `forwarded=false`.

Schema-mutating response:

```powershell
$headers = @{"X-Sentinel-Intent"="Read the schema"; "X-Sentinel-Session"="schema-demo"}
$body = @{jsonrpc="2.0"; id=5; method="tools/call"; params=@{name="schema_mutation"; arguments=@{}}} | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8788 -Method Post -ContentType application/json -Headers $headers -Body $body
```

Expect withheld-response error `-32042` and causal evidence in audit.

Audit verification:

```powershell
Invoke-RestMethod http://127.0.0.1:8788/v1/audit | ConvertTo-Json -Depth 8
```

Records contain server/session/tool identity, forwarded state, decision, trace, risk/trust fields where evaluated, fingerprints, reasons, and latency. They intentionally do not contain raw request arguments.

## Shutdown

Press `Ctrl+C` in the gateway terminal and then the mock-server terminal. Do not expose either port through a public bind or firewall rule.

See `docs/troubleshooting.md` for common failures.
