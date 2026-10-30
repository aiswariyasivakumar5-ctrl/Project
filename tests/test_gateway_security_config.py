import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path

from sentinel.gateway import (
    GatewayConfig,
    SentinelGateway,
    UpstreamSessionBinding,
    create_gateway_server,
)
from sentinel.novelty import NoveltyConfig


class GatewaySecurityConfigTests(unittest.TestCase):
    def test_gateway_config_rejects_unsafe_limits_credentials_and_mappings(self):
        invalid = (
            {"timeout_seconds": 0},
            {"request_timeout_seconds": float("inf")},
            {"confirm_timeout_seconds": True},
            {"resolved_action_ttl_seconds": -1},
            {"rate_limit": float("nan")},
            {"rate_burst": True},
            {"rate_limit": 1},
            {"audit_log_max_bytes": 10},
            {"log_level": "TRACE"},
            {"max_pending_actions": 0},
            {"auth_token": "x"},
            {"client_auth_token": "short"},
            {"auth_token": "same-credential-value", "client_auth_token": "same-credential-value"},
            {"tls_client_ca": "ca.pem"},
            {"allowed_tools": ["safe_read"]},
            {"allowed_tools": ("safe_read", "safe_read")},
            {"allowed_hosts": ("localhost", "localhost")},
            {"allowed_origins": ("",)},
            {"allowed_methods": ("tools/call",)},
            {"upstream_headers": [("Authorization", "TOKEN")]},
            {"upstream_headers": (("Host", "TOKEN"),)},
            {"upstream_headers": (("X-Token", "bad-name"),)},
            {"upstream_headers": (("X-Token", "TOKEN"), ("x-token", "OTHER"))},
            {"max_connections": True},
            {"max_request_bytes": 0},
            {"upstream_url": "ftp://example.com/mcp"},
            {"upstream_url": "http://user:secret@example.com/mcp"},
            {"novelty_config": object()},
            {"novelty_config": NoveltyConfig(unreviewed_trust_floor=1.1)},
            {"novelty_config": NoveltyConfig(capability_trust=1)},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                kwargs = {
                    "upstream_url": "http://127.0.0.1:8765",
                    "server_id": "server",
                    **overrides,
                }
                GatewayConfig(**kwargs)

    def test_credentials_file_maps_hashes_to_client_ids(self):
        token = "some-high-entropy-client-token"
        digest = hashlib.sha256(token.encode()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            path.write_text(json.dumps({digest: "team-a"}), encoding="utf-8")
            gateway = SentinelGateway(
                GatewayConfig("http://127.0.0.1:8765", "server", credentials_file=str(path))
            )
        self.assertEqual(gateway.client_credentials[digest], "team-a")

    def test_non_loopback_plaintext_bind_requires_explicit_override(self):
        config = GatewayConfig("http://127.0.0.1:8765", "server")
        with self.assertRaisesRegex(ValueError, "non-loopback plaintext"):
            create_gateway_server(config, host="0.0.0.0", port=0)

    def test_tls_certificate_and_key_are_a_pair(self):
        with self.assertRaisesRegex(ValueError, "configured together"):
            GatewayConfig("http://127.0.0.1:8765", "server", tls_cert="cert.pem")

    def test_rate_bucket_refills_and_rejects_excess(self):
        gateway = SentinelGateway(
            GatewayConfig("http://127.0.0.1:8765", "server", rate_limit=1, rate_burst=1)
        )
        self.assertTrue(gateway.allow_rate("client")[0])
        allowed, retry = gateway.allow_rate("client")
        self.assertFalse(allowed)
        self.assertGreater(retry, 0)

    def test_session_id_cannot_be_reused_by_a_different_authenticated_client(self):
        gateway = SentinelGateway(GatewayConfig("http://127.0.0.1:8765", "server"))
        gateway._uses_upstream_sessions = True
        gateway._upstream_sessions["downstream-A"] = UpstreamSessionBinding(
            "client-A", "upstream-A", "2025-06-18"
        )
        gateway.in_process_forwarder = lambda payload: self.fail(
            "spoofed session must not reach the upstream"
        )
        status, body, _ = gateway.handle(
            b'{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}',
            {
                "mcp-session-id": "downstream-A",
                "x-sentinel-authenticated-client": "client-B",
            },
        )
        self.assertEqual(status, 404)
        self.assertIn(b"unknown MCP session", body)

    def test_expired_downstream_session_is_removed(self):
        gateway = SentinelGateway(
            GatewayConfig("http://127.0.0.1:8765", "server", session_ttl_seconds=1)
        )
        gateway._uses_upstream_sessions = True
        binding = UpstreamSessionBinding("client-A", "upstream-A", None)
        binding.last_used = time.monotonic() - 2
        gateway._upstream_sessions["stale"] = binding
        status, _, _ = gateway.handle(
            b'{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}',
            {"mcp-session-id": "stale", "x-sentinel-authenticated-client": "client-A"},
        )
        self.assertEqual(status, 404)
        self.assertNotIn("stale", gateway._upstream_sessions)


if __name__ == "__main__":
    unittest.main()
