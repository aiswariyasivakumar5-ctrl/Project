from dataclasses import replace
import unittest

from sentinel.models import Interaction
from sentinel.novelty import NoveltyConfig
from sentinel_research.verified_learning import VerifiedLearningEngine, verify_calculation


class VerifiedLearningTests(unittest.TestCase):
    def event(self, index=0, text='3.0'):
        return Interaction('srv', 'calculate', {'a': 1.0, 'b': 2.0},
            {'content': [{'type': 'text', 'text': text}]}, 20, 'Calculate a plus b', session_id=str(index))

    def engine(self, verifier=verify_calculation):
        return VerifiedLearningEngine(config=NoveltyConfig(require_promotion_approval=False), verifier=verifier)

    def test_local_reference_rejects_wrong_and_unsupported_results(self):
        self.assertTrue(verify_calculation(self.event()))
        for text in ('3.1', 'NaN', 'inf', 'x' * 129):
            self.assertFalse(verify_calculation(self.event(text=text)))
        self.assertIsNone(verify_calculation(replace(self.event(), tool_name='unknown')))
        self.assertFalse(verify_calculation(replace(self.event(), arguments={'a': True, 'b': 2})))

    def test_post_promotion_wrong_answer_never_learns(self):
        engine = self.engine()
        for i in range(3):
            verdict = engine.evaluate(self.event(i), attested=True, independent_session=str(i))
        self.assertEqual(verdict.memory_disposition, 'promoted')
        before = engine.base.profiles['srv'].trusted_count
        bad = engine.evaluate(self.event(3, '3.1'), attested=True, independent_session='3')
        self.assertEqual(bad.memory_disposition, 'evidence-withheld')
        self.assertEqual(engine.base.profiles['srv'].trusted_count, before)
        engine.evaluate(self.event(4), attested=True, independent_session='4')
        self.assertEqual(engine.base.profiles['srv'].trusted_count, before + 1)

    def test_missing_exception_and_truthy_nonboolean_fail_closed(self):
        def broken(event):
            raise RuntimeError('unavailable')
        for verifier in (None, broken, lambda e: 1, lambda e: 'yes'):
            engine = self.engine(verifier)
            result = engine.evaluate(self.event(), trusted_enrollment=True)
            self.assertEqual(result.memory_disposition, 'evidence-withheld')
            self.assertEqual(engine.base.profiles['srv'].trusted_count, 0)

    def test_queued_events_rechecked_and_original_not_mutated(self):
        revoked = set()
        def verifier(event):
            identity = event.session_id
            event.arguments['a'] = 999
            return identity not in revoked
        engine = self.engine(verifier)
        event = self.event()
        engine.evaluate(event, attested=True, independent_session='0')
        self.assertEqual(event.arguments['a'], 1.0)
        revoked.add('0')
        result = engine.evaluate(self.event(1), attested=True, independent_session='1')
        self.assertEqual(result.memory_disposition, 'evidence-withheld')
        self.assertEqual(engine.base.profiles['srv'].trusted_count, 0)

    def test_frozen_call_never_invokes_verifier(self):
        def forbidden(event):
            self.fail('frozen evaluation invoked verifier')
        result = self.engine(forbidden).evaluate(self.event(), learn=False)
        self.assertEqual(result.memory_disposition, 'frozen')
