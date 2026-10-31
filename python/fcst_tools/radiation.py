# SPDX-License-Identifier: MIT OR Apache-2.0
"""Frozen, complete-ensemble radiation assessment; never choose or rerun seeds."""
import math
import re
from statistics import NormalDist


def require(ok):
    if not ok:
        raise ValueError('radiation_acceptance_failed')


def wilson(hits, samples, z):
    require(type(hits) is int and type(samples) is int and 0 <= hits <= samples and samples > 0)
    require(math.isfinite(z) and z > 0)
    p = hits / samples
    d = 1 + z*z/samples
    center = (p + z*z/(2*samples))/d
    half = z*math.sqrt(p*(1-p)/samples + z*z/(4*samples*samples))/d
    return p, max(0, center-half), min(1, center+half)


def validate_run(run, geometry, seed, samples, candidate):
    require(run['candidate'] == candidate and run['geometry'] == geometry and run['seed'] == seed and run['samples'] == samples)
    require(type(samples) is int and samples > 0 and type(run['facets']) is int and run['facets'] > 0)
    ids = [r['id'] for r in run['rows']]
    require(len(ids) == len(set(ids)) and len(ids) > 0)
    for row in run['rows']:
        require(math.isfinite(row['area']) and row['area'] > 0)
        targets = [c['target'] for c in row['counts']]
        require(len(targets) == len(set(targets)) and set(targets) <= set(ids))
        counts = [row['escaped'], row['blocked']] + [c['hits'] for c in row['counts']]
        require(all(type(c) is int and 0 <= c <= samples for c in counts) and sum(counts) == samples)
    for field in ('storage_bytes', 'build_seconds', 'trace_seconds'):
        require(math.isfinite(run[field]) and run[field] > 0)
    return run


def assess(runs, policy, statistical, candidate):
    expected = {(g, seed, n) for g in policy['quantities'] for seed in statistical['seeds'] for n in statistical['samples_per_replicate']}
    require(len(runs) == len(expected) and statistical['replicates'] == len(statistical['seeds']))
    require(len(set(statistical['seeds'])) == len(statistical['seeds']))
    family = sum(len(q) for q in policy['quantities'].values()) * len(statistical['seeds']) * len(statistical['samples_per_replicate'])
    z = NormalDist().inv_cdf(1 - (1-statistical['coverage'])/(2*family))
    errors = {n: [] for n in statistical['samples_per_replicate']}
    observations, misses = [], []
    for run in runs:
        key = run['geometry'], run['seed'], run['samples']
        require(key in expected)
        expected.remove(key)
        g, seed, n = key
        validate_run(run, g, seed, n, candidate)
        rows = {r['id']: r for r in run['rows']}
        require(set(rows) == {v for q in policy['quantities'][g] for v in q.split('->')})
        if g in ('spheres', 'cube'):
            require(all(r['escaped'] == r['blocked'] == 0 for r in rows.values()))
        for quantity, reference in policy['quantities'][g].items():
            a, b = quantity.split('->')
            hits = next((c['hits'] for c in rows[a]['counts'] if c['target'] == b), 0)
            p, lo, hi = wilson(hits, n, z)
            error = abs(p-reference)
            errors[n].append(error**2)
            observation = dict(geometry=g, seed=seed, samples=n, quantity=quantity, hits=hits, estimate=p, lower=lo, upper=hi, error=error)
            observations.append(observation)
            if not lo-1e-15 <= reference <= hi+1e-15:
                misses.append(observation)
    require(not expected)
    rms = {n: math.sqrt(sum(e)/len(e)) for n, e in errors.items()}
    ns = statistical['samples_per_replicate']
    converged = all(rms[b] < rms[a] for a, b in zip(ns, ns[1:]))
    practical = all(o['error'] <= statistical['practical_absolute_error'] for o in observations if o['samples'] == ns[-1])
    return dict(status='passed' if not misses and converged and practical else 'failed', family_size=family, normal_quantile=z,
                rms_error={str(n): rms[n] for n in ns}, converged=converged, practical_error_passed=practical,
                misses=misses, observations=observations)


def assess_report(report, policy, statistical, hashes, candidate):
    require(report['schema_version'] == 1 and report['profile'] == policy['profile'] and report['candidate'] == candidate)
    require(report['input_sha256'] == hashes and report['scope'] == policy['scope'] and report['execution_mode'] == 'fcst_native')
    require(report['status'] == 'passed' and report['vendor_compatibility_qualified'] is False and report['q1_qualified'] is False)
    require(report['independent_backends'] == policy['independent_backends'])
    for field in ('native_sha256', 'worker_sha256'):
        require(isinstance(report[field], str) and re.fullmatch('[0-9a-f]{64}', report[field]))
    expected_cases = set(policy['native_cases']) | {'fixed-ensemble', 'independent-quadrature-and-radiosity', 'worker-input-boundary', 'worker-replay', 'worker-coupled-steady', 'million-facet-scaling'}
    require(len(report['cases']) == len(expected_cases) and {c['id'] for c in report['cases']} == expected_cases)
    require(all(c['status'] == 'passed' for c in report['cases']))
    expected_runs = {(g, seed, n) for g in policy['quantities'] for seed in statistical['seeds'] for n in statistical['samples_per_replicate']}
    require(len(report['runs']) == len(expected_runs))
    for run in report['runs']:
        key = run['geometry'], run['seed'], run['samples']
        require(key in expected_runs and re.fullmatch('[0-9a-f]{64}', run['raw_sha256']))
        expected_runs.remove(key)
    expected = {(g, seed, n, q) for g, qs in policy['quantities'].items() for q in qs for seed in statistical['seeds'] for n in statistical['samples_per_replicate']}
    ensemble = report['ensemble']
    require(ensemble['status'] == 'passed' and ensemble['family_size'] == len(expected) and len(ensemble['observations']) == len(expected) and ensemble['misses'] == [])
    z = NormalDist().inv_cdf(1-(1-statistical['coverage'])/(2*len(expected)))
    require(ensemble['normal_quantile'] == z)
    errors = {n: [] for n in statistical['samples_per_replicate']}
    for o in ensemble['observations']:
        key = o['geometry'], o['seed'], o['samples'], o['quantity']
        require(key in expected); expected.remove(key)
        g, _, n, q = key
        p, lo, hi = wilson(o['hits'], n, z)
        error = abs(p-policy['quantities'][g][q])
        require((o['estimate'], o['lower'], o['upper'], o['error']) == (p, lo, hi, error))
        require(lo-1e-15 <= policy['quantities'][g][q] <= hi+1e-15)
        if n == statistical['samples_per_replicate'][-1]: require(error <= statistical['practical_absolute_error'])
        errors[n].append(error**2)
    rms = {str(n): math.sqrt(sum(e)/len(e)) for n, e in errors.items()}
    require(ensemble['rms_error'] == rms and ensemble['converged'] is True and ensemble['practical_error_passed'] is True)
    ns = statistical['samples_per_replicate']
    require(all(rms[str(b)] < rms[str(a)] for a, b in zip(ns, ns[1:])))
    scaling = {(4*s*s, n, r) for s in policy['scaling_subdivisions'] for n in policy['scaling_samples'] for r in range(policy['scaling_replicates'])}
    require(len(report['scaling']) == len(scaling))
    for c in report['scaling']:
        key = c['facets'], c['samples'], c['replicate']
        require(key in scaling); scaling.remove(key)
        require(c['seed'] == statistical['seeds'][c['replicate']] and re.fullmatch('[0-9a-f]{64}', c['raw_sha256']))
        for k in ('storage_bytes', 'peak_working_set_bytes', 'build_seconds', 'trace_seconds', 'rays_per_second'):
            require(math.isfinite(c[k]) and c[k] > 0)
        require(c['storage_bytes'] <= policy['maximum_storage_bytes_per_facet']*c['facets'])
        require(math.isfinite(c['maximum_absolute_error']) and 0 <= c['maximum_absolute_error'] <= policy['scaling_practical_error'])
        require(c['rays_per_second'] == 2*c['samples']/c['trace_seconds'])
    reference = report['independent_reference']
    require(abs(reference['plate_quadrature']-policy['quantities']['plates']['lower/front->upper/front']) < 1e-12)
    require(0 <= reference['quadrature_error_bound'] < 1e-10)
    require(0 <= reference['maximum_radiosity_error'] <= policy['source_comparison_tolerance_W'])
    require(0 <= reference['coupled_steady_temperature_error_K'] < 1e-6)
    return True
