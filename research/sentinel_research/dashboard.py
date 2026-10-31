"""Loopback-only visual demo using real HTTP gateway calls and safe mock servers."""

import json
import secrets
import threading
import traceback
from collections import deque
from dataclasses import replace
from http.server import BaseHTTPRequestHandler
from importlib.resources import files

from .experiment import ExperimentConfig
from sentinel.http_limits import BoundedHTTPServer
from .novelty_experiment import NoveltyLiveExperiment
from .novelty_scenarios import build_novelty_scenarios
from sentinel.validation import read_body
from .workload import normal_workload

SCENARIOS = {
    "normal": (
        "Normal reads",
        "Six benign requests. Observe actual decisions, including any false positives.",
    ),
    "intent_mismatch": (
        "Intent mismatch",
        "A read intent requests simulated deletion. No real files are touched.",
    ),
    "capability_laundering": (
        "Capability misuse",
        "Mock export misuse alternates with benign reads to show scoped trust.",
    ),
    "schema_stable_response": (
        "Response injection",
        "Mock responses contain an injection while keeping their usual schema.",
    ),
    "distributed_poisoning": (
        "Learning protection",
        "One fixture identity rotates sessions with an unapproved argument shape.",
    ),
}


class DemoSession:
    def __init__(self):
        self.lock = threading.Lock()
        self.events = deque(maxlen=200)
        self.total = 0
        self.live = NoveltyLiveExperiment(
            ExperimentConfig(training_events=100), "approval_required"
        )

    def __enter__(self):
        try:
            self.live.__enter__()
            self.live.run_phase(normal_workload(100, 42, "dashboard-enrollment"), True, 1000, True)
            self.checkpoint = self.live.checkpoint()
            self.live.restore(self.checkpoint)
            return self
        except BaseException:
            self.live.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        self.live.__exit__(*args)

    def run(self, name):
        if name not in SCENARIOS:
            raise ValueError("Unknown demo scenario")
        if name in ("normal", "intent_mismatch"):
            cases = normal_workload(6, 42, "dashboard-normal")
            if name == "intent_mismatch":
                case = cases[0]
                cases = [
                    replace(
                        case,
                        interaction=replace(
                            case.interaction, tool_name="simulated_delete", side_effect=True
                        ),
                        malicious=True,
                    )
                ]
        else:
            cases = build_novelty_scenarios(42, 6)[name].scenario.cases
        # Calls remain sequential; partial successful calls stay visible if a later call fails.
        for case in cases:
            _, detail = self.live.execute(case, 2000 + self.total, learn=True)
            self.total += 1
            self.events.append({**detail, "event_id": self.total, "demo_scenario": name})

    def reset(self):
        self.live.restore(self.checkpoint)
        self.events.clear()
        self.total = 0

    def snapshot(self):
        capabilities = []
        for gateway in self.live.gateways.values():
            if gateway.novelty:
                for (server, tool), state in gateway.novelty.capabilities.states.items():
                    capabilities.append({"server": server, "tool": tool, "trust": state.trust})
        return {
            "events": list(self.events),
            "total": self.total,
            "retained_limit": 200,
            "capabilities": capabilities,
            "scenarios": SCENARIOS,
            "mode": "Safe mock servers · approval-required policy",
            "enrollment_events": 100,
            "learning_enabled": True,
        }


def create_dashboard(session, port=8765):
    token = secrets.token_urlsafe(32)
    assets = files("sentinel_research").joinpath("dashboard_assets")

    class Handler(BaseHTTPRequestHandler):
        def valid_host(self):
            return self.headers.get_all("Host") == [f"127.0.0.1:{self.server.server_port}"]

        def send(self, status, body, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def reply(self, status, data):
            self.send(status, json.dumps(data, allow_nan=False).encode())

        def do_GET(self):
            if not self.valid_host():
                return self.reply(403, {"error": "Loopback host required"})
            routes = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/style.css": ("style.css", "text/css; charset=utf-8"),
            }
            if self.path in routes:
                name, kind = routes[self.path]
                data = assets.joinpath(name).read_text(encoding="utf-8").replace("__TOKEN__", token)
                return self.send(200, data.encode(), kind)
            if self.path != "/api/state":
                return self.reply(404, {"error": "Not found"})
            if not session.lock.acquire(blocking=False):
                return self.reply(409, {"error": "Demo is running"})
            try:
                self.reply(200, session.snapshot())
            finally:
                session.lock.release()

        def do_POST(self):
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            if (
                not self.valid_host()
                or self.headers.get_all("Origin") != [expected_origin]
                or self.headers.get_all("X-Demo-Token") != [token]
            ):
                return self.reply(403, {"error": "Same-origin demo token required"})
            if self.path not in ("/api/run", "/api/reset"):
                return self.reply(404, {"error": "Not found"})
            try:
                body = json.loads(read_body(self, 1024, 3))
                if not isinstance(body, dict) or set(body) != (
                    {"scenario"} if self.path == "/api/run" else set()
                ):
                    raise ValueError("Invalid fields")
                if self.path == "/api/run" and (
                    not isinstance(body["scenario"], str) or body["scenario"] not in SCENARIOS
                ):
                    raise ValueError("Unknown scenario")
            except (ValueError, TimeoutError):
                return self.reply(400, {"error": "Invalid demo request"})
            if not session.lock.acquire(blocking=False):
                return self.reply(409, {"error": "Demo is already running"})
            try:
                if self.path == "/api/reset":
                    session.reset()
                else:
                    session.run(body["scenario"])
                self.reply(200, session.snapshot())
            except Exception:
                traceback.print_exc()
                self.reply(
                    502,
                    {
                        "error": "Gateway call failed. Partial events are retained; "
                        "no automatic retry. Reset or inspect the terminal."
                    },
                )
            finally:
                session.lock.release()

        def log_message(self, *args):
            pass

    return BoundedHTTPServer(("127.0.0.1", port), Handler, max_connections=8, request_timeout=30)


def serve_dashboard(port=8765):
    print("Preparing 100 benign enrollment calls against local mock servers…", flush=True)
    with DemoSession() as session:
        server = create_dashboard(session, port)
        print(f"Dashboard: http://127.0.0.1:{server.server_port}  (Ctrl+C to stop)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    serve_dashboard()
