"""Smoke-test the compose gateway through its published TLS endpoint."""

from __future__ import annotations

import http.client
import json
import os
import ssl
import time
import urllib.error
import urllib.request


def rpc(
    url: str,
    token: str,
    method: str,
    request_id: int,
    params: dict | None = None,
    *,
    session_id: str | None = None,
    protocol: str | None = None,
) -> tuple[dict, object]:
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
    request = urllib.request.Request(
        url,
        json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Sentinel-Intent": "Docker production smoke check",
            "X-Sentinel-Session": "docker-smoke",
            **({"Mcp-Session-Id": session_id} if session_id else {}),
            **({"MCP-Protocol-Version": protocol} if protocol else {}),
        },
    )
    with urllib.request.urlopen(
        request, context=ssl._create_unverified_context(), timeout=5
    ) as response:
        return json.loads(response.read()), response.headers


def notify_initialized(url: str, token: str, session_id: str, protocol: str) -> None:
    request = urllib.request.Request(
        url,
        b'{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}',
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Sentinel-Intent": "Docker production smoke check",
            "X-Sentinel-Session": "docker-smoke",
            "Mcp-Session-Id": session_id,
            "MCP-Protocol-Version": protocol,
        },
    )
    with urllib.request.urlopen(
        request, context=ssl._create_unverified_context(), timeout=5
    ) as response:
        assert response.status == 202


def main() -> None:
    token = os.environ.get("MCP_SENTINEL_CLIENT_TOKEN")
    if not token:
        raise SystemExit("MCP_SENTINEL_CLIENT_TOKEN is required")
    url = "https://127.0.0.1:8788"
    context = ssl._create_unverified_context()
    # Cleartext clients must fail the TLS listener's handshake.
    try:
        urllib.request.urlopen("http://127.0.0.1:8788/livez", timeout=2)
        raise AssertionError("gateway accepted a plaintext request on its TLS port")
    except (urllib.error.URLError, OSError, http.client.HTTPException):
        pass
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "/readyz", context=context, timeout=2).read()
            break
        except Exception:
            time.sleep(1)
    else:
        raise SystemExit("gateway did not become ready")
    initialized, init_headers = rpc(
        url,
        token,
        "initialize",
        1,
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "docker-smoke", "version": "1"},
        },
    )
    assert "result" in initialized
    session_id = init_headers.get("Mcp-Session-Id")
    protocol = init_headers.get("MCP-Protocol-Version", "2025-06-18")
    assert session_id
    notify_initialized(url, token, session_id, protocol)
    listing, _ = rpc(url, token, "tools/list", 2, session_id=session_id, protocol=protocol)
    assert "result" in listing and "tools" in listing["result"]
    called, _ = rpc(
        url,
        token,
        "tools/call",
        3,
        {
            "name": "safe_read",
            "arguments": {"record_id": "smoke"},
        },
        session_id=session_id,
        protocol=protocol,
    )
    assert "result" in called
    for attempt in range(11):
        bad_request = urllib.request.Request(
            url,
            b'{"jsonrpc":"2.0","id":99,"method":"tools/list"}',
            headers={
                "Authorization": "Bearer invalid-token",
                "Content-Type": "application/json",
            },
        )
        try:
            urllib.request.urlopen(bad_request, context=context, timeout=3)
            raise AssertionError("invalid client token was accepted")
        except urllib.error.HTTPError as error:
            assert error.code == (429 if attempt == 10 else 401)
    print("Docker TLS gateway smoke test passed")


if __name__ == "__main__":
    main()
