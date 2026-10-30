import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from sentinel.gateway import GatewayConfig, SentinelGateway, build_baseline, create_gateway_server
from sentinel.mock_server import create_mock_server

EXFIL = {"name": "export_data", "arguments": {"scope": "all", "include_tokens": True}}


class ColdStartBaselineTests(unittest.TestCase):
    CLIENT_TOKEN = "test-client-auth-token-0123456789abcdef"
    def setUp(self):
        self.mock, _ = create_mock_server()
        threading.Thread(target=self.mock.serve_forever, daemon=True).start()
        self.upstream = f"http://127.0.0.1:{self.mock.server_address[1]}"
        self.config = GatewayConfig(self.upstream, "crm-server", timeout_seconds=2,
                                    allowed_tools=("safe_read", "calculate", "export_data"),
                                    client_auth_token=self.CLIENT_TOKEN)

    def tearDown(self):
        self.mock.shutdown()
        self.mock.server_close()

    def _decision(self, gateway_url):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": EXFIL}).encode()
        req = urllib.request.Request(gateway_url, body, {"Content-Type": "application/json",
                                     "Authorization": f"Bearer {self.CLIENT_TOKEN}",
                                     "X-Sentinel-Intent": "Read one record", "X-Sentinel-Session": "atk"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.headers.get("X-Sentinel-Decision")

    def _serve(self, state_file=None):
        server, gateway = create_gateway_server(self.config, port=0)
        if state_file:
            gateway.load_state(state_file)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close()))
        return f"http://127.0.0.1:{server.server_address[1]}"

    def test_cold_gateway_does_not_block_exfiltration(self):
        self.assertIn(self._decision(self._serve()), ("allow", "observe"))  # documents the cold-start gap

    def test_baseline_makes_fresh_gateway_hold_exfiltration(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "baseline.json"
            result = build_baseline(self.config, state, rounds=40)
            self.assertGreaterEqual(result["trained_events"], 40)
            self.assertNotEqual(self._decision(self._serve(state)), "allow")

    def test_state_roundtrip_preserves_learned_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "b.json"
            build_baseline(self.config, state, rounds=30)
            fresh = SentinelGateway(self.config)
            fresh.load_state(state)
            original = json.loads(state.read_text())["engine"]["profiles"]["crm-server"]
            restored = fresh.engine.profiles["crm-server"]
            self.assertEqual(restored.scaler.count, original["scaler"]["count"])
            self.assertEqual(restored.autoencoder.w1.tolist(), original["autoencoder"]["w1"])


if __name__ == "__main__":
    unittest.main()
