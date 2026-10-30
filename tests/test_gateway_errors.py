import json
import unittest

from sentinel.engine import SentinelEngine
from sentinel.gateway import GatewayConfig, SentinelGateway
from sentinel.jsonrpc import JsonRpcError


def call_payload(request_id=1):
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": "safe_read", "arguments": {"record_id": "one"}},
        }
    ).encode()


class GatewayErrorTests(unittest.TestCase):
    def gateway(self, fail_closed=True):
        return SentinelGateway(
            GatewayConfig(
                "http://127.0.0.1:1",
                "error-test",
                fail_closed=fail_closed,
                allowed_tools=("safe_read",),
            )
        )

    def test_response_id_mismatch_is_rejected(self):
        gateway = self.gateway()
        gateway._forward = lambda payload, **kwargs: (
            200,
            json.dumps({"jsonrpc": "2.0", "id": 999, "result": {}}).encode(),
            "application/json",
            {},
        )
        with self.assertRaises(JsonRpcError) as raised:
            gateway.handle(call_payload(1), {})
        self.assertEqual(raised.exception.code, -32054)

    def test_malformed_upstream_response_is_rejected(self):
        gateway = self.gateway()
        gateway._forward = lambda payload, **kwargs: (200, b"not-json", "text/plain", {})
        with self.assertRaises(JsonRpcError) as raised:
            gateway.handle(call_payload(), {})
        self.assertEqual(raised.exception.code, -32053)

    def test_analysis_failure_is_fail_closed(self):
        engine = SentinelEngine()
        gateway = SentinelGateway(
            GatewayConfig("http://unused", "error-test", allowed_tools=("safe_read",)), engine
        )
        gateway._forward = lambda payload, **kwargs: (
            200,
            json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": {"content": []}}).encode(),
            "application/json",
            {},
        )
        engine.evaluate = lambda event: (_ for _ in ()).throw(RuntimeError("detector failed"))
        with self.assertRaises(JsonRpcError) as raised:
            gateway.handle(call_payload(), {})
        self.assertEqual(raised.exception.code, -32055)

    def test_analysis_failure_can_be_explicitly_fail_open(self):
        engine = SentinelEngine()
        gateway = SentinelGateway(
            GatewayConfig(
                "http://unused", "error-test", fail_closed=False, allowed_tools=("safe_read",)
            ),
            engine,
        )
        gateway._forward = lambda payload, **kwargs: (
            200,
            json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": {"content": []}}).encode(),
            "application/json",
            {},
        )
        engine.evaluate = lambda event: (_ for _ in ()).throw(RuntimeError("detector failed"))
        _, body, _ = gateway.handle(call_payload(), {})
        self.assertIn("result", json.loads(body))

    def test_forward_rejects_invalid_json_before_upstream_dispatch(self):
        gateway = self.gateway()
        gateway.in_process_forwarder = lambda payload: self.fail(
            "invalid JSON must be rejected before dispatch"
        )
        with self.assertRaises(JsonRpcError) as raised:
            gateway._forward(b"{invalid")
        self.assertEqual(raised.exception.code, -32600)

    def test_handle_rejects_invalid_size_method_notifications_and_params(self):
        gateway = self.gateway()
        gateway.in_process_forwarder = lambda payload: self.fail(
            "invalid request must not reach the upstream"
        )
        invalid_requests = (
            b"",
            b"x" * (gateway.config.max_request_bytes + 1),
            b'{"jsonrpc":"2.0","id":1,"method":"unknown","params":{}}',
            b'{"jsonrpc":"2.0","id":1,"method":"notifications/initialized","params":{}}',
            b'{"jsonrpc":"2.0","method":"tools/call","params":{}}',
            b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":[]}',
            b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"","arguments":{}}}',
        )
        for body in invalid_requests:
            with self.subTest(body=body[:48]), self.assertRaises(JsonRpcError):
                gateway.handle(body, {})

        with self.assertRaises(JsonRpcError):
            gateway.handle(call_payload(), {"x-sentinel-session": ""})
        with self.assertRaises(JsonRpcError):
            gateway.handle(call_payload(), {"mcp-session-id": "unsafe\r"})


if __name__ == "__main__":
    unittest.main()
