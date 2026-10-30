"""Measure gateway throughput and p99 latency against an already-running gateway."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--token-env", default="MCP_SENTINEL_CLIENT_TOKEN")
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    token = os.environ.get(args.token_env)
    if not token:
        parser.error(f"environment variable {args.token_env} must contain the client token")
    latencies: list[float] = []

    def request(index: int) -> float:
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": index, "method": "tools/list", "params": {}}
        ).encode()
        req = urllib.request.Request(
            args.url,
            payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Sentinel-Intent": "benchmark list tools",
                "X-Sentinel-Session": "benchmark",
            },
        )
        started = time.perf_counter()
        with urllib.request.urlopen(req, timeout=10) as response:
            response.read()
        return (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        latencies = list(pool.map(request, range(args.requests)))
    elapsed = time.perf_counter() - started
    ordered = sorted(latencies)
    p99 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))]
    print(
        json.dumps(
            {
                "requests": len(latencies),
                "workers": args.workers,
                "throughput_per_second": len(latencies) / elapsed,
                "mean_latency_ms": statistics.fmean(latencies),
                "p99_latency_ms": p99,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
