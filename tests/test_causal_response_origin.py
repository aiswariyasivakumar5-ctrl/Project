import unittest
from sentinel.causal import TemporalCausalGraph
from sentinel.engine import EngineConfig, SentinelEngine
from sentinel.models import Interaction
from sentinel.novelty import NoveltyConfig, NoveltySentinelEngine


class TestCausalResponseOrigin(unittest.TestCase):
    def test_default_mode_flags_generic_record_overlap(self):
        graph = TemporalCausalGraph(causal_requires_response_origin=False)
        first = Interaction(
            "server-a", "safe_read", {"record_id": "record-1005"},
            {"content": [{"type": "text", "text": "record:record-1005"}]},
            20.0, "Read record", session_id="session-1",
        )
        second = Interaction(
            "server-b", "safe_read", {"record_id": "record-1005"},
            {"content": [{"type": "text", "text": "record:record-1005"}]},
            20.0, "Read record", session_id="session-1",
        )
        graph.observe(first)
        evidence = graph.observe(second)
        self.assertGreaterEqual(evidence.risk, 0.60)
        self.assertTrue(any("cross-server data flow from server-a" in r for r in evidence.reasons))

    def test_response_origin_filters_generic_record_overlap(self):
        graph = TemporalCausalGraph(causal_requires_response_origin=True)
        first = Interaction(
            "server-a", "safe_read", {"record_id": "record-1005"},
            {"content": [{"type": "text", "text": "record:record-1005"}]},
            20.0, "Read record", session_id="session-1",
        )
        second = Interaction(
            "server-b", "safe_read", {"record_id": "record-1005"},
            {"content": [{"type": "text", "text": "record:record-1005"}]},
            20.0, "Read record", session_id="session-1",
        )
        graph.observe(first)
        evidence = graph.observe(second)
        self.assertEqual(evidence.risk, 0.0)
        self.assertEqual(len(evidence.reasons), 0)

    def test_response_origin_retains_genuine_cross_server_canary(self):
        graph = TemporalCausalGraph(causal_requires_response_origin=True)
        first = Interaction(
            "server-a", "safe_read", {"record_id": "canary-token-88421"},
            {"content": [{"type": "text", "text": "record:canary-token-88421"}]},
            20.0, "Read record", session_id="session-1",
        )
        second = Interaction(
            "server-b", "export_data", {"payload": "canary-token-88421"},
            {"status": "exported"},
            20.0, "Export record", session_id="session-1",
        )
        graph.observe(first)
        evidence = graph.observe(second)
        self.assertEqual(evidence.risk, 1.0)
        self.assertTrue(any("cross-server data flow from server-a" in r for r in evidence.reasons))

    def test_engine_config_wires_flag_to_graph(self):
        cfg = EngineConfig(causal_requires_response_origin=True)
        engine = SentinelEngine(config=cfg)
        self.assertTrue(engine.causal_graph.causal_requires_response_origin)

    def test_novelty_config_wires_flag(self):
        ncfg = NoveltyConfig(causal_requires_response_origin=True)
        novelty = NoveltySentinelEngine(config=ncfg)
        self.assertTrue(novelty.base.causal_graph.causal_requires_response_origin)


if __name__ == "__main__":
    unittest.main()
