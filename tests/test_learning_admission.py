from dataclasses import replace
import threading
import unittest

from sentinel.engine import SentinelEngine
from sentinel.learning_admission import LearningAdmission, POLICIES
from sentinel.models import Interaction
from sentinel.verified_learning import verify_calculation


def event():
    return Interaction('srv', 'calculate', {'a': 1, 'b': 2},
        {'content': [{'type': 'text', 'text': '3'}]}, 20, 'Calculate sum',
        capability_digest='calculator-v1')


class Clock:
    def __init__(self):
        self.value = 10.0
    def __call__(self):
        return self.value


class PausingEngine(SentinelEngine):
    entered = None
    resume = None
    def learn_approved(self, event, **kwargs):
        super().learn_approved(event, **kwargs)
        type(self).entered.set()
        if not type(self).resume.wait(5):
            raise RuntimeError('test coordination timeout')


class BrokenEngine(SentinelEngine):
    def learn_approved(self, event, **kwargs):
        super().learn_approved(event, **kwargs)
        raise RuntimeError('partial staged mutation')


class LearningAdmissionTests(unittest.TestCase):
    def make(self, **kwargs):
        self.clock = Clock()
        gate = LearningAdmission(clock=self.clock, verifier=verify_calculation, **kwargs)
        gate.set_permission(('srv', 'calculate'), True)
        gate.set_capability(('srv', 'calculate'), 'calculator-v1')
        return gate

    def ticket(self, gate, identity='event-1', **kwargs):
        return gate.approve(identity, event(), evidence_ref='local-reference', **kwargs)

    def test_commit_once_and_copied_snapshot(self):
        gate = self.make()
        ticket = self.ticket(gate)
        self.assertEqual(gate.commit(ticket, event()), 'committed')
        self.assertEqual(gate.commit(ticket, event()), 'replay')
        model, version, consumed, decisions = gate.snapshot()
        self.assertEqual(model.profiles['srv'].trusted_count, 1)
        self.assertEqual((version, consumed, decisions[ticket]), (1, {'event-1'}, 'committed'))
        model.profiles.clear()
        self.assertIn('srv', gate.snapshot()[0].profiles)

    def test_relevant_revocation_and_regrant(self):
        for regrant in (False, True):
            gate = self.make()
            ticket = self.ticket(gate)
            gate.set_permission(('srv', 'calculate'), False)
            if regrant:
                gate.set_permission(('srv', 'calculate'), True)
            self.assertEqual(gate.commit(ticket, event()), 'permission_changed')
            self.assertEqual(gate.snapshot()[1], 0)

    def test_capability_aba(self):
        gate = self.make()
        ticket = self.ticket(gate)
        gate.set_capability(('srv', 'calculate'), 'calculator-v2')
        gate.set_capability(('srv', 'calculate'), 'calculator-v1')
        self.assertEqual(gate.commit(ticket, event()), 'capability_changed')

    def test_unrelated_changes_retained(self):
        gate = self.make()
        ticket = self.ticket(gate)
        gate.set_permission(('srv', 'other'), False)
        gate.set_capability(('srv', 'other'), 'other-v2')
        self.assertEqual(gate.commit(ticket, event()), 'committed')

    def test_expiry_exact_boundary(self):
        gate = self.make()
        ticket = self.ticket(gate, ttl=1)
        self.clock.value += 1
        self.assertEqual(gate.commit(ticket, event()), 'expired')

    def test_event_binding_and_duplicate_update(self):
        gate = self.make()
        ticket = self.ticket(gate)
        with self.assertRaises(ValueError):
            self.ticket(gate)
        changed = replace(event(), session_id='other')
        self.assertEqual(gate.commit(ticket, changed), 'binding_mismatch')
        self.assertEqual(gate.commit(ticket, event()), 'replay')
        self.assertEqual(gate.commit('unknown', event()), 'unknown')

    def test_clock_rollback_is_latched(self):
        gate = self.make()
        ticket = self.ticket(gate)
        self.clock.value -= 1
        self.assertEqual(gate.commit(ticket, event()), 'clock_invalid')
        self.clock.value += 2
        with self.assertRaises(ValueError):
            self.ticket(gate, 'next')

    def test_verifier_failure_and_mutation(self):
        for verifier in (None, lambda e: 1, lambda e: False):
            gate = LearningAdmission(verifier=verifier)
            gate.set_permission(('srv', 'calculate'), True)
            gate.set_capability(('srv', 'calculate'), 'calculator-v1')
            with self.assertRaises(ValueError):
                self.ticket(gate)
        gate = self.make()
        def mutate(e):
            e.arguments['a'] = 100
            return True
        gate._verifier = mutate
        self.assertEqual(gate.commit(self.ticket(gate), event()), 'committed')

    def test_verification_race(self):
        gate = self.make()
        def revoke(e):
            gate.set_permission(('srv', 'calculate'), False)
            return True
        gate._verifier = revoke
        with self.assertRaises(ValueError):
            self.ticket(gate)

    def test_partial_preparation_not_published(self):
        gate = self.make(engine=BrokenEngine())
        ticket = self.ticket(gate)
        self.assertEqual(gate.commit(ticket, event()), 'preparation_failed')
        model, version, consumed, decisions = gate.snapshot()
        self.assertEqual((model.profiles, version, consumed, decisions), ({}, 0, set(), {}))

    def paused(self):
        PausingEngine.entered, PausingEngine.resume = threading.Event(), threading.Event()
        gate = self.make(engine=PausingEngine())
        ticket = self.ticket(gate)
        outcomes = []
        worker = threading.Thread(target=lambda: outcomes.append(gate.commit(ticket, event())))
        worker.start()
        self.addCleanup(lambda: (PausingEngine.resume.set(), worker.join(6)))
        self.assertTrue(PausingEngine.entered.wait(5))
        return gate, ticket, worker, outcomes

    def test_revocation_during_preparation(self):
        gate, ticket, worker, outcomes = self.paused()
        gate.set_permission(('srv', 'calculate'), False)
        PausingEngine.resume.set()
        worker.join(6)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcomes, ['permission_changed'])
        self.assertEqual(gate.snapshot()[1], 0)

    def test_expiry_during_preparation(self):
        gate, ticket, worker, outcomes = self.paused()
        self.clock.value += 60
        PausingEngine.resume.set()
        worker.join(6)
        self.assertEqual(outcomes, ['expired'])
        self.assertEqual(gate.snapshot()[1], 0)

    def test_two_workers_same_ticket(self):
        gate, ticket, worker, outcomes = self.paused()
        second = threading.Thread(target=lambda: outcomes.append(gate.commit(ticket, event())))
        second.start()
        PausingEngine.resume.set()
        worker.join(6)
        second.join(6)
        self.assertFalse(second.is_alive())
        self.assertCountEqual(outcomes, ['committed', 'replay'])
        self.assertEqual(gate.snapshot()[1], 1)

    def test_commit_before_revocation_not_undone(self):
        gate = self.make()
        self.assertEqual(gate.commit(self.ticket(gate), event()), 'committed')
        gate.set_permission(('srv', 'calculate'), False)
        self.assertEqual(gate.snapshot()[1], 1)

    def test_baseline_controls(self):
        for policy in POLICIES:
            gate = self.make(policy=policy)
            ticket = self.ticket(gate)
            gate.set_permission(('srv', 'calculate'), False)
            expected = 'permission_changed' if policy in ('combined', 'transactional') else 'committed'
            self.assertEqual(gate.commit(ticket, event()), expected)

    def test_capacity_and_bad_fields(self):
        gate = self.make(capacity=1)
        self.ticket(gate)
        with self.assertRaises(ValueError):
            self.ticket(gate, 'second')
        for ttl in (0, -1, float('nan'), float('inf'), True):
            with self.assertRaises(ValueError):
                self.ticket(gate, 'invalid', ttl=ttl)

    def test_two_updates_never_overwrite_each_other(self):
        gate, ticket, worker, outcomes = self.paused()
        second_ticket = self.ticket(gate, 'second')
        # Commit the second update while the first has already copied version 0.
        PausingEngine.resume.set()
        second_result = gate.commit(second_ticket, event())
        worker.join(6)
        if second_result == 'retry_model_conflict':
            self.assertEqual(gate.commit(second_ticket, event()), 'committed')
        elif outcomes == ['retry_model_conflict']:
            self.assertEqual(gate.commit(ticket, event()), 'committed')
        self.assertEqual(gate.snapshot()[1], 2)
        self.assertEqual(gate.snapshot()[0].profiles['srv'].trusted_count, 2)

    def test_matched_demo_and_strong_baseline(self):
        from sentinel.learning_admission_demo import run_matrix
        rows = run_matrix()
        self.assertEqual(len(rows), 40)
        for policy in ('combined', 'transactional'):
            selected = [r for r in rows if r['policy'] == policy]
            self.assertEqual(sum(r['unsafe_admission'] for r in selected), 0)
            self.assertEqual(sum(r['eligible_withheld'] for r in selected), 0)
        for scenario in {r['scenario'] for r in rows}:
            pair = [r['decision'] for r in rows if r['scenario'] == scenario and
                    r['policy'] in ('combined', 'transactional')]
            self.assertEqual(pair[0], pair[1])


if __name__ == '__main__':
    unittest.main()
