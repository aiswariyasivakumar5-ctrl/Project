from __future__ import annotations

import json
import statistics
import threading
import time
import tracemalloc
import urllib.request

from .engine import SentinelEngine
from .gateway import GatewayConfig, create_gateway_server
from .mock_server import create_mock_server


def _rpc(url: str, payload: dict, headers: dict[str, str] | None = None) -> float:
    request = urllib.request.Request(
        url,
        json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=3) as response:
        response.read()
    return (time.perf_counter() - started) * 1000


def run_gateway_benchmark(requests: int = 100) -> dict[str, float | int]:
    client_token = "benchmark-client-token-0123456789abcdef"
    mock_server, _ = create_mock_server()
    mock_thread = threading.Thread(target=mock_server.serve_forever, daemon=True)
    mock_thread.start()
    direct_url = f"http://127.0.0.1:{mock_server.server_address[1]}"
    gateway_server, _ = create_gateway_server(
        GatewayConfig(
            direct_url,
            "benchmark-mcp",
            timeout_seconds=3,
            allowed_tools=("safe_read", "calculate"),
            client_auth_token=client_token,
        ),
        SentinelEngine(10),
        port=0,
    )
    gateway_thread = threading.Thread(target=gateway_server.serve_forever, daemon=True)
    gateway_thread.start()
    gateway_url = f"http://127.0.0.1:{gateway_server.server_address[1]}"
    list_payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    _rpc(gateway_url, list_payload, {"Authorization": f"Bearer {client_token}"})
    headers = {
        "Authorization": f"Bearer {client_token}",
        "X-Sentinel-Intent": "Read record benchmark",
        "X-Sentinel-Session": "benchmark",
    }
    direct: list[float] = []
    proxied: list[float] = []
    tracemalloc.start()
    try:
        for index in range(requests):
            payload = {
                "jsonrpc": "2.0",
                "id": index + 10,
                "method": "tools/call",
                "params": {
                    "name": "safe_read",
                    "arguments": {"record_id": f"benchmark-{index % 8}"},
                },
            }
            direct.append(_rpc(direct_url, payload))
            proxied.append(_rpc(gateway_url, payload, headers))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        gateway_server.shutdown()
        mock_server.shutdown()
        gateway_server.server_close()
        mock_server.server_close()
    direct_mean = statistics.mean(direct)
    gateway_mean = statistics.mean(proxied)
    return {
        "requests": requests,
        "direct_mean_ms": direct_mean,
        "direct_p95_ms": sorted(direct)[max(0, int(len(direct) * 0.95) - 1)],
        "direct_throughput_rps_sequential": 1000 / direct_mean,
        "gateway_mean_ms": gateway_mean,
        "proxy_overhead_ms": gateway_mean - direct_mean,
        "gateway_p95_ms": sorted(proxied)[max(0, int(len(proxied) * 0.95) - 1)],
        "gateway_throughput_rps_sequential": 1000 / gateway_mean,
        "tracemalloc_peak_bytes": peak,
    }


def print_gateway_benchmark(requests: int = 100) -> None:
    print(json.dumps(run_gateway_benchmark(requests), indent=2))
