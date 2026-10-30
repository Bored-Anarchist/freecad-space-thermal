# SPDX-License-Identifier: MIT OR Apache-2.0
"""Unattended native WP-11.1/11.2 acceptance with no external thermal runtime."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python'))
from fcst_contracts import inspect
from fcst_tools.gate import evaluate
from fcst_tools.thermal import input_hashes, assess


def uid(n): return f'00000000-0000-4000-8000-{n:012d}'
def quantity(value, unit): return {'value': value, 'unit': unit}
def entity(value, n): return next(e for e in value['model']['entities'] if e['id'] == uid(n))


def check(worker, native_tests):
    policy = json.loads((ROOT/'ci/thermal-acceptance.json').read_bytes())
    fixture = ROOT/'tests/fixtures/thermal/material-network.json'
    baseline = json.loads(fixture.read_bytes())
    # Prove installed engine execution with Python, host and vendor search paths absent.
    env = {k: v for k, v in os.environ.items() if k.upper() not in
           {'PYTHONPATH', 'PYTHONHOME', 'FREECAD_LIB', 'FREECAD_USER_HOME', 'SINDAPATH', 'ESATAN'} }
    env['PATH'] = str(worker.parent)
    def run(value):
        raw = value if isinstance(value, bytes) else json.dumps(value, allow_nan=False).encode()
        result = subprocess.run([str(worker), '--thermal-prepare'], input=raw, capture_output=True, env=env, timeout=30)
        output = json.loads(result.stdout)
        assert result.returncode == (0 if output['status'] == 'passed' else 1) and not result.stderr
        return output
    def passes(value):
        result = run(value); assert result['status'] == 'passed' and result['solver_available'] is False
        return result
    def rejects(value, *codes):
        result = run(value); assert result['status'] == 'failed' and result['code'] in codes
        return result
    def preparation():
        result = passes(baseline)
        assert result['model_hash'] == inspect('model', json.dumps(baseline['model']).encode())['semantic_hash']
        assert result['material_count'] == 1 and result['source_identity_count'] == 3
        assert [n['equation'] for n in result['nodes']] == [0, 1, None]
        assert [n['differential_index'] for n in result['nodes']] == [0, None, None]
        assert [n['algebraic_index'] for n in result['nodes']] == [None, 0, None]
    def canonical_identity():
        value = deepcopy(baseline)
        value['model']['entities'].reverse(); value['model']['source_maps'].reverse()
        for source in value['model']['source_maps']: source['entries'].reverse()
        for e in value['model']['entities']:
            if e['kind'] == 'node': e['temperature'] = quantity(26.85, 'degC')
        value['model']['revision'] = 20
        first, second = passes(baseline), passes(value)
        assert first == second
        value['node_storage'][0]['mass']['value'] = 3
        entity(value, 4)['capacity']['value'] = 9
        assert passes(value)['preparation_hash'] != first['preparation_hash']
    def disconnected():
        value = deepcopy(baseline)
        value['model']['entities'] = [e for e in value['model']['entities'] if e['kind'] != 'conductor']
        components = passes(value)['components']
        assert len(components) == 3
        assert [(c['steady_conduction_singular'], c['transient_algebraic_singular']) for c in components] == [(True,False),(True,True),(False,False)]
        # A second independent prescribed/capacitive component is well posed.
        a = deepcopy(entity(value, 4)); a['id'] = uid(20)
        b = deepcopy(entity(value, 6)); b['id'] = uid(21)
        c = deepcopy(entity(baseline, 7)); c.update(id=uid(22), from_node_id=uid(20), to_node_id=uid(21))
        value['model']['entities'] += [a,b,c]
        assert passes(value)['components'][-1]['steady_conduction_singular'] is False
    def zero_links():
        value = deepcopy(baseline)
        for n in (7,8): entity(value,n)['conductance']['value'] = 0
        assert len(passes(value)['components']) == 3
        entity(value,7)['conductance']['value'] = -1
        rejects(value,'range')
    def invalid_structure():
        for change in ('duplicate','reference','class','dimension','source'):
            value = deepcopy(baseline)
            if change == 'duplicate': value['model']['entities'].append(deepcopy(entity(value,4)))
            if change == 'reference': entity(value,7)['to_node_id'] = uid(999)
            if change == 'class': entity(value,5)['capacity']['value'] = 1
            if change == 'dimension': entity(value,4)['temperature']['unit'] = 'W'
            if change == 'source': value['model']['source_maps'][0]['entries'].append(deepcopy(value['model']['source_maps'][0]['entries'][0]))
            rejects(value,'range','dimension','reference','duplicate_id')
    def invalid_tables():
        for change in ('unit','axis','length','zero','negative','jump','incomplete','duplicate','unknown','empty'):
            value = deepcopy(baseline); table = value['material_laws'][0]['specific_heat']
            if change == 'unit': table['values'][0]['unit'] = 'W'
            if change == 'axis': table['temperature'][1] = deepcopy(table['temperature'][0])
            if change == 'length': table['values'].pop()
            if change == 'zero': table['values'][0]['value'] = 0
            if change == 'negative': table['values'][1]['value'] = -1
            if change == 'jump': table['discontinuities'] = [1]
            if change == 'incomplete': table['temperature'][0]['value'] = 250
            if change == 'duplicate': value['material_laws'].append(deepcopy(value['material_laws'][0]))
            if change == 'unknown': value['material_laws'][0]['material_id'] = uid(999)
            if change == 'empty': del value['material_laws'][0]['specific_heat']
            rejects(value,'schema','range','dimension','duplicate_id','reference')
    def storage_binding():
        for change in ('mass','mismatch','algebraic','duplicate','temperature','dimension'):
            value = deepcopy(baseline); binding = value['node_storage'][0]
            if change == 'mass': binding['mass']['value'] = 0
            if change == 'mismatch': binding['mass']['value'] = 3
            if change == 'algebraic': binding['node_id'] = uid(5)
            if change == 'duplicate': value['node_storage'].append(deepcopy(binding))
            if change == 'temperature': entity(value,4)['temperature']['value'] = 450
            if change == 'dimension': binding['mass']['unit'] = 'K'
            rejects(value,'range','storage_mismatch','duplicate_id','dimension')
    def tensors():
        for tensor in ([[1,2,0],[2,1,0],[0,0,1]], [[1,1,0],[0,1,0],[0,0,1]], [[1,0,0],[0,1,0],[0,0,0]]):
            value = deepcopy(baseline); entity(value,9)['conductivity_tensor'] = tensor
            rejects(value,'range')
        value = deepcopy(baseline); del entity(value,9)['frame_id']; rejects(value,'frame')
        value = deepcopy(baseline)
        value['material_laws'][0]['conductivity'] = deepcopy(value['material_laws'][0]['specific_heat'])
        for q in value['material_laws'][0]['conductivity']['values']: q['unit'] = 'W/(m*K)'
        rejects(value,'unsupported_tensor_law')
    def source_diagnostic():
        value = deepcopy(baseline); entity(value,4)['capacity']['value'] = 0
        result = rejects(value,'range')
        assert result['entity_id'] == uid(4) and result['source_map_id'] == uid(11)
        value = deepcopy(baseline); value['node_storage'][0]['mass']['value'] = 3
        result = rejects(value,'storage_mismatch')
        assert result['entity_id'] == uid(4) and result['source_map_id'] == uid(11)
    def case_selection():
        value = json.loads((ROOT/'tests/fixtures/thermal/case-network.json').read_bytes())
        prepared = passes(value)
        assert len(prepared['components']) == 2
        del value['case_id']; rejects(value,'case_required')
        value['case_id'] = uid(999); rejects(value,'reference')
        value['case_id'] = uid(13)
        case = entity(value,13); case['overlays'].append(deepcopy(case['overlays'][0]))
        rejects(value,'duplicate_id')
    def safe_failures():
        for raw in (b'{',b'{}',b'[]', b'\xff', b'{' + b' '*1048576,
                    b'{"contract_version":"1.0.0","contract_version":"1.0.0"}'):
            rejects(raw,'invalid_json','schema','version')
        value = deepcopy(baseline); value['contract_version'] = '99.0.0'; rejects(value,'version')
        value = deepcopy(baseline); value['private_payload'] = 'opaque-marker'
        result = rejects(value,'schema'); assert 'opaque-marker' not in json.dumps(result)
        value = deepcopy(baseline); value['material_laws'][0]['specific_heat']['values'][0]['value'] = 1e309
        raw = json.dumps(value).encode(); rejects(raw,'invalid_json')
    cli = {'native-preparation': preparation, 'canonical-identity': canonical_identity,
           'disconnected-components': disconnected, 'zero-links': zero_links,
           'invalid-structure': invalid_structure, 'invalid-tables': invalid_tables,
           'storage-binding': storage_binding, 'tensor-validation': tensors,
           'source-diagnostics': source_diagnostic, 'case-selection': case_selection,
           'safe-failures': safe_failures}
    records = []
    for case in policy['required_cases']:
        try:
            if case.startswith('native-') and case != 'native-preparation':
                result = subprocess.run([str(native_tests), case.removeprefix('native-'), str(fixture)],
                                        capture_output=True, timeout=30, env=env)
                assert result.returncode == 0 and json.loads(result.stdout) == {'status':'passed'} and not result.stderr
            else: cli[case]()
            status = 'passed'
        except (AssertionError, KeyError, ValueError, OSError, subprocess.SubprocessError):
            status = 'failed'
        records.append({'id': case, 'status': status})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--native-tests', type=Path, required=True)
    parser.add_argument('--report', type=Path, default=ROOT/'.local/thermal.json')
    args = parser.parse_args()
    policy = json.loads((ROOT/'ci/thermal-acceptance.json').read_bytes())
    records = check(args.worker.resolve(), args.native_tests.resolve())
    report = {'schema_version':1, 'work_packages':['WP-11.1','WP-11.2'], 'solver_available':False,
              'candidate':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'input_sha256':input_hashes(ROOT), 'gate':evaluate(policy['required_cases'],records), 'cases':records}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'gate':report['gate'],'failures':[c['id'] for c in records if c['status']!='passed']}))
    try: assess(report,policy,input_hashes(ROOT),report['candidate'])
    except ValueError: return 1
    return 0


if __name__ == '__main__': raise SystemExit(main())
