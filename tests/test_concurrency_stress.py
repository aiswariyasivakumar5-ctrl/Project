import hashlib
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from sentinel.gateway import GatewayConfig, SentinelGateway, create_gateway_server
from sentinel_research.mock_server import create_mock_server
from sentinel.provenance import ProvenanceLedger


@pytest.mark.stress
class GatewayConcurrencyStressTests(unittest.TestCase):
    """Concurrency stress checks; run with `pytest -m stress`."""

    def test_recovery_probe_does_not_invert_gateway_and_engine_locks(self):
        class LockOrderRecorder:
            ranks = {"gateway": 0, "engine": 1}

            def __init__(self):
                self.local = threading.local()
                self.acquisitions = {}

            def acquire(self, name):
                thread_id = threading.get_ident()
                stack = getattr(self.local, "stack", [])
                if stack and self.ranks[name] < self.ranks[stack[-1]]:
                    raise AssertionError(
                        f"lock-order inversion: {stack[-1]} held before {name}"
                    )
                stack = [*stack, name]
                self.local.stack = stack
                self.acquisitions.setdefault(thread_id, []).append(tuple(stack))

            def release(self, name):
                stack = getattr(self.local, "stack", [])
                if not stack or stack[-1] != name:
                    raise AssertionError(f"lock release order mismatch for {name}: {stack}")
                self.local.stack = stack[:-1]

        class OwnedRLock:
            def __init__(self, order):
                self.lock = threading.RLock()
                self.order = order

            def acquire(self, *args, **kwargs):
                acquired = self.lock.acquire(*args, **kwargs)
                if acquired:
                    self.order.acquire("engine")
                return acquired

            def release(self):
                self.order.release("engine")
                self.lock.release()

            def __enter__(self):
                self.acquire()
                return self

            def __exit__(self, *args):
                self.release()

        class OrderedGatewayLock:
            def __init__(self, order):
                self.order = order
                self.lock = threading.RLock()

            def __enter__(self):
                self.order.acquire("gateway")
                self.lock.acquire()
                return self

            def __exit__(self, *args):
                self.lock.release()
                self.order.release("gateway")

        gateway = SentinelGateway(GatewayConfig("http://127.0.0.1:8765", "stress", novelty=True))
        order = LockOrderRecorder()
        engine_lock = OwnedRLock(order)
        gateway.engine.lock = engine_lock
        gateway._lock = OrderedGatewayLock(order)
        gateway._recovery_event = lambda *args: SimpleNamespace(
            server_id="stress",
            session_id="session",
            tool_name="safe_read",
            response=None,
            success=False,
            latency_ms=0.0,
        )
        gateway._forward = lambda payload: (
            200,
            b'{"jsonrpc":"2.0","id":"sentinel-recovery","result":{"content":[]}}',
            "application/json",
            None,
        )
        gateway._execute_attestation = lambda challenge: True

        class FakeNovelty:
            recovery_approvals = {"key": object()}

            @staticmethod
            def recovery_key(event):
                return "key"

            @staticmethod
            def evaluate_recovery(event, *, independent_session, attested):
                return SimpleNamespace(
                    action=SimpleNamespace(value="allow"),
                    trace_id="trace",
                    reasons=[],
                    provenance=None,
                    to_dict=lambda: {"action": "allow"},
                )

            @staticmethod
            def invalidate_reviews(event, reason):
                raise AssertionError(reason)

        gateway.novelty = FakeNovelty()
        result = gateway.probe_recovery("safe_read", {}, "read", independent_identity="operator")
        self.assertEqual(result, {"action": "allow"})
        self.assertTrue(order.acquisitions)
        self.assertTrue(all(stack for stacks in order.acquisitions.values() for stack in stacks))

    def test_simultaneous_create_approve_deny_and_expire(self):
        for workers in (2, 4, 8):
            for _round_number in range(17):
                gateway = SentinelGateway(GatewayConfig("http://127.0.0.1:8765", "stress"))
                barrier = threading.Barrier(workers)
                actions = [None] * workers
                errors = []

                def create(
                    index,
                    gateway=gateway,
                    actions=actions,
                    barrier=barrier,
                    errors=errors,
                    workers=workers,
                    round_number=_round_number,
                ):
                    try:
                        barrier.wait()
                        actions[index] = gateway.create_pending_action(
                            f"trace-{workers}-{round_number}-{index}",
                            "session",
                            "tool",
                            {},
                            b"payload",
                            ["review"],
                        )
                    except BaseException as exc:
                        errors.append(exc)

                threads = [threading.Thread(target=create, args=(i,)) for i in range(workers)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(5)
                self.assertFalse(any(thread.is_alive() for thread in threads))
                self.assertEqual(errors, [])
                self.assertTrue(all(actions))

                barrier = threading.Barrier(workers)
                outcomes = [None] * workers

                def resolve(
                    index,
                    actions=actions,
                    barrier=barrier,
                    gateway=gateway,
                    outcomes=outcomes,
                    errors=errors,
                ):
                    action = actions[index]
                    try:
                        barrier.wait()
                        if index % 3 == 0:
                            outcomes[index] = gateway.approve_action(action.action_id)["status"]
                        elif index % 3 == 1:
                            outcomes[index] = gateway.deny_action(action.action_id)["status"]
                        else:
                            with gateway._lock:
                                gateway.pending_actions[action.action_id].expires_at = (
                                    time.time() - 1
                                )
                            outcomes[index] = gateway.get_action(action.action_id)["status"]
                    except BaseException as exc:
                        errors.append(exc)

                threads = [threading.Thread(target=resolve, args=(i,)) for i in range(workers)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(5)
                self.assertFalse(any(thread.is_alive() for thread in threads))
                self.assertEqual(errors, [])
                for i, outcome in enumerate(outcomes):
                    self.assertEqual(outcome, ("approved", "denied", "expired")[i % 3])

    def test_concurrent_state_save_and_profile_rate_mutation_roundtrips(self):
        for workers in (2, 4, 8):
            for _round_number in range(17):
                gateway = SentinelGateway(
                    GatewayConfig(
                        "http://127.0.0.1:8765", "stress", rate_limit=10000, rate_burst=10000
                    )
                )
                gateway.in_process_forwarder = lambda payload: (
                    200,
                    json.dumps(
                        {"jsonrpc": "2.0", "id": payload["id"], "result": {"content": []}}
                    ).encode(),
                    "application/json",
                )
                with tempfile.TemporaryDirectory() as directory:
                    state_path = Path(directory) / "state.json"
                    start = threading.Barrier(workers + 1)
                    errors = []

                    def mutate(index, gateway=gateway, start=start, errors=errors):
                        try:
                            start.wait()
                            for n in range(4):
                                gateway.allow_rate(f"client-{index}")
                                gateway.handle(
                                    json.dumps(
                                        {
                                            "jsonrpc": "2.0",
                                            "id": index * 10 + n,
                                            "method": "tools/call",
                                            "params": {
                                                "name": "safe_read",
                                                "arguments": {"record_id": str(n)},
                                            },
                                        }
                                    ).encode(),
                                    {
                                        "x-sentinel-session": f"session-{index}",
                                        "x-sentinel-intent": "read record",
                                    },
                                )
                        except BaseException as exc:
                            errors.append(exc)

                    threads = [threading.Thread(target=mutate, args=(i,)) for i in range(workers)]
                    for thread in threads:
                        thread.start()
                    start.wait()
                    for _ in range(4):
                        gateway.save_state(state_path)
                    for thread in threads:
                        thread.join(10)
                    self.assertFalse(any(thread.is_alive() for thread in threads))
                    self.assertEqual(errors, [])
                    gateway.save_state(state_path)
                    persisted = json.loads(state_path.read_text(encoding="utf-8"))
                    restored = SentinelGateway(gateway.config)
                    restored.load_state(state_path)
                    current = restored.export_state()
                    self.assertEqual(persisted["engine"], current["engine"])
                    self.assertEqual(persisted["pending_actions"], current["pending_actions"])
                    self.assertEqual(persisted["tool_metadata"], current["tool_metadata"])

    def test_provenance_single_use_is_atomic_under_contention(self):
        for workers in (2, 4, 8):
            for _ in range(17):
                ledger = ProvenanceLedger()
                claim = ledger.issue("origin", "read", "session", "stress", "safe_read", {"id": 1})
                barrier = threading.Barrier(workers)
                successes = []

                def consume(ledger=ledger, claim=claim, barrier=barrier, successes=successes):
                    barrier.wait()
                    result = ledger.validate(
                        claim.claim_id,
                        intent="read",
                        session_id="session",
                        server_id="stress",
                        tool_name="safe_read",
                        arguments={"id": 1},
                    )
                    successes.append(result.valid)

                threads = [threading.Thread(target=consume) for _ in range(workers)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(5)
                self.assertFalse(any(thread.is_alive() for thread in threads))
                self.assertEqual(sum(successes), 1)

    def test_credential_reload_during_authenticated_requests(self):
        for workers in (2, 4, 8):
            for round_number in range(17):
                with tempfile.TemporaryDirectory() as directory:
                    credentials_path = Path(directory) / "credentials.json"
                    tokens = (
                        f"old-token-{workers}-{round_number}",
                        f"new-token-{workers}-{round_number}",
                    )
                    credentials_path.write_text(
                        json.dumps({hashlib.sha256(tokens[0].encode()).hexdigest(): "client"}),
                        encoding="utf-8",
                    )
                    upstream, upstream_state = create_mock_server()
                    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
                    upstream_thread.start()
                    gateway = SentinelGateway(
                        GatewayConfig(
                            f"http://127.0.0.1:{upstream.server_address[1]}",
                            "stress",
                            allowed_tools=("safe_read",),
                            credentials_file=str(credentials_path),
                        )
                    )
                    server, _ = create_gateway_server(gateway.config, port=0)
                    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
                    server_thread.start()
                    url = f"http://127.0.0.1:{server.server_address[1]}"
                    barrier = threading.Barrier(workers + 1)
                    errors = []
                    statuses = []

                    def request(
                        index,
                        barrier=barrier,
                        tokens=tokens,
                        url=url,
                        statuses=statuses,
                        errors=errors,
                    ):
                        try:
                            barrier.wait()
                            token = tokens[index % 2]
                            req = urllib.request.Request(
                                url,
                                data=json.dumps(
                                    {
                                        "jsonrpc": "2.0",
                                        "id": index + 1,
                                        "method": "initialize",
                                        "params": {
                                            "protocolVersion": "2025-06-18",
                                            "capabilities": {},
                                            "clientInfo": {"name": "stress", "version": "1"},
                                        },
                                    }
                                ).encode(),
                                headers={
                                    "Authorization": f"Bearer {token}",
                                    "Content-Type": "application/json",
                                },
                            )
                            try:
                                with urllib.request.urlopen(req, timeout=5) as response:
                                    statuses.append(response.status)
                            except urllib.error.HTTPError as exc:
                                statuses.append(exc.code)
                        except BaseException as exc:
                            errors.append(exc)

                    threads = [threading.Thread(target=request, args=(i,)) for i in range(workers)]
                    try:
                        for thread in threads:
                            thread.start()
                        barrier.wait()
                        credentials_path.write_text(
                            json.dumps({hashlib.sha256(tokens[1].encode()).hexdigest(): "client"}),
                            encoding="utf-8",
                        )
                        gateway.reload_client_credentials()
                        for thread in threads:
                            thread.join(8)
                        self.assertFalse(any(thread.is_alive() for thread in threads))
                        self.assertEqual(errors, [])
                        self.assertEqual(len(statuses), workers)
                        self.assertTrue(all(status in (200, 401) for status in statuses), statuses)
                    finally:
                        server.shutdown()
                        upstream.shutdown()
                        server.server_close()
                        upstream.server_close()
