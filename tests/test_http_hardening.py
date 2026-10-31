import copy
import hashlib
import http.client
import io
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock

from sentinel.attestation import AttestationManager
from sentinel.engine import SentinelEngine
from sentinel.gateway import GatewayConfig, SentinelGateway, make_gateway_handler
from sentinel.jsonrpc import JsonRpcError, parse_request, validate_response
from sentinel.models import Interaction
from sentinel.service import make_handler
from sentinel.validation import load_json, read_body, validate_json


class AttestationHardeningTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.manager = AttestationManager(clock=lambda: self.now, ttl_seconds=5, max_pending=2)
        self.manager.enroll("srv", "digest")

    def answer(self, challenge, server="srv"):
        echo = hashlib.sha256(f"{challenge.nonce}:digest".encode()).hexdigest()
        return self.manager.verify(challenge.challenge_id, "digest", echo, server_id=server)

    def test_server_binding_single_use_and_expiry_boundary(self):
        challenge = self.manager.issue("srv")
        self.assertFalse(self.answer(challenge, "other"))
        self.assertTrue(self.answer(challenge))
        self.assertFalse(self.answer(challenge))
        challenge = self.manager.issue("srv")
        self.now = challenge.expires_at
        self.assertFalse(self.answer(challenge))

    def test_wrong_answer_consumes_challenge(self):
        challenge = self.manager.issue("srv")
        self.assertFalse(
            self.manager.verify(challenge.challenge_id, "digest", "bad", server_id="srv")
        )
        self.assertFalse(self.answer(challenge))

    def test_capacity_and_deepcopy(self):
        first = self.manager.issue("srv")
        self.manager.issue("srv")
        last = self.manager.issue("srv")
        self.assertEqual(len(self.manager.pending), 2)
        self.assertFalse(self.answer(first))
        restored = copy.deepcopy(self.manager)
        self.manager.discard(last.challenge_id)
        self.assertIn(last.challenge_id, restored.pending)

    def test_clock_failure_invalidates_pending(self):
        for bad in (9.0, float("nan"), float("inf")):
            self.now = 10.0
            challenge = self.manager.issue("srv")
            self.now = bad
            self.assertFalse(self.answer(challenge))
            self.assertEqual(self.manager.pending, {})

    def test_concurrent_replay_only_one_succeeds(self):
        challenge = self.manager.issue("srv")
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.answer(challenge), range(16)))
        self.assertEqual(sum(results), 1)


class BoundaryHardeningTests(unittest.TestCase):
    def test_json_depth_limit_accepts_boundary_and_rejects_one_level_over(self):
        validate_json([[0]], max_depth=2)
        with self.assertRaisesRegex(ValueError, "exceeds limits"):
            validate_json([[[0]]], max_depth=2)

    def test_ambiguous_and_nonfinite_json_rejected(self):
        for body in (
            b'{"a":1,"a":2}',
            b'{"a":NaN}',
            b'{"a":1e999}',
            b'{"a":"\\ud800"}',
            b"[" * 70 + b"0" + b"]" * 70,
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                load_json(body)

    def test_boolean_and_missing_response_ids_rejected(self):
        with self.assertRaises(JsonRpcError):
            parse_request(b'{"jsonrpc":"2.0","id":true,"method":"tools/list"}')
        for response in (
            {"jsonrpc": "2.0", "id": True, "result": {}},
            {"jsonrpc": "2.0", "result": {}},
            {"jsonrpc": "2.0", "id": 1, "error": {"code": True, "message": "bad"}},
        ):
            with self.assertRaises(JsonRpcError):
                validate_response(response, 1)

    def test_request_framing_rejected_before_read(self):
        for entries in (
            [],
            [("Content-Length", "-1")],
            [("Content-Length", "11")],
            [("Content-Length", "2"), ("Content-Length", "2")],
            [("Content-Length", "2"), ("Transfer-Encoding", "chunked")],
        ):
            headers = Message()
            for key, value in entries:
                headers[key] = value
            handler = SimpleNamespace(headers=headers, rfile=io.BytesIO(b"{}"), connection=Mock())
            with self.assertRaises(ValueError):
                read_body(handler, 10, 1)
            self.assertEqual(handler.rfile.tell(), 0)

    def test_invalid_interaction_fields(self):
        base = dict(
            server_id="srv",
            tool_name="read",
            arguments={},
            response={},
            latency_ms=1,
            user_intent="read",
        )
        for change in (
            {"latency_ms": -1},
            {"timestamp": True},
            {"success": "false"},
            {"arguments": []},
            {"session_id": "s" * 129},
            {"server_id": []},
        ):
            with self.assertRaises(ValueError):
                Interaction.from_dict(base | change)

    def test_invalid_metadata_does_not_replace_cache(self):
        gateway = SentinelGateway(GatewayConfig("http://unused", "srv"))
        gateway.tool_metadata = {"known": {"name": "known"}}
        for tools in (
            [{"name": "bad", "annotations": []}],
            [{"name": "bad", "annotations": {"destructiveHint": "false"}}],
            [{"name": "same"}, {"name": "same"}],
        ):
            gateway._forward = Mock(
                return_value=(
                    200,
                    json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": tools}}).encode(),
                    "application/json",
                    {},
                )
            )
            with self.assertRaises(JsonRpcError):
                gateway.handle(b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}', {})
            self.assertEqual(list(gateway.tool_metadata), ["known"])

    def test_oversized_identity_never_forwarded(self):
        gateway = SentinelGateway(GatewayConfig("http://unused", "srv"))
        gateway._forward = Mock()
        with self.assertRaises(JsonRpcError):
            gateway.handle(
                b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}', {"x-sentinel-session": "s" * 129}
            )
        gateway._forward.assert_not_called()

    def test_failed_attestation_transport_discards_pending(self):
        gateway = SentinelGateway(GatewayConfig("http://unused", "srv"))
        gateway.engine.attestation.enroll("srv", "digest")
        challenge = gateway.engine.attestation.issue("srv")
        gateway._forward = Mock(side_effect=JsonRpcError(-32050, "unavailable"))
        self.assertFalse(gateway._execute_attestation(challenge.to_dict()))
        self.assertEqual(gateway.engine.attestation.pending, {})

    def test_http_rejects_malformed_length_and_service_payload(self):
        engine = SentinelEngine()
        gateway = SentinelGateway(
            GatewayConfig(
                "http://unused", "srv", client_auth_token="test-client-auth-token-0123456789abcdef"
            ),
            engine,
        )
        gateway._forward = Mock()
        for handler, path in (
            (make_handler(engine), "/v1/evaluate"),
            (make_gateway_handler(gateway), "/"),
        ):
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                # Invalid framing is rejected before reading a body. Do not send
                # unread body bytes here: closing with those bytes outstanding
                # can reset the TCP connection on Windows before the error is
                # received. Keep the error-response assertions strict below.
                for body, length in ((b"", "oops"), (b'{"latency_ms":NaN}', "17")):
                    connection = http.client.HTTPConnection(*server.server_address, timeout=2)
                    try:
                        connection.request(
                            "POST",
                            path,
                            body=body,
                            headers={
                                "Content-Length": length,
                                "Authorization": "Bearer test-client-auth-token-0123456789abcdef",
                            },
                        )
                        response = connection.getresponse()
                        self.assertIn(response.status, (200, 400))
                        self.assertIn("error", json.loads(response.read()))
                    finally:
                        connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
        self.assertEqual(engine.profiles, {})
        gateway._forward.assert_not_called()

    def test_oversized_request_body_returns_413(self):
        engine = SentinelEngine()
        gateway = SentinelGateway(
            GatewayConfig(
                "http://unused",
                "srv",
                client_auth_token="test-client-auth-token-0123456789abcdef",
                max_request_bytes=512,
            ),
            engine,
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_gateway_handler(gateway))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection(*server.server_address, timeout=2)
            try:
                conn.request(
                    "POST",
                    "/",
                    body=b"",
                    headers={
                        "Content-Length": "1024",
                        "Content-Type": "application/json",
                        "Authorization": "Bearer test-client-auth-token-0123456789abcdef",
                    },
                )
                resp = conn.getresponse()
                self.assertEqual(resp.status, 413)
                data = json.loads(resp.read())
                self.assertIn("error", data)
            finally:
                conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
