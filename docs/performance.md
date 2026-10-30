# Gateway performance measurements

Use `python scripts/benchmark_gateway_concurrency.py --url https://gateway.example`
with `MCP_SENTINEL_CLIENT_TOKEN` set in the environment. Run the same workload
before and after changes on the same host, upstream, baseline, request count, and
worker count. The script reports throughput, mean latency, and p99 latency.

No defensible before/after throughput or p99 numbers are recorded from this
workspace: its sandbox rejects loopback socket operations with Windows
`WinError 10013`, so a local gateway benchmark cannot complete. Run the script
in the deployment or CI environment and append both result objects here before
using them to size production capacity. Detector scoring behavior was left
unchanged; engine lock wait is exposed as `mcp_sentinel_lock_wait_milliseconds_total`
to help profile contention in that run.
