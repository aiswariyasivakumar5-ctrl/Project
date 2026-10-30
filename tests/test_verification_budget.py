import unittest
from sentinel.models import Interaction
from sentinel.verification_budget import VerificationBudget


class VerificationBudgetTests(unittest.TestCase):
    def event(self):
        return Interaction('s', 'calculate', {'a': 1, 'b': 2}, {}, 20, 'Add', capability_digest='v1')

    def fill(self, scheduler):
        for i in range(8):
            scheduler.observe(i, self.event(), i / 8, True)

    def test_equal_budget_and_uncertainty_selection(self):
        for policy in ('first', 'periodic', 'random', 'uncertainty'):
            scheduler = VerificationBudget(policy)
            self.fill(scheduler)
            selected = scheduler.select(lambda e, i: True)
            self.assertEqual(len(selected), 2)
            self.assertEqual(scheduler.queries, 2)
            self.assertEqual(scheduler.select(lambda e, i: True), [])
            if policy == 'uncertainty':
                self.assertEqual([r['source_index'] for r in selected], [7, 6])

    def test_delayed_scope_and_exactly_once(self):
        scheduler = VerificationBudget('first', delay=4)
        self.fill(scheduler)
        scheduler.select(lambda e, i: True)
        learned = []
        self.assertEqual(scheduler.deliver(10, {('s', 'calculate'): 'v1'}, learned.append), [])
        rows = scheduler.deliver(11, {('s', 'calculate'): 'v2'}, learned.append)
        self.assertTrue(all(r['status'] == 'scope_changed' for r in rows))
        self.assertFalse(learned)
        self.assertFalse(scheduler.deliver(12, {('s', 'calculate'): 'v1'}, learned.append))

    def test_expiration_unknown_scope_and_callback_failure(self):
        for scopes, ttl, status in (({}, 16, 'scope_changed'),
                ({('s', 'calculate'): 'v1'}, 1, 'expired')):
            scheduler = VerificationBudget('first', ttl=ttl)
            self.fill(scheduler)
            scheduler.select(lambda e, i: True)
            rows = scheduler.deliver(7, scopes, lambda e: self.fail('must not learn'))
            self.assertTrue(all(r['status'] == status for r in rows))
        scheduler = VerificationBudget('first')
        self.fill(scheduler)
        scheduler.select(lambda e, i: 1 / 0)
        rows = scheduler.deliver(7, {('s', 'calculate'): 'v1'}, lambda e: self.fail('must not learn'))
        self.assertEqual(scheduler.queries, 2)
        self.assertTrue(all(r['status'] == 'unavailable' for r in rows))

    def test_copy_isolation_no_future_selection_and_order(self):
        scheduler = VerificationBudget('first')
        event = self.event()
        scheduler.observe(0, event, .5, True)
        event.arguments['a'] = 999
        self.assertFalse(scheduler.select(lambda e, i: True))
        with self.assertRaises(ValueError):
            scheduler.observe(0, event, .5, True)
        for i in range(1, 8):
            scheduler.observe(i, event, .5, False)
        def verify(e, i):
            self.assertEqual(e.arguments['a'], 1)
            e.arguments['a'] = -1
            return True
        scheduler.select(verify)
        learned = []
        scheduler.deliver(7, {('s', 'calculate'): 'v1'}, learned.append)
        self.assertEqual(learned[0].arguments['a'], 1)
