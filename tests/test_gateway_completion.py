import json
import threading
import unittest
import urllib.request
from dataclasses import asdict
from unittest.mock import patch

from sentinel.gateway import GatewayConfig, SentinelGateway, create_gateway_server
from sentinel.jsonrpc import JsonRpcError
from sentinel_research.mock_server import create_mock_server
from sentinel.novelty import CapabilityState, NoveltyConfig


class GatewayCompletionTests(unittest.TestCase):
    CLIENT_TOKEN = "test-client-auth-token-0123456789abcdef"

    def test_tool_allowlist_fails_closed_before_dispatch(self):
        gateway = SentinelGateway(GatewayConfig("http://unused", "srv"))
        dispatched = []
        gateway.in_process_forwarder = lambda payload: (
            dispatched.append(payload)
            or (
                200,
                json.dumps({"jsonrpc": "2.0", "id": payload.get("id"), "result": {}}).encode(),
                "application/json",
            )
        )
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "write_file", "arguments": {"path": "x"}},
        }
        _, body, _ = gateway.handle(
            json.dumps(payload).encode(), {"x-sentinel-intent": "Write file x"}
        )
        self.assertEqual(json.loads(body)["error"]["code"], -32041)
        self.assertEqual(dispatched, [])
        self.assertFalse(gateway.audit[-1].forwarded)

    def test_allowlisted_tool_dispatches(self):
        gateway = SentinelGateway(
            GatewayConfig("http://unused", "srv", allowed_tools=("safe_read",))
        )
        gateway.in_process_forwarder = lambda payload: (
            200,
            json.dumps(
                {"jsonrpc": "2.0", "id": payload.get("id"), "result": {"content": []}}
            ).encode(),
            "application/json",
        )
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "safe_read", "arguments": {"record_id": "x"}},
        }
        _, body, _ = gateway.handle(
            json.dumps(payload).encode(), {"x-sentinel-intent": "Read record x"}
        )
        self.assertIn("result", json.loads(body))
        self.assertTrue(gateway.audit[-1].forwarded)

    def test_tools_list_hides_unapproved_tools(self):
        gateway = SentinelGateway(
            GatewayConfig("http://unused", "srv", allowed_tools=("safe_read",))
        )
        gateway.in_process_forwarder = lambda payload: (
            200,
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {"tools": [{"name": "safe_read"}, {"name": "delete_everything"}]},
                }
            ).encode(),
            "application/json",
        )
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        _, body, _ = gateway.handle(json.dumps(payload).encode(), {})
        self.assertEqual(
            [tool["name"] for tool in json.loads(body)["result"]["tools"]], ["safe_read"]
        )

    def test_gateway_server_refuses_to_start_without_client_auth(self):
        from sentinel.gateway import serve_gateway

        with self.assertRaisesRegex(ValueError, "client authentication"):
            serve_gateway(GatewayConfig("http://unused", "srv"), port=0)

    def test_gateway_server_requires_operator_auth_and_trained_state(self):
        from sentinel.gateway import serve_gateway

        client = self.CLIENT_TOKEN
        with self.assertRaisesRegex(ValueError, "operator credential"):
            serve_gateway(GatewayConfig("http://unused", "srv", client_auth_token=client), port=0)
        config = GatewayConfig(
            "http://unused",
            "srv",
            client_auth_token=client,
            auth_token="test-operator-auth-token-0123456789",
        )
        with self.assertRaisesRegex(ValueError, "trained --state-file"):
            serve_gateway(config, port=0)

    def test_remote_hosts_and_origins_are_explicit_config(self):
        config = GatewayConfig(
            "http://upstream",
            "srv",
            allowed_hosts=("sentinel.example:8443",),
            allowed_origins=("https://console.example",),
        )
        self.assertEqual(config.allowed_hosts, ("sentinel.example:8443",))
        with self.assertRaisesRegex(ValueError, "allowed_hosts"):
            GatewayConfig("http://upstream", "srv", allowed_hosts=("sentinel.example:8443",) * 2)

    def test_component_configuration_reaches_engine(self):
        config = NoveltyConfig(False, False, False, False)
        gateway = SentinelGateway(
            GatewayConfig(
                "http://unused",
                "srv",
                novelty=True,
                allowed_tools=("safe_read",),
                novelty_config=config,
            )
        )
        self.assertEqual(gateway.novelty.config, config)
        self.assertEqual(gateway._preflight_block("safe_read", {}, "Read record"), None)

    def test_invalid_component_configuration_rejected(self):
        with self.assertRaises(ValueError):
            GatewayConfig("http://unused", "srv", novelty_config={})
        with self.assertRaises(ValueError):
            GatewayConfig(
                "http://unused", "srv", novelty_config=NoveltyConfig(intent_provenance="false")
            )

    def test_disabled_capability_trust_restores_server_isolation(self):
        from sentinel.models import Interaction

        gateway = SentinelGateway(
            GatewayConfig(
                "http://unused",
                "srv",
                novelty=True,
                allowed_tools=("safe_read",),
                novelty_config=NoveltyConfig(capability_trust=False),
            )
        )
        gateway.engine.evaluate(Interaction("srv", "safe_read", {}, {}, 10, "Read record"))
        gateway.engine.profiles["srv"].trust = 0.01
        self.assertEqual(
            gateway._preflight_block("safe_read", {}, "Read record"),
            "server trust below isolation threshold",
        )

    def test_cli_component_switches_and_provenance_are_independent(self):
        from sentinel_research.cli import main

        args = [
            "mcp-sentinel",
            "gateway",
            "--upstream",
            "http://unused",
            "--server-id",
            "srv",
            "--novelty",
            "--no-intent-provenance",
            "--no-capability-trust",
            "--no-dual-memory",
            "--no-require-promotion-approval",
            "--require-provenance",
            "--allow-tool",
            "safe_read",
            "--client-auth-token",
            self.CLIENT_TOKEN,
        ]
        with patch("sys.argv", args), patch("sentinel_research.cli.serve_gateway") as serve:
            main()
        config = serve.call_args.args[0]
        self.assertEqual(config.novelty_config, NoveltyConfig(False, False, False, False))
        self.assertTrue(config.require_provenance)
        self.assertEqual(config.allowed_tools, ("safe_read",))
        self.assertEqual(config.client_auth_token, self.CLIENT_TOKEN)

    def test_dispatch_failure_is_audited_without_reviving_claim(self):
        gateway = SentinelGateway(
            GatewayConfig("http://unused", "srv", novelty=True, allowed_tools=("safe_read",))
        )
        gateway._forward = lambda payload, **kwargs: (_ for _ in ()).throw(
            JsonRpcError(-32050, "timeout")
        )
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "safe_read", "arguments": {}},
        }
        with self.assertRaises(JsonRpcError):
            gateway.handle(json.dumps(payload).encode(), {})
        record = asdict(gateway.audit[-1])
        self.assertTrue(record["forwarded"])
        self.assertEqual(record["decision"], "error")
        self.assertEqual(record["reasons"], ["upstream dispatch failed"])

    def test_live_partial_isolation_and_audit_evidence(self):
        mock, state = create_mock_server()
        server, gateway = create_gateway_server(
            GatewayConfig(
                f"http://127.0.0.1:{mock.server_port}",
                "srv",
                novelty=True,
                auth_token="completion-secret-token",
                client_auth_token=self.CLIENT_TOKEN,
                allowed_tools=("safe_read", "export_data"),
            ),
            port=0,
        )
        for item in (mock, server):
            threading.Thread(target=item.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_port}"

        def call(tool):
            request = urllib.request.Request(
                url,
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": tool, "arguments": {"record_id": "1"}},
                    }
                ).encode(),
                headers={
                    "Authorization": f"Bearer {self.CLIENT_TOKEN}",
                    "X-Sentinel-Intent": "Read record 1",
                    "X-Sentinel-Session": "s",
                },
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                return json.loads(response.read())

        try:
            gateway.novelty.capabilities.states[("srv", "export_data")] = CapabilityState(
                trust=0.01
            )
            blocked = call("export_data")
            self.assertEqual(blocked["error"]["code"], -32041)
            self.assertEqual(state.tool_calls.get("export_data", 0), 0)
            record = gateway.audit[-1]
            self.assertFalse(record.forwarded)
            self.assertEqual(record.novelty["capability_trust"], 0.01)
            self.assertEqual(record.novelty["memory_disposition"], "not-evaluated")
            allowed = call("safe_read")
            self.assertIn("result", allowed)
            self.assertEqual(state.tool_calls["safe_read"], 1)
            audit_req = urllib.request.Request(
                url + "/v1/audit", headers={"Authorization": "Bearer completion-secret-token"}
            )
            with urllib.request.urlopen(audit_req, timeout=3) as response:
                rows = json.loads(response.read())
            claim = rows[-1]["novelty"]["claim"]
            self.assertEqual(claim["claim_id"], rows[-1]["novelty"]["claim_id"])
            self.assertEqual(claim["capability"], "safe_read")
            self.assertNotIn("arguments", claim)
            self.assertEqual(rows[-1]["novelty"]["config"], asdict(NoveltyConfig()))
        finally:
            for item in (server, mock):
                item.shutdown()
                item.server_close()


if __name__ == "__main__":
    unittest.main()
