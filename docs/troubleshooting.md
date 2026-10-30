# Troubleshooting

## Python or activation problems

- Require Python 3.11+: `py -0p` lists installed interpreters.
- PowerShell activation: `.\.venv\Scripts\Activate.ps1`.
- If execution policy blocks activation, invoke `.\.venv\Scripts\python.exe` directly rather than weakening machine policy.

## Missing NumPy or build dependency

Run `python -m pip install -e .` with network access. In an offline environment with compatible inherited packages, follow the `--system-site-packages` and `--no-build-isolation` procedure in `docs/dependencies.md`. Do not install PyTorch/TensorFlow; the project does not require them.

## Port already in use

```powershell
Get-NetTCPConnection -LocalPort 8788,8790 -State Listen
```

Stop only the process you own or choose alternate `--port` values. For the automated demo: `.\scripts\demo.ps1 -MockPort 8890 -GatewayPort 8888`.

## Gateway cannot reach upstream

Start the mock server first and verify the gateway `--upstream` URL and port. `Invoke-RestMethod http://127.0.0.1:8788/health` checks gateway availability, not upstream tool correctness.

## MCP client cannot connect

Use HTTP POST with `Content-Type: application/json`. The prototype supports single JSON-RPC messages, not stdio, batch, SSE, or Streamable HTTP session negotiation.

## Malformed JSON-RPC

Every request needs `jsonrpc: "2.0"`, a supported method, object params, and an ID except notifications. Malformed JSON returns `-32700`; unsupported gateway methods return `-32601`.

## Oversized request payload (HTTP 413)

Requests with a `Content-Length` header exceeding `--max-request-bytes` (default 1 MB, 1,048,576 bytes) return HTTP 413 (Payload Too Large) and the connection is closed before reading the body into memory. If larger payloads or tool arguments are legitimately required, increase `--max-request-bytes` in the gateway configuration.

## PowerShell JSON issues

Use hashtables plus `ConvertTo-Json -Depth 8`; avoid hand-escaped JSON. Backticks shown in documentation are PowerShell line continuations and must be the final character on the line.

## Missing result directory

Experiment commands create their output directories. Use a new path such as `results/reproduction_smoke`; do not point smoke commands at `results/baselines_publication`, `results/ablations_publication`, or other approved directories.

## Withheld safe-looking response

Inspect `X-Sentinel-Decision`, `X-Sentinel-Trace`, and `/v1/audit`. Warm-up, intent text, causal evidence, capability changes, and response content affect the existing decision; do not lower thresholds for a demo.
