import io
import json
import unittest

from sentinel.gateway import GatewayConfig, SentinelGateway


class GatewaySseParserTests(unittest.TestCase):
    def test_protocol_version_is_negotiated_from_initialize_result(self):
        gateway = SentinelGateway(GatewayConfig("http://127.0.0.1:1", "sse-test"))
        gateway.in_process_forwarder = lambda request: (
            200,
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "serverInfo": {},
                    },
                }
            ).encode(),
            "application/json",
        )
        _, _, headers = gateway.handle(
            b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}',
            {},
        )
        self.assertEqual(headers["MCP-Protocol-Version"], "2025-06-18")

    def test_selects_matching_json_rpc_event_from_sse_stream(self):
        gateway = SentinelGateway(GatewayConfig("http://127.0.0.1:1", "sse-test"))
        stream = io.BytesIO(
            b': keepalive\n\nevent: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n'
            b'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"ok":true}}\n\n'
        )
        body = gateway._read_sse_response(stream, 2)
        self.assertEqual(json.loads(body)["result"], {"ok": True})

    def test_notification_has_no_sse_response_body(self):
        gateway = SentinelGateway(GatewayConfig("http://127.0.0.1:1", "sse-test"))
        self.assertEqual(gateway._read_sse_response(io.BytesIO(b""), None), b"")

    def test_invalid_events_are_skipped_and_missing_response_fails(self):
        gateway = SentinelGateway(GatewayConfig("http://127.0.0.1:1", "sse-test"))
        stream = io.BytesIO(
            b"event: message\ndata: not-json\n\n"
            b"event: message\ndata: \xff\n\n"
            b": keepalive\n\n"
            b'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{}}\n\n'
        )
        with self.assertRaisesRegex(Exception, "without a matching"):
            gateway._read_sse_response(stream, 99)

    def test_sse_stream_size_limit_is_enforced(self):
        gateway = SentinelGateway(
            GatewayConfig("http://127.0.0.1:1", "sse-test", max_request_bytes=32)
        )
        stream = io.BytesIO(b"data: " + b"x" * 40 + b"\n\n")
        with self.assertRaisesRegex(Exception, "stream exceeds size limit"):
            gateway._read_sse_response(stream, 1)


if __name__ == "__main__":
    unittest.main()
