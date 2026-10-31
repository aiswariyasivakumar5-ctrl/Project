import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from sentinel.engine import SentinelEngine
from sentinel_research.experiment import ExperimentConfig
from sentinel.gateway import GatewayConfig, SentinelGateway
from sentinel.models import Interaction
from sentinel.novelty import CapabilityState, NoveltyConfig, NoveltySentinelEngine
from sentinel_research.novelty_experiment import (NoveltyLiveExperiment, NoveltyStudyConfig,
                                         VARIANTS, run_novelty_study, summarize)
from sentinel_research.novelty_scenarios import build_novelty_scenarios
from sentinel_research.workload import normal_workload


class NoveltyScenarioTests(unittest.TestCase):
    def test_seeded_catalog_and_identity_threat_models(self):
        first = build_novelty_scenarios(42, 6)
        self.assertEqual(first, build_novelty_scenarios(42, 6))
        self.assertNotEqual(first, build_novelty_scenarios(123, 6))
        self.assertEqual(len(first), 8)
        spoofed = first['distributed_poisoning'].scenario.cases
        compromised = first['multi_actor_poisoning'].scenario.cases
        self.assertEqual(len({x.interaction.session_id for x in spoofed}), 6)
        self.assertEqual(len({x.independent_identity for x in spoofed}), 1)
        self.assertEqual(len({x.independent_identity for x in compromised}), 6)
        self.assertTrue(all(x.malicious for x in compromised))

    def test_rejected_candidate_cannot_later_promote(self):
        engine = NoveltySentinelEngine()
        event = Interaction('srv', 'safe_read', {'record_id': '1'}, {}, 10, 'Read record 1')
        engine.evaluate(event, attested=True, independent_session='one')
        engine.evaluate(replace(event, success=False), independent_session='two')
        for identity in ('three', 'four', 'five'):
            verdict = engine.evaluate(event, attested=True, independent_session=identity)
            self.assertEqual(verdict.memory_disposition, 'rejected')
        self.assertEqual(engine.base.profiles['srv'].trusted_count, 0)

    def test_capability_ablation_restores_server_preflight(self):
        engine = SentinelEngine()
        event = Interaction('srv', 'safe_read', {}, {}, 10, 'read')
        engine.evaluate(event)
        engine.profiles['srv'].trust = .01
        gateway = SentinelGateway(GatewayConfig('http://unused', 'srv', novelty=True,
                                                allowed_tools=('safe_read',)), engine)
        self.assertIsNone(gateway._preflight_block('safe_read', {}, 'read'))
        gateway.novelty.config = NoveltyConfig(capability_trust=False)
        self.assertEqual(gateway._preflight_block('safe_read', {}, 'read'),
                         'server trust below isolation threshold')


class NoveltyStudyTests(unittest.TestCase):
    def test_checkpoint_restores_full_shared_graph_and_candidate_memory(self):
        with NoveltyLiveExperiment(ExperimentConfig(training_events=20), 'full') as live:
            live.run_phase(normal_workload(20, 42, 'train'), True, 1000, True)
            checkpoint = live.checkpoint()
            before = live.learning_state()
            gateway = next(iter(live.gateways.values()))
            gateway.novelty.capabilities.states[('extra', 'tool')] = CapabilityState(.01)
            live.engine.profiles.clear()
            live.restore(checkpoint)
            self.assertEqual(before, live.learning_state())
            for gateway in live.gateways.values():
                self.assertIs(gateway.engine, live.engine)
                self.assertIs(gateway.novelty.base, live.engine)
                self.assertNotIn(('extra', 'tool'), gateway.novelty.capabilities.states)
            live.run_phase(normal_workload(4, 43, 'validation'), False, 2000)
            self.assertEqual(before, live.learning_state())

    def test_live_matrix_has_frozen_and_independent_adaptive_phases(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'study'
            config = NoveltyStudyConfig(seeds=(42,), variants=tuple(VARIANTS),
                scenarios=('distributed_poisoning', 'legitimate_upgrade', 'schema_stable_response'),
                training_events=20, validation_events=4, test_events=3, output=str(root))
            summary = run_novelty_study(config)
            self.assertEqual(len(summary['aggregate']), 5 * len(VARIANTS))
            protocol = json.loads((root / 'protocol.json').read_text())
            self.assertFalse(protocol['validation_used_for_tuning'])
            self.assertTrue((root / 'REPORT.md').exists())
            execution = json.loads((root / 'execution.json').read_text())
            self.assertEqual(execution['status'], 'completed')
            self.assertEqual(execution['completed_phase_records'], 5 * len(VARIANTS))
            for path in root.glob('*/*/seed-*.json'):
                row = json.loads(path.read_text())
                if row['phase'] == 'test':
                    self.assertEqual(row['learning_before'], row['learning_after'])
                if row['phase'] == 'adaptive':
                    frozen = json.loads(path.with_name('seed-42-test.json').read_text())
                    self.assertEqual(frozen['learning_before'], row['learning_before'])
                if row['variant'] != 'baseline':
                    self.assertEqual(row['novelty_components'], asdict(VARIANTS[row['variant']]))
            snapshot = (root / 'summary.json').read_bytes()
            execution_snapshot = (root / 'execution.json').read_bytes()
            with self.assertRaises(FileExistsError):
                run_novelty_study(config)
            self.assertEqual((root / 'summary.json').read_bytes(), snapshot)
            self.assertEqual((root / 'execution.json').read_bytes(), execution_snapshot)

    def test_failed_request_is_recorded_without_retry_or_summary(self):
        def fail_phase(live, *args, **kwargs):
            live._rpc('fixture-server', 'tools/call', {}, 1007, 'private intent')

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'failure'
            config = NoveltyStudyConfig(variants=('baseline',), training_events=20,
                                       validation_events=4, test_events=3, output=str(root))
            stdout = io.StringIO()
            with redirect_stdout(stdout), \
                 patch.object(NoveltyLiveExperiment, '__enter__', lambda live: live), \
                 patch.object(NoveltyLiveExperiment, '__exit__', return_value=None), \
                 patch.object(NoveltyLiveExperiment, 'run_phase', fail_phase), \
                 patch('sentinel_research.experiment.LiveExperiment._rpc', side_effect=TimeoutError('fixture timeout')) as rpc:
                with self.assertRaisesRegex(TimeoutError, 'fixture timeout'):
                    run_novelty_study(config)
            self.assertEqual(rpc.call_count, 1)
            self.assertEqual(stdout.getvalue(), '')
            record = json.loads((root / 'execution.json').read_text())
            self.assertEqual(record['status'], 'failed')
            self.assertEqual(record['phase'], 'train')
            self.assertEqual(record['seed'], 42)
            self.assertEqual(record['variant'], 'baseline')
            self.assertEqual(record['last_request']['request_id'], 1007)
            self.assertEqual(record['error_type'], 'TimeoutError')
            self.assertEqual(record['completed_phase_records'], 0)
            self.assertNotIn('private intent', (root / 'execution.json').read_text())
            self.assertFalse((root / 'summary.json').exists())
            self.assertTrue((root / 'protocol.json').exists())

    def test_existing_output_is_never_given_a_failure_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(FileExistsError):
                run_novelty_study(NoveltyStudyConfig(output=str(root)))
            self.assertEqual(list(root.iterdir()), [])

    def test_bad_configs_fail_before_creating_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'bad'
            config = NoveltyStudyConfig(variants=('missing',), output=str(root))
            with self.assertRaises(ValueError):
                run_novelty_study(config)
            self.assertFalse(root.exists())

    def test_repeated_live_runs_have_identical_decisions_and_workloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            snapshots = []
            for index in range(2):
                root = Path(temporary) / str(index)
                run_novelty_study(NoveltyStudyConfig(variants=('full',),
                    scenarios=('distributed_poisoning', 'schema_stable_response'),
                    training_events=20, validation_events=4, test_events=3, output=str(root)))
                snapshots.append([
                    (row['workload_sha256'], [(event['risk'], event['decision'], event['model_updates'])
                                              for event in row['decisions']])
                    for path in sorted(root.glob('*/*/seed-*.json'))
                    for row in [json.loads(path.read_text())]])
            self.assertEqual(snapshots[0], snapshots[1])

    def test_paired_statistics_align_seed_ids(self):
        rows = [{'variant': variant, 'scenario': 'sample', 'phase': 'test', 'seed': seed,
                 'metrics': {'f1': value, 'recall': value, 'false_positive_rate': 0},
                 'learning_before': {'model_updates': 0}, 'learning_after': {'model_updates': 0}}
                for variant, seed, value in [('full', 42, .9), ('full', 123, .1),
                                              ('baseline', 123, .1), ('baseline', 42, .9)]]
        report = summarize(rows)['exploratory_paired_comparisons'][0]
        self.assertEqual(report['paired_seeds'], [42, 123])
        self.assertEqual(report['test']['mean_difference'], 0)


if __name__ == '__main__':
    unittest.main()
