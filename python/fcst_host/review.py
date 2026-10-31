# SPDX-License-Identifier: LGPL-2.1-or-later
"""Value-only review operations shared by the workbench and unattended clients."""
from copy import deepcopy
import math
import re
import uuid

from fcst_contracts import loads, normalize, read
from fcst_app.persistence import Package, encode, reject, semantic_hash


def uid(number):
    return str(uuid.UUID(int=(0x40008000000000000000 | number)))


def new_model():
    """An editable geometry-free network; no implicit engineering assumptions."""
    return read('model', dict(contract_version='1.0.0', minimum_reader='1.0.0',
        project_id=str(uuid.uuid4()), revision=0, entities=[], source_maps=[],
        mappings=[], attachments=[], assumptions=[], limitations=[]))


def example_model():
    model = new_model()
    model['project_id'] = uid(1)
    model['entities'] = [dict(id=uid(2), kind='submodel'),
        dict(id=uid(4), kind='node', submodel_id=uid(2), classification='capacitive',
             temperature=dict(value=310, unit='K'), capacity=dict(value=2, unit='J/K')),
        dict(id=uid(5), kind='node', submodel_id=uid(2), classification='capacitive',
             temperature=dict(value=290, unit='K'), capacity=dict(value=3, unit='J/K')),
        dict(id=uid(7), kind='conductor', from_node_id=uid(4), to_node_id=uid(5),
             conductance=dict(value=4, unit='W/K'))]
    return read('model', model)


def change(store, entity, *, expected_revision, key=None):
    model = store.snapshot()
    return store.apply('local-workbench', {'changes.apply'}, model['project_id'], expected_revision,
                       key or str(uuid.uuid4()), {'upsert': [entity], 'delete': []})


def settings(value):
    required = {'mode', 'start', 'end', 'samples', 'absolute_temperature_tolerance', 'relative_temperature_tolerance'}
    if not isinstance(value, dict) or set(value) != required:
        reject('solver_settings')
    if value['mode'] not in ('steady','transient'):
        reject('solver_settings')
    if any(type(v) not in (int, float) or not math.isfinite(v) for k,v in value.items() if k!='mode'):
        reject('solver_settings')
    if (not 0 <= value['start'] < value['end'] or not 2 <= value['samples'] <= 1001
            or int(value['samples']) != value['samples']
            or value['absolute_temperature_tolerance'] <= 0
            or value['relative_temperature_tolerance'] < 0):
        reject('solver_settings')
    return deepcopy(value)


DEFAULT_SETTINGS = dict(mode='transient',start=0, end=2, samples=21, absolute_temperature_tolerance=1e-5,
                        relative_temperature_tolerance=1e-6)


def configuration(value, model):
    """Closed, inert view metadata; malformed packages never leave a half-open host."""
    required={'sequence','options','case_id','bindings'}
    if not isinstance(value,dict) or not required<=value.keys() or set(value)-required-{'spatial_id'}:
        reject('review_configuration')
    sequence=value['sequence']
    if type(sequence) not in (int,float) or not math.isfinite(sequence) or sequence<0 or sequence!=int(sequence):
        reject('review_configuration')
    settings(value['options'])
    entities={e['id']:e for e in read('model',model)['entities']}
    if value['case_id'] is not None and (not isinstance(value['case_id'],str)
            or entities.get(value['case_id'],{}).get('kind')!='case'):
        reject('review_configuration')
    bindings=value['bindings']
    if not isinstance(bindings,list) or len(bindings)>len(entities):reject('review_configuration')
    seen=set()
    for binding in bindings:
        if not isinstance(binding,dict) or set(binding)!={'entity_id','target_id','subelement','source_revision'}:
            reject('review_configuration')
        if (not all(isinstance(v,str) for v in binding.values()) or binding['entity_id'] not in entities
                or binding['entity_id'] in seen or entities.get(binding['target_id'],{}).get('kind') not in ('geometry','face')
                or not re.fullmatch(r'Face[1-9][0-9]{0,6}',binding['subelement'])
                or not re.fullmatch(r'[a-f0-9]{64}',binding['source_revision'])):
            reject('review_configuration')
        seen.add(binding['entity_id'])
    if value.get('spatial_id') is not None:
        try:uuid.UUID(value['spatial_id'])
        except (ValueError,TypeError,AttributeError):reject('review_configuration')
    return deepcopy(value)


def request(model, options, case_id=None):
    model = read('model', model)
    options = settings(options)
    mode=options.pop('mode')
    envelope = dict(contract_version='1.0.0', model=model, material_laws=[], node_storage=[])
    if case_id:
        case = next((e for e in model['entities'] if e['id'] == case_id and e['kind'] == 'case'), None)
        if case is None:
            reject('unknown_case')
        envelope['case_id'] = case_id
        case = normalize(case)
        options.update(start=case['start']['value'], end=case['end']['value'])
        mode=case['mode']
    if mode=='steady':
        return '--thermal-steady',envelope
    count = int(options.pop('samples'))
    start, end = options['start'], options['end']
    options['output_times'] = [start+(end-start)*i/(count-1) for i in range(count)]
    return '--thermal-transient', dict(thermal_input=envelope, transient=options)


def validate_result(value, model):
    """Reject stale, partial, substituted and non-native results before display."""
    # Round trip bounds depth, size, duplicate keys, finite numbers and inert text.
    value = loads(encode(value))
    model = read('model', model)
    if not isinstance(value,dict): reject('invalid_result')
    if value.get('model_hash') != semantic_hash(model):
        reject('stale_result')
    backend = value.get('backend', {})
    if (value.get('status') != 'passed' or not isinstance(backend,dict) or backend.get('execution_mode') != 'fcst_native'
            or backend.get('external_reference') is not False):
        reject('invalid_result')
    if 'samples' not in value:
        # Native steady results contain per-node data rather than transient arrays.
        nodes = value.get('nodes', [])
        if not isinstance(nodes,list) or any(not isinstance(n,dict) or not {'node_id','temperature_K','boundary_power_W'}<=n.keys() for n in nodes):
            reject('result_identity')
        node_ids = [n['node_id'] for n in nodes]
        samples = [dict(time_s=0, temperature_K=[n['temperature_K'] for n in nodes],
                        boundary_power_W=[n['boundary_power_W'] for n in nodes],
                        valid=True, duty_cycles={}, run_energy={})]
        balance={name:value.get(name) for name in ('energy_defect_W','internal_exchange_defect_W')}
        if any(type(v) not in (int,float) for v in balance.values()):reject('result_samples')
        samples[0]['steady_balance_W']=balance
    else:
        if value.get('valid') is not True:
            reject('invalid_result')
        node_ids, samples = value.get('node_ids', []), value['samples']
    expected = {e['id'] for e in model['entities'] if e['kind'] == 'node'}
    if (not isinstance(node_ids,list) or any(not isinstance(i,str) for i in node_ids)
            or set(node_ids) != expected or len(node_ids) != len(expected) or not expected or not isinstance(samples,list) or not samples):
        reject('result_identity')
    previous = -1
    for sample in samples:
        if not isinstance(sample,dict): reject('result_samples')
        t = sample.get('time_s')
        temperatures = sample.get('temperature_K', [])
        if (type(t) not in (int, float) or t <= previous or sample.get('valid') is not True
                or not isinstance(temperatures,list) or len(temperatures) != len(node_ids)
                or any(type(v) not in (int,float) or v < 0 for v in temperatures)):
            reject('result_samples')
        for name in ('boundary_power_W', 'conductive_in_W', 'radiation_in_W', 'load_in_W',
                     'environment_in_W', 'storage_power_W', 'residual_W'):
            if name in sample and (not isinstance(sample[name], list) or len(sample[name]) != len(node_ids)
                                   or any(type(v) not in (int,float) for v in sample[name])):
                reject('result_samples')
        if not isinstance(sample.get('duty_cycles',{}),dict) or any(type(duty) not in (int,float) or not 0 <= duty <= 1 for duty in sample.get('duty_cycles', {}).values()):
            reject('result_samples')
        if 'conductor_power_W' in sample:
            powers=sample['conductor_power_W']
            if not isinstance(powers,list) or any(type(v) not in (int,float) for v in powers):reject('result_samples')
        energy=sample.get('run_energy',{})
        if not isinstance(energy,dict) or any(
                any(type(n) not in (int,float) for n in v) if isinstance(v,list) else type(v) not in (int,float)
                for v in energy.values()):reject('result_samples')
        previous = t
    return dict(node_ids=node_ids, samples=samples, native=value)


def attach_result(store, result, submitted_model, input_value, worker_hash):
    """Atomic immutable result plus revision-bound derivation in the portable store."""
    validate_result(result, submitted_model)
    result_id = str(uuid.uuid4())
    raw = encode(dict(schema_version=1, model=submitted_model, result=result,
                      input=input_value, worker_sha256=worker_hash))
    path = 'review/'+result_id+'.json'
    with store.transaction():
        state = store.state()
        if state['model'] != submitted_model:
            reject('stale_result')
        state['derived'].append(dict(id=result_id, kind='solve',
            dependencies=[e['id'] for e in submitted_model['entities']],
            revision=submitted_model['revision'], semantic_hash=semantic_hash(submitted_model), stale=False))
        artifact = (result_id, 'evidence', path, raw, [])
        package = Package.create(state['model'], [*store._artifacts(), artifact], state=state,
                                 **store._package_metadata())
        store.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?)',
                         (result_id, 'evidence', path, encode([]), raw))
        store.db.execute('UPDATE package_manifest SET data=? WHERE id=1', (encode(package.manifest),))
        store._write(state)
    return result_id


def query_result(store, result_id, *, historical=False):
    derived = store.derived(result_id, historical=historical)
    artifact = next((a for a in store._artifacts() if a[0] == result_id and a[2] == 'review/'+result_id+'.json'), None)
    if artifact is None:
        reject('result_unavailable')
    value = loads(artifact[3])
    if (derived['semantic_hash'] != semantic_hash(value['model'])
            or derived['revision'] != value['model']['revision']):
        reject('result_identity')
    result = validate_result(value['result'], value['model'])
    result['historical'] = derived['stale'] or value['model'] != store.snapshot()
    if result['historical'] and not historical:
        reject('stale_result')
    return result


def colour(value, lower, upper):
    """Perceptually ordered cool/teal/gold scale, fixed across all sample times."""
    f = .5 if upper == lower else max(0, min(1, (value-lower)/(upper-lower)))
    stops = ((.14,.22,.50), (.10,.65,.64), (.98,.80,.22))
    i = min(1, int(f*2)); u = f*2-i
    return tuple(stops[i][k]*(1-u)+stops[i+1][k]*u for k in range(3))


def display(result, sample_index, selected=None, unit='K'):
    if unit not in ('K', 'degC') or not 0 <= sample_index < len(result['samples']):
        reject('result_selection')
    ids, samples = result['node_ids'], result['samples']
    if selected is not None and selected not in ids:
        reject('result_identity')
    index = ids.index(selected) if selected else 0
    all_values = [v for s in samples for v in s['temperature_K']]
    lo, hi = min(all_values), max(all_values)
    sample = samples[sample_index]
    offset = 273.15 if unit == 'degC' else 0
    powers={k: sample[k] for k in ('conductor_power_W', 'boundary_power_W', 'conductive_in_W',
        'radiation_in_W', 'load_in_W', 'environment_in_W', 'storage_power_W', 'residual_W') if k in sample}
    powers.update({k:[v] for k,v in sample.get('steady_balance_W',{}).items()})
    return dict(time_s=sample['time_s'], unit=unit, lower=lo-offset, upper=hi-offset,
        temperatures=[v-offset for v in sample['temperature_K']],
        colours=[colour(v, lo, hi) for v in sample['temperature_K']],
        history=[(s['time_s'], s['temperature_K'][index]-offset) for s in samples],
        powers=powers,
        energy=sample.get('run_energy', {}), duty=sample.get('duty_cycles', {}))
