import unittest

from sentinel.features import intent_mismatch, lexical_intent_mismatch
from sentinel.semantic_intent import semantic_intent_mismatch
from sentinel_research.intent_benchmark import evaluate_intent_matcher, ADVERSARIAL_INTENT_DATASET


class IntentBenchmarkTests(unittest.TestCase):
    def test_semantic_intent_matcher_outperforms_lexical_baseline(self):
        m_orig = evaluate_intent_matcher(lexical_intent_mismatch, ADVERSARIAL_INTENT_DATASET, threshold=0.60)
        m_semi = evaluate_intent_matcher(semantic_intent_mismatch, ADVERSARIAL_INTENT_DATASET, threshold=0.60)

        # Semantic matcher should eliminate evasions (100% recall on deceptive intents)
        self.assertEqual(m_semi["recall"], 1.0)
        self.assertEqual(m_semi["evasion_rate"], 0.0)

        # Semantic matcher should have significantly higher F1 than lexical baseline
        self.assertGreater(m_semi["f1"], m_orig["f1"])
        self.assertGreater(m_semi["precision"], m_orig["precision"])

        # False positive rate on benign paraphrases must drop significantly
        self.assertLess(m_semi["false_positive_rate"], m_orig["false_positive_rate"])

    def test_empty_intent_is_penalized(self):
        score = semantic_intent_mismatch("", "simulated_delete", {"record_id": "1001"})
        self.assertGreaterEqual(score, 0.70, "Empty intent must receive strong mismatch penalty")

    def test_action_conflict_is_flagged(self):
        score = semantic_intent_mismatch(
            "view record 1001", "simulated_delete", {"record_id": "1001"}
        )
        self.assertGreaterEqual(score, 0.90, "Read intent for delete tool must be flagged as conflict")


if __name__ == "__main__":
    unittest.main()
