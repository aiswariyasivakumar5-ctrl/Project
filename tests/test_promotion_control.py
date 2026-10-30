import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sentinel.novelty import DualMemoryAdapter
from sentinel.experiment import ExperimentConfig
from sentinel.learning_attribution import LearningAttribution
from sentinel.novelty_experiment import NoveltyLiveExperiment
from sentinel.promotion_control import fixtures, run_control
from sentinel.promotion_factorial import run_factorial


class PromotionControlTests(unittest.TestCase):
    def test_live_trained_model_promotes_reviewed_shape_and_replays_sources(self):
        train, cases = fixtures(varied_enrollment=True)
        with NoveltyLiveExperiment(ExperimentConfig(training_events=100), 'approval_required') as live:
            live.run_phase(train, True, 1000, True)
            gateway = live.gateways['local-test-mcp']
            reviewed = replace(cases[0].interaction, capability_digest=gateway.capability_digest)
            fp = DualMemoryAdapter.fingerprint(reviewed)
            self.assertNotIn(fp, gateway.novelty.memory.trusted.get((reviewed.server_id, reviewed.tool_name), ()))
            gateway.novelty.approve_promotion(reviewed, reviewer='test operator', evidence_ref='numeric-shape-control')
            profile = live.engine.profiles[reviewed.server_id]
            before_count = profile.trusted_count
            before_weights = profile.autoencoder.w1.copy()
            with LearningAttribution(live.engine, cases) as attribution:
                for index, case in enumerate(cases):
                    attribution.step = index
                    _, detail = live.execute(case, 10000 + index, True)
                    self.assertTrue(detail['attestation_verified'])
                    self.assertEqual(detail['model_updates'], (0, 0, 3, 1, 1, 1)[index])
                    if index == 2:
                        self.assertEqual(detail['novelty']['memory_disposition'], 'promoted')
                        self.assertEqual([r['source_event_index'] for r in attribution.records], [0, 1, 2])
                        self.assertTrue(all(not r['sequence_updated'] for r in attribution.records))
                self.assertEqual([r['source_event_index'] for r in attribution.records], list(range(6)))
            self.assertEqual(profile.trusted_count - before_count, 6)
            self.assertFalse((before_weights == profile.autoencoder.w1).all())
            self.assertIn(fp, gateway.novelty.memory.trusted[(reviewed.server_id, reviewed.tool_name)])
            self.assertIsNone(gateway.novelty.approvals.get(gateway.novelty.approval_key(reviewed)))

    def test_variety_changes_training_only_and_keeps_new_shape_unseen(self):
        for explicit in (False, True):
            constant, adaptive = fixtures(explicit)
            varied, matched = fixtures(explicit, True)
            self.assertEqual(adaptive, matched)
            self.assertEqual(len(varied), len(constant))
            self.assertEqual({c.interaction.arguments['a'] for c in varied}, {1, 10, 100, 1000})
            self.assertTrue(all(type(c.interaction.arguments['a']) is int for c in varied))
            fp = DualMemoryAdapter.fingerprint(adaptive[0].interaction)
            self.assertTrue(all(DualMemoryAdapter.fingerprint(c.interaction) != fp for c in varied))

    def test_factorial_runs_every_fixed_condition(self):
        with tempfile.TemporaryDirectory() as root:
            with patch('sentinel.promotion_factorial.run_control', return_value=[{'policy': 'fixture'}]) as run:
                rows = run_factorial(Path(root) / 'run')
            self.assertEqual([(c.args[2], c.args[1]) for c in run.call_args_list],
                             [(False, False), (False, True), (True, False), (True, True)])
            self.assertEqual(len(rows), 4)
            state = json.loads((Path(root) / 'run/execution.json').read_text())
            self.assertEqual(state['completed_cells'], 4)
            self.assertEqual(state['status'], 'complete')

    def test_shape_changes_but_numeric_meaning_and_intent_do_not(self):
        for explicit in (False, True):
            train, adaptive = fixtures(explicit)
            self.assertEqual((train, adaptive), fixtures(explicit))
            self.assertEqual(len(train), 100)
            self.assertEqual(len(adaptive), 6)
            old, new = train[0].interaction, adaptive[0].interaction
            self.assertEqual(old.arguments, new.arguments)
            self.assertNotEqual(DualMemoryAdapter.fingerprint(old), DualMemoryAdapter.fingerprint(new))
            self.assertEqual(old.user_intent, new.user_intent)
            self.assertFalse(any(c.malicious for c in train + adaptive))
            self.assertEqual(len({c.independent_identity for c in adaptive}), 6)
            self.assertFalse({c.interaction.session_id for c in train} &
                             {c.interaction.session_id for c in adaptive})

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / 'keep.txt'
            marker.write_text('original', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                run_control(root)
            self.assertEqual(marker.read_text(encoding='utf-8'), 'original')

    def test_transport_failure_is_retained_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'run'
            with patch('sentinel.promotion_control.NoveltyLiveExperiment.__enter__',
                       side_effect=TimeoutError('fixture transport failure')):
                with self.assertRaises(TimeoutError):
                    run_control(output)
            execution = json.loads((output / 'execution.json').read_text())
            self.assertEqual(execution['status'], 'failed')
            self.assertEqual(execution['completed'], 0)
            self.assertFalse((output / 'summary.json').exists())
