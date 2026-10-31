# SPDX-License-Identifier: MIT OR Apache-2.0
from copy import deepcopy
import json
import math
from pathlib import Path
import unittest
from fcst_tools.radiation import assess, assess_report, wilson
from fcst_tools.privacy import Scanner

ROOT = Path(__file__).resolve().parents[1]


class RadiationTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT/'ci/radiation-acceptance-v1.json').read_bytes())
        self.statistical = json.loads((ROOT/'ci/numerical-criteria-v1.json').read_bytes())['statistical_policy']
        self.candidate = 'a'*40

    def runs(self):
        result = []
        for g, quantities in self.policy['quantities'].items():
            ids = sorted({x for q in quantities for x in q.split('->')})
            for seed in self.statistical['seeds']:
                for n in self.statistical['samples_per_replicate']:
                    rows = []
                    for a in ids:
                        counts = []
                        for q, p in quantities.items():
                            source, b = q.split('->')
                            if a == source:
                                hits = round(n*p + (.5*math.sqrt(n) if 0 < p < .5 else -.5*math.sqrt(n) if .5 <= p < 1 else 0))
                                if hits: counts.append(dict(target=b, hits=hits))
                        remainder = n-sum(c['hits'] for c in counts)
                        if g == 'cube':
                            target = next(b for b in ids if b != a and b not in [c['target'] for c in counts])
                            counts.append(dict(target=target, hits=remainder)); remainder = 0
                        rows.append(dict(id=a, area=1 if a != 'outer/front' else 4, escaped=remainder, blocked=0, counts=counts))
                    result.append(dict(candidate=self.candidate, geometry=g, seed=seed, samples=n, facets=12, storage_bytes=4000, build_seconds=.1, trace_seconds=.2, rows=rows))
        return result

    def test_frozen_ensemble_passes_and_retains_every_interval(self):
        report = assess(self.runs(), self.policy, self.statistical, self.candidate)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['family_size'], 576)
        self.assertEqual(len(report['observations']), 576)
        self.assertGreater(report['normal_quantile'], 3.9)

    def test_missing_duplicate_seed_shopping_and_candidate_substitution_reject(self):
        runs = self.runs()
        for kind in ('missing', 'duplicate', 'seed', 'samples', 'candidate', 'nan', 'counts', 'target', 'escaped'):
            values = deepcopy(runs)
            if kind == 'missing': values.pop()
            if kind == 'duplicate': values[-1] = deepcopy(values[0])
            if kind == 'seed': values[0]['seed'] = 1
            if kind == 'samples': values[0]['samples'] += 1
            if kind == 'candidate': values[0]['candidate'] = 'b'*40
            if kind == 'nan': values[0]['rows'][0]['area'] = float('nan')
            if kind == 'counts': values[0]['rows'][0]['counts'].append(deepcopy(values[0]['rows'][0]['counts'][0]))
            if kind == 'target': values[0]['rows'][0]['counts'][0]['target'] = 'unknown'
            if kind == 'escaped': values[0]['rows'][0]['escaped'] = .5
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                assess(values, self.policy, self.statistical, self.candidate)

    def test_outliers_fail_and_remain_in_evidence(self):
        runs = self.runs()
        row = runs[0]['rows'][0]; row['counts'][0]['hits'] += 1000; row['escaped'] -= 1000
        report = assess(runs, self.policy, self.statistical, self.candidate)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(report['observations']), 576)
        self.assertTrue(report['misses'])

    def test_wilson_boundaries_and_invalid_counts(self):
        self.assertEqual(wilson(0, 100, 2)[1], 0)
        self.assertEqual(wilson(100, 100, 2)[2], 1)
        for hits, n in ((101, 100), (-1, 100), (1, 0), (True, 100), (1.5, 100)):
            with self.assertRaises(ValueError): wilson(hits, n, 2)

    def report(self):
        runs = self.runs()
        cases = self.policy['native_cases'] + ['fixed-ensemble', 'independent-quadrature-and-radiosity', 'worker-input-boundary', 'worker-replay', 'worker-coupled-steady', 'million-facet-scaling']
        curves = []
        for size in self.policy['scaling_subdivisions']:
            for n in self.policy['scaling_samples']:
                for replicate in range(3):
                    curves.append(dict(facets=4*size*size, samples=n, replicate=replicate, seed=self.statistical['seeds'][replicate], storage_bytes=1000, peak_working_set_bytes=2000, build_seconds=.1, trace_seconds=.2, rays_per_second=2*n/.2, maximum_absolute_error=.001, raw_sha256='1'*64))
        return dict(schema_version=1, profile=self.policy['profile'], candidate=self.candidate, input_sha256={}, scope=self.policy['scope'],
                    execution_mode='fcst_native', status='passed', vendor_compatibility_qualified=False, q1_qualified=False, native_sha256='1'*64, worker_sha256='2'*64,
                    cases=[dict(id=c, status='passed') for c in cases], ensemble=assess(runs, self.policy, self.statistical, self.candidate), scaling=curves,
                    runs=[dict(geometry=r['geometry'], seed=r['seed'], samples=r['samples'], raw_sha256='3'*64) for r in runs],
                    independent_reference=dict(plate_quadrature=.19982489569838746, quadrature_error_bound=1e-13, maximum_radiosity_error=1e-10, coupled_steady_temperature_error_K=1e-10), independent_backends=self.policy['independent_backends'])

    def test_handoff_recomputes_intervals_scaling_coverage_and_provenance(self):
        r = self.report()
        self.assertTrue(assess_report(r, self.policy, self.statistical, {}, self.candidate))
        for kind in ('source', 'candidate', 'case', 'interval', 'rms', 'hit', 'scaling', 'scaling-error', 'throughput', 'reference', 'run', 'q1'):
            report = deepcopy(r)
            if kind == 'source': report['input_sha256'] = {'modified': 'f'*64}
            if kind == 'candidate': report['candidate'] = 'b'*40
            if kind == 'case': report['cases'].pop()
            if kind == 'interval': report['ensemble']['observations'][0]['upper'] = 1
            if kind == 'rms': report['ensemble']['rms_error']['4096'] = 0
            if kind == 'hit': report['ensemble']['observations'][0]['hits'] += 1
            if kind == 'scaling': report['scaling'].pop()
            if kind == 'scaling-error': report['scaling'][0]['maximum_absolute_error'] = float('nan')
            if kind == 'throughput': report['scaling'][0]['rays_per_second'] *= 2
            if kind == 'reference': report['independent_reference']['maximum_radiosity_error'] = 1
            if kind == 'run': report['runs'][-1] = deepcopy(report['runs'][0])
            if kind == 'q1': report['q1_qualified'] = True
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                assess_report(report, self.policy, self.statistical, {}, self.candidate)

    def test_sources_fixture_and_publication_wiring(self):
        policy = json.loads((ROOT/'ci/publication-policy.json').read_bytes())
        scanner = Scanner(policy)
        for relative in ('tests/fixtures/radiation/plates.json', 'ci/radiation-acceptance-v1.json'):
            scanner.scan(relative, (ROOT/relative).read_bytes())
        self.assertFalse(scanner.findings)
        driver = (ROOT/'tools/verify.py').read_text()
        workflow = (ROOT/'.github/workflows/ci.yml').read_text()
        self.assertIn('radiation-acceptance', driver)
        self.assertIn('radiation.json', workflow)
        self.assertIn('radiation.json', (ROOT/'tools/check_workflows.py').read_text())
        self.assertEqual(self.statistical['samples_per_replicate'], [4096, 16384, 65536])
        self.assertEqual(len(self.statistical['seeds']), 16)
