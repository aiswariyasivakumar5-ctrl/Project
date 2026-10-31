from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from .engine import SentinelEngine
from .http_limits import BoundedHTTPServer, remaining, timed_lock
from .models import Interaction
from .validation import load_json, read_body


def make_handler(engine: SentinelEngine) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, payload: object) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._json(200, {"status": "ok", "servers": len(engine.profiles)})
            elif self.path.startswith("/v1/traces/"):
                trace_id = self.path.rsplit("/", 1)[-1]
                try:
                    with timed_lock(engine.lock):
                        trace = engine.causal_graph.trace(trace_id)
                    self._json(200, trace)
                except KeyError:
                    self._json(404, {"error": "trace not found"})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/evaluate":
                self._json(404, {"error": "not found"})
                return
            try:
                event = Interaction.from_dict(load_json(read_body(self, 1_048_576, 5.0)))
                with timed_lock(engine.lock):
                    verdict = engine.evaluate(event).to_dict()
                remaining()
                self._json(200, verdict)
            except (TypeError, ValueError, TimeoutError) as exc:
                self.close_connection = True
                self._json(400, {"error": str(exc)})

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def create_service_server(
    engine: SentinelEngine | None = None,
    host: str = "127.0.0.1",
    port: int = 8787,
    *,
    max_connections: int = 32,
    request_timeout: float = 10.0,
) -> BoundedHTTPServer:
    return BoundedHTTPServer(
        (host, port),
        make_handler(engine or SentinelEngine()),
        max_connections=max_connections,
        request_timeout=request_timeout,
    )


def serve(
    host: str = "127.0.0.1",
    port: int = 8787,
    *,
    max_connections: int = 32,
    request_timeout: float = 10.0,
) -> None:
    server = create_service_server(
        host=host, port=port, max_connections=max_connections, request_timeout=request_timeout
    )
    print(f"MCP Runtime Sentinel listening on http://{host}:{port}")
    server.serve_forever()
