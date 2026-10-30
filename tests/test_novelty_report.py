import copy
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

from sentinel.novelty_experiment import VARIANTS
from sentinel.novelty_scenarios import build_novelty_scenarios
from sentinel.novelty_report import analyze, value, provenance_outcomes
from sentinel.novelty_report import generate as generate_report
from sentinel.novelty_figures import generate as generate_figures


class NoveltyReportTests(unittest.TestCase):
    def test_denied_origin_not_counted_as_issued_claim(self):
        counts = provenance_outcomes([
            {'provenance': {'operation': 'issue', 'issued': None, 'issuance_error': 'denied'}},
            {'provenance': {'operation': 'use', 'before': None}},
            {'provenance': {'operation': 'issue', 'issued': {'claim_id': 'valid'}}},
            {'provenance': {'operation': 'use', 'before': {'uses': 0}}}, {}])
        self.assertEqual(counts, dict(issue_attempts=2, issued_claims=1,
            denied_issuance=1, use_attempts=2, uses_without_retained_claim=1))

    def fixture(self):
        config = dict(seeds=[42, 123, 456, 789, 1001], variants=list(VARIANTS),
                      scenarios=list(build_novelty_scenarios()), test_events=3)
        rows = []
        for v in config['variants']:
            for s, scenario in build_novelty_scenarios().items():
                for phase in (('test', 'adaptive') if scenario.adaptive else ('test',)):
                    for seed in config['seeds']:
                        m = dict(tp=1, tn=1, fp=0, fn=0, precision=1., recall=1., f1=1.,
                                 false_positive_rate=0., auroc=1., auprc=1., detection_delay_events=0,
                                 latency_ms={'mean': 1.}, sentinel_evaluation_mean_ms=.5)
                        rows.append(dict(variant=v, scenario=s, phase=phase, seed=seed, metrics=m,
                                         learning_before={'model_updates': 10}, learning_after={'model_updates': 10},
                                         workload_sha256={'train': str(seed), phase: s}))
        return config, rows

    def test_complete_identical_matrix_is_not_significant(self):
        config, rows = self.fixture()
        result = analyze(list(reversed(rows)), config)
        self.assertEqual(len(result['aggregate']), 66)
        self.assertEqual(len(result['primary_comparisons']), 4)
        for comparison in result['primary_comparisons']:
            self.assertEqual(comparison['holm_p'], 1.)
            self.assertFalse(comparison['significant_0_05'])

    def test_missing_and_duplicate_rows_rejected(self):
        config, rows = self.fixture()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            analyze(rows[:-1], config)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            analyze(rows + [rows[0]], config)

    def test_mismatched_workloads_rejected(self):
        config, rows = self.fixture()
        next(r for r in rows if r['variant'] == 'full' and r['scenario'] == 'capability_laundering')['workload_sha256'] = {}
        with self.assertRaisesRegex(ValueError, 'unmatched'):
            analyze(rows, config)

    def test_empty_denominators_are_undefined(self):
        _, rows = self.fixture()
        row = copy.deepcopy(rows[0])
        row['metrics'].update(tp=0, fn=0)
        self.assertIsNone(value(row, 'recall'))
        self.assertIsNone(value(row, 'f1'))
        self.assertIsNone(value(row, 'precision'))
        row['metrics'].update(tn=0)
        self.assertIsNone(value(row, 'false_positive_rate'))

    def test_report_and_svg_export_with_explicit_unit_test_fixtures(self):
        config, rows = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'unit-test-fixture'
            source.mkdir()
            (source / 'protocol.json').write_text(json.dumps({'configuration': config}), encoding='utf-8')
            (source / 'summary.json').write_text('{}', encoding='utf-8')
            for row in rows:
                row['metrics']['roc_curve'] = [{'fpr': 0., 'tpr': 0.}, {'fpr': 1., 'tpr': 1.}]
                row['metrics']['precision_recall_curve'] = [{'recall': 0., 'precision': 1.}, {'recall': 1., 'precision': .5}]
                path = source / row['variant'] / row['scenario'] / f"seed-{row['seed']}-{row['phase']}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(row), encoding='utf-8')
            generate_report(source, root / 'analysis')
            files = generate_figures(source, root / 'analysis/statistics.json', root / 'figures')
            self.assertEqual(len(files), 77)
            for name in files:
                self.assertEqual(ElementTree.parse(root / 'figures' / name).getroot().tag,
                                 '{http://www.w3.org/2000/svg}svg')
            with self.assertRaises(FileExistsError):
                generate_figures(source, root / 'analysis/statistics.json', root / 'figures')


if __name__ == '__main__':
    unittest.main()
