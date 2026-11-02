# SPDX-License-Identifier: MIT OR Apache-2.0
"""Unattended WP-12 acceptance with all frozen seeds and bounded public evidence."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python'))
from fcst_tools.radiation import assess, assess_report, require, validate_run


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def input_hashes():
    paths = ['ci/radiation-acceptance-v1.json', 'ci/numerical-criteria-v1.json', 'tools/check_radiation.py',
             'python/fcst_tools/radiation.py', 'engine/src/radiation.cpp', 'engine/src/radiation_loading.inc',
             'engine/include/fcst/radiation.hpp', 'engine/tests/radiation_fixtures.hpp', 'engine/tests/radiation_tests.cpp',
             'engine/tests/radiation_subject.cpp', 'tests/fixtures/radiation/plates.json', 'tests/fixtures/radiation/steady.json']
    return {p: digest(ROOT/p) for p in paths}


def check(subject, native, worker, output):
    import numpy as np
    import scipy
    from scipy.integrate import dblquad
    from scipy.optimize import brentq
    from fcst_tools.radiation import wilson
    policy = json.loads((ROOT/'ci/radiation-acceptance-v1.json').read_bytes())
    statistical = json.loads((ROOT/'ci/numerical-criteria-v1.json').read_bytes())['statistical_policy']
    frozen_hashes = input_hashes()
    candidate = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    reference_versions = dict(numpy=np.__version__, scipy=scipy.__version__)
    require(reference_versions == policy['independent_backends'])
    work = output.parent/('radiation-attempt-'+str(time.time_ns()))
    work.mkdir(parents=True)
    env = dict(os.environ, PATH=str(worker.parent))
    for key in ('PYTHONPATH', 'PYTHONHOME', 'FREECAD_LIB', 'SINDAPATH', 'ESATAN'):
        env.pop(key, None)
    records, runs = [], []
    def execute(exe, arguments, stem, data=None):
        r = subprocess.run([str(exe), *map(str, arguments)], input=data, capture_output=True, cwd=ROOT, env=env, timeout=600)
        (work/(stem+'.json')).write_bytes(r.stdout)
        (work/(stem+'.log')).write_bytes(r.stderr)
        return r
    identity = execute(worker, ['--build-info'], 'worker-identity')
    require(identity.returncode == 0 and json.loads(identity.stdout)['source_revision'] == candidate)
    for case in policy['native_cases']:
        started = time.monotonic()
        r = execute(native, [case, ROOT/'tests/fixtures/thermal'], 'native-'+case)
        records.append(dict(id=case, status='passed' if r.returncode == 0 and r.stdout == b'passed\r\n' or r.returncode == 0 and r.stdout == b'passed\n' else 'failed',
                            seconds=round(time.monotonic()-started, 3)))
    for geometry, size in policy['geometry_size'].items():
        for n in statistical['samples_per_replicate']:
            for seed in statistical['seeds']:
                r = execute(subject, [geometry, seed, n, size], f'{geometry}-{seed}-{n}')
                require(r.returncode == 0 and not r.stderr)
                runs.append(validate_run(json.loads(r.stdout), geometry, seed, n, candidate))
        print(geometry+': complete fixed ensemble', flush=True)
    # Persist all samples, including misses, before assessing any aggregate.
    ensemble = assess(runs, policy, statistical, candidate)
    (work/'ensemble.json').write_text(json.dumps(ensemble, indent=2)+'\n')
    records.append(dict(id='fixed-ensemble', status=ensemble['status']))
    # Independently integrate the plate kernel reduced by translation symmetry.
    # This deterministic quadrature does not call the native intersection code.
    quadrature, error = dblquad(lambda y, x: 4*(1-x)*(1-y)/(np.pi*(1+x*x+y*y)**2), 0, 1, lambda _: 0, lambda _: 1, epsabs=1e-12, epsrel=1e-12)
    reference = policy['quantities']['plates']['lower/front->upper/front']
    require(abs(quadrature-reference) < 1e-12 and error < 1e-10)
    fixture = json.loads((ROOT/'tests/fixtures/radiation/plates.json').read_bytes())
    r = execute(worker, ['--radiation-evaluate'], 'worker-evaluation', json.dumps(fixture).encode())
    require(r.returncode == 0 and not r.stderr)
    result = json.loads(r.stdout)
    require(result['source_revision'] == candidate and result['input_sha256'] == hashlib.sha256(json.dumps(fixture).encode()).hexdigest())
    for row in result['raw']:
        for count_entry in row['counts']:
            expected = wilson(count_entry['hits'], row['samples'], 1.959963984540054)
            require(all(abs(count_entry[k]-v) < 1e-14 for k, v in zip(('estimate','lower','upper'), expected)))
    patches = result['patches']; count = len(patches)
    areas = np.array([p['area_m2'] for p in patches]); factors = np.zeros((count, count))
    for edge in result['edges']:
        i, j, g = edge['first'], edge['second'], edge['area_factor_m2']
        factors[i, j] = g/areas[i]
        factors[j, i] = g/areas[j]
    eps = np.array([.7, .4]); alpha = np.array([.3, .8])
    t = np.array(fixture['temperatures_K']); escape = np.array([p['escape'] for p in patches]); sigma = 5.670374419e-8
    eb = sigma*fixture['environment']['temperature_K']**4
    j = np.linalg.solve(np.eye(count)-(1-eps[:, None])*factors, eps*sigma*t**4+(1-eps)*escape*eb)
    direct = np.array(fixture['environment']['solar_incident_W_m2'])
    solar_j = np.linalg.solve(np.eye(count)-(1-alpha[:, None])*factors, (1-alpha)*direct)
    internal = areas*(factors@j-(1-escape)*j)
    environment = areas*(escape*(eb-j)+alpha*(factors@solar_j+direct))
    source_error = max(float(np.max(np.abs(j-np.array([p['radiosity_W_m2'] for p in patches])))),
                       float(np.max(np.abs(internal-np.array([p['internal_W'] for p in patches])))),
                       float(np.max(np.abs(environment-np.array([p['environment_W'] for p in patches])))))
    records.append(dict(id='independent-quadrature-and-radiosity', status='passed' if source_error <= policy['source_comparison_tolerance_W'] else 'failed'))
    require(max(abs(edge['area_factor_m2']-reference) for edge in result['edges']) < statistical['practical_absolute_error'])
    steady_fixture = json.loads((ROOT/'tests/fixtures/radiation/steady.json').read_bytes())
    solved = execute(worker, ['--radiation-steady'], 'worker-steady', json.dumps(steady_fixture).encode())
    require(solved.returncode == 0 and not solved.stderr)
    steady = json.loads(solved.stdout)
    # Two series conductors of 2 W/K give 1 W/K to the 300 K reservoir.
    equilibrium = brentq(lambda t: t-300 + sigma*(t**4-250**4)-5, 100, 400, xtol=1e-12)
    steady_error = abs(steady['temperatures_K'][0]-equilibrium)
    records.append(dict(id='worker-coupled-steady', status='passed' if steady_error < 1e-6 and abs(steady['energy_defect_W']) < 1e-7 else 'failed'))
    bad_steady = deepcopy(steady_fixture); bad_steady['facets'][0]['front']['ir_emittance'] = .9
    rejected = execute(worker, ['--radiation-steady'], 'reject-steady-optics', json.dumps(bad_steady).encode())
    require(rejected.returncode == 1 and json.loads(rejected.stdout)['code'] == 'radiation_mapping')
    # Actual JSON boundary mutations: no unsupported optics, malformed geometry,
    # missing node temperatures, unknown fields, nonintegral seeds or raw echo.
    mutations = []
    for kind in ('geometry', 'optics', 'node', 'unknown', 'seed'):
        f = deepcopy(fixture)
        if kind == 'geometry': f['facets'][0]['vertices_m'][1] = f['facets'][0]['vertices_m'][0]
        if kind == 'optics': f['facets'][0]['front']['ir_emittance'] = -1
        if kind == 'node': f['temperatures_K'] = [300]
        if kind == 'unknown': f['arbitrary'] = 'synthetic-untrusted-marker'
        if kind == 'seed': f['sampling']['seed'] = .5
        rejected = execute(worker, ['--radiation-evaluate'], 'reject-'+kind, json.dumps(f).encode())
        mutations.append(rejected.returncode == 1 and json.loads(rejected.stdout)['status'] == 'failed' and b'synthetic-untrusted-marker' not in rejected.stdout)
    records.append(dict(id='worker-input-boundary', status='passed' if all(mutations) else 'failed'))
    # Reproducible replay checks the whole non-timing artifact.
    replay = execute(worker, ['--radiation-evaluate'], 'worker-replay', json.dumps(fixture).encode())
    records.append(dict(id='worker-replay', status='passed' if replay.stdout == r.stdout else 'failed'))
    curves = []
    for size in policy['scaling_subdivisions']:
        for replicate in range(policy['scaling_replicates']):
            seed = statistical['seeds'][replicate]
            rscale = execute(subject, ['plates', seed, 0, size], f'scale-{size}-{replicate}')
            require(rscale.returncode == 0 and not rscale.stderr)
            lines = rscale.stdout.splitlines(keepends=True)
            require(len(lines) == len(policy['scaling_samples']))
            for n, raw in zip(policy['scaling_samples'], lines):
                (work/f'scale-{size}-{n}-{replicate}.json').write_bytes(raw)
                run = validate_run(json.loads(raw), 'plates', seed, n, candidate)
                require(run['facets'] == 4*size*size and run['storage_bytes'] <= policy['maximum_storage_bytes_per_facet']*run['facets'])
                estimates = [sum(c['hits'] for c in row['counts'])/n for row in run['rows']]
                practical_error = max(abs(p-reference) for p in estimates)
                require(practical_error <= policy['scaling_practical_error'])
                curves.append(dict(facets=run['facets'], samples=n, replicate=replicate, seed=seed,
                                   storage_bytes=run['storage_bytes'], peak_working_set_bytes=run['peak_working_set_bytes'], build_seconds=run['build_seconds'], trace_seconds=run['trace_seconds'],
                                   rays_per_second=2*n/run['trace_seconds'], maximum_absolute_error=practical_error,
                                   raw_sha256=hashlib.sha256(raw).hexdigest()))
        print(f'scaling: {4*size*size} facets complete', flush=True)
    records.append(dict(id='million-facet-scaling', status='passed'))
    report = dict(schema_version=1, profile=policy['profile'], candidate=candidate, execution_mode='fcst_native',
                  scope=policy['scope'], vendor_compatibility_qualified=False, q1_qualified=False,
                  input_sha256=input_hashes(), native_sha256=digest(subject), worker_sha256=digest(worker),
                  status='passed' if all(c['status'] == 'passed' for c in records) else 'failed', cases=records,
                  ensemble=ensemble, runs=[dict(geometry=x['geometry'], seed=x['seed'], samples=x['samples'],
                  build_seconds=x['build_seconds'], trace_seconds=x['trace_seconds'],
                  raw_sha256=digest(work/f"{x['geometry']}-{x['seed']}-{x['samples']}.json")) for x in runs],
                  independent_reference=dict(plate_quadrature=quadrature, quadrature_error_bound=error, maximum_radiosity_error=source_error, coupled_steady_temperature_error_K=steady_error), scaling=curves)
    report['independent_backends'] = reference_versions
    require(frozen_hashes == input_hashes())
    if report['status'] == 'passed': assess_report(report, policy, statistical, frozen_hashes, candidate)
    output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--subject', type=Path, required=True)
    p.add_argument('--native-tests', type=Path, required=True)
    p.add_argument('--worker', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args(); args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = check(args.subject.resolve(), args.native_tests.resolve(), args.worker.resolve(), args.report)
    except (OSError, ValueError, KeyError, AssertionError, subprocess.SubprocessError):
        args.report.write_text(json.dumps(dict(status='failed', reason='radiation_execution_or_acceptance_failed'))+'\n')
        print('radiation: failed; raw attempt retained locally', flush=True)
        return 1
    print('radiation: '+result['status'], flush=True)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
