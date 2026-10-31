# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned WP-11 oracles and captured-reference comparison, with bounded receipts.

Reference artifact checks establish byte/model/result correspondence. They never
grant license authenticity, vendor compatibility or full Q1 qualification.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import tempfile

from .gate import evaluate


def require(good, code='thermal_qualification'):
    if not good:
        raise ValueError(code)


def finite(value):
    require(type(value) in (int, float) and math.isfinite(value))
    return value


def digest(raw):
    return sha256(raw).hexdigest()


def qualification(policy, cases):
    """Derive coverage from actual required case verdicts, never editable labels."""
    rows=[]
    for requirement,required in policy['requirements'].items():
        selected=[r for r in cases if r['id'] in required]
        gate=evaluate(required,selected)
        rows.append({'requirement_id':requirement,'native_status':gate['status'],
                     'required_cases':required,'remaining_q1_gates':policy['remaining_q1_gates'].get(requirement,[])})
    return {'schema_version':1,'execution_mode':'fcst_native','requirements':rows,
            'native_status':'passed' if all(r['native_status']=='passed' for r in rows) else 'failed',
            'licensed_paired_status':'blocked','licensed_paired_reason':'approved_reference_pair_unavailable',
            'q1_qualified':False}


def metrics_check(policy, metrics):
    require(set(metrics)=={'transient-event-refinement','transient-network-profile','transient-network-localized'})
    event=metrics['transient-event-refinement']; p=policy['event_refinement']
    require(set(event)=={'coarse_error_s','medium_error_s','fine_error_s','fine_duty_error','coarse_steps','medium_steps','fine_steps'})
    for value in event.values():require(finite(value)>=0)
    require(event['coarse_error_s']>0 and event['medium_error_s']<p['maximum_error_ratio']*event['coarse_error_s']
            and event['fine_error_s']<p['maximum_error_ratio']*event['medium_error_s']
            and event['fine_error_s']<p['maximum_fine_error_s'] and event['fine_duty_error']<p['maximum_fine_duty_error'])
    require(all(type(event[k]) is int for k in ('coarse_steps','medium_steps','fine_steps'))
            and 0<event['coarse_steps']<event['medium_steps']<event['fine_steps'])
    for name in ('transient-network-profile','transient-network-localized'):
        profile=metrics[name]; p=policy['representative_network']
        require(set(profile)=={'equations','nonzeros','accepted_steps','residual_evaluations','jacobian_evaluations','linear_solves',
                              'assembly_seconds','linear_seconds','total_seconds','energy_defect_J'})
        for value in profile.values():finite(value)
        for k in ('equations','nonzeros','accepted_steps','residual_evaluations','jacobian_evaluations','linear_solves'):
            require(type(profile[k]) is int and profile[k]>0)
        require(profile['equations']==p['equations'] and profile['nonzeros']==p['nonzeros']
                and abs(profile['energy_defect_J'])<=p['maximum_energy_defect_J'])
        require(profile['assembly_seconds']>0 and profile['linear_seconds']>0
                and profile['total_seconds']>=profile['assembly_seconds']+profile['linear_seconds'])


def import_literal(raw, ecosystem, units, source_version):
    """Only a single inert, constant source deck; never execute source code."""
    from fcst_exchange.sinda import SindaAdapter,SindaUnits
    from fcst_exchange.esatan import EsatanAdapter,EsatanUnits
    require(ecosystem in ('sinda','esatan') and isinstance(raw,bytes) and len(raw)<=1048576)
    require(isinstance(units,list) and len(units)==5)
    if ecosystem=='sinda':
        require(source_version=='6.3')
        adapter=SindaAdapter(SindaUnits(*units)); name='network.inp'
    else:
        adapter=EsatanAdapter(EsatanUnits(*units),source_version=source_version); name='network.d'
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder); (root/name).write_bytes(raw)
        staged=adapter.preview(root,name)
        model=staged.require_native()
        require(len(staged.sources)==1 and (root/name).read_bytes()==raw)
    return model


def source_model(definition):
    require(set(definition)=={'ecosystem','source_version','filename','units','source_ascii'})
    require(definition['filename']=={'sinda':'network.inp','esatan':'network.d'}.get(definition['ecosystem']))
    raw=definition['source_ascii'].encode('ascii')
    return import_literal(raw,definition['ecosystem'],definition['units'],definition['source_version'])


def oracle_model(model, criteria):
    """Assert frozen physical constants independently of imported solver output."""
    nodes={}
    for source in model['source_maps']:
        for entry in source['entries']:
            if entry['handle'].startswith('node.'):
                number=int(entry['handle'].split('.')[1]); require(number not in nodes)
                nodes[number]=entry['entity_id']
    require(set(nodes)=={1,2,3})
    entities={e['id']:e for e in model['entities']}
    expected={1:('capacitive',criteria['initial_K'],criteria['capacity_J_per_K']),
              2:('algebraic',criteria['algebraic_guess_K'],0),3:('prescribed',criteria['boundary_K'],0)}
    for number,(classification,temperature,capacity) in expected.items():
        e=entities[nodes[number]]
        require(e['classification']==classification and abs(e['temperature']['value']-temperature)<1e-10
                and e['temperature']['unit']=='K' and e['capacity']=={'value':capacity,'unit':'J/K'})
    conductors=[e for e in entities.values() if e['kind']=='conductor']
    require(len(conductors)==2)
    edges={frozenset((e['from_node_id'],e['to_node_id'])) for e in conductors}
    require(edges=={frozenset((nodes[1],nodes[2])),frozenset((nodes[2],nodes[3]))})
    require(all(e['conductance']=={'value':criteria['link_W_per_K'],'unit':'W/K'} for e in conductors))
    loads=[e for e in entities.values() if e['kind']=='load']
    require(len(loads)==1 and loads[0]['node_id']==nodes[1] and loads[0]['power']=={'value':criteria['load_W'],'unit':'W'})
    return nodes


def source_results(model, steady, transient, criteria):
    nodes=oracle_model(model,criteria)
    require(steady['status']=='passed' and steady['outcome']=='converged'
            and transient['status']=='passed' and transient['valid'] is True)
    require(transient['backend']['execution_mode']=='fcst_native' and transient['backend']['external_reference'] is False)
    equivalent=criteria['link_W_per_K']/2
    equilibrium=criteria['boundary_K']+criteria['load_W']/equivalent
    tau=criteria['capacity_J_per_K']/equivalent
    temperature_error=power_error=storage_error=0
    steady_nodes={r['node_id']:r for r in steady['nodes']}
    require(set(steady_nodes)==set(nodes.values()) and len(steady['nodes'])==3)
    expected={1:equilibrium,2:(equilibrium+criteria['boundary_K'])/2,3:criteria['boundary_K']}
    for number,value in expected.items():
        temperature_error=max(temperature_error,abs(finite(steady_nodes[nodes[number]]['temperature_K'])-value))
    power_error=abs(finite(steady_nodes[nodes[3]]['boundary_power_W'])+criteria['load_W'])
    ids=transient['node_ids']; require(len(ids)==3 and set(ids)==set(nodes.values()))
    index={number:ids.index(identifier) for number,identifier in nodes.items()}
    require([s['time_s'] for s in transient['samples']]==criteria['output_times_s'])
    for sample in transient['samples']:
        require(sample['valid'] is True)
        temperature=equilibrium+(criteria['initial_K']-equilibrium)*math.exp(-sample['time_s']/tau)
        expected={1:temperature,2:(temperature+criteria['boundary_K'])/2,3:criteria['boundary_K']}
        for number,value in expected.items():
            temperature_error=max(temperature_error,abs(finite(sample['temperature_K'][index[number]])-value))
        power_error=max(power_error,abs(finite(sample['boundary_power_W'][index[3]])+equivalent*(temperature-criteria['boundary_K'])))
        storage_error=max(storage_error,abs(finite(sample['storage_change_J'][index[1]])-criteria['capacity_J_per_K']*(temperature-criteria['initial_K'])))
        require(abs(finite(sample['run_energy']['defect_J']))<1e-6)
    require(temperature_error<criteria['temperature_tolerance_K'] and power_error<criteria['power_tolerance_W']
            and storage_error<criteria['storage_tolerance_J'])
    return {'maximum_temperature_error_K':temperature_error,'maximum_boundary_power_error_W':power_error,
            'maximum_storage_error_J':storage_error,'node_classes':3,'execution_mode':'fcst_native','vendor_qualified':False}


def artifact(root, reference, maximum):
    from fcst_exchange.vendor_paths import checked_path
    require(isinstance(reference,dict) and set(reference)=={'path','sha256','byte_length'})
    length=reference['byte_length']
    require(type(length) in (int,float) and math.isfinite(length) and float(length).is_integer() and 0<length<=maximum)
    require(isinstance(reference['sha256'],str) and re.fullmatch('[0-9a-f]{64}',reference['sha256']))
    path=checked_path(root,reference['path'])
    with path.open('rb') as stream:raw=stream.read(maximum+1)
    require(len(raw)==reference['byte_length'] and digest(raw)==reference['sha256'],'reference_artifact_binding')
    return raw


def captured_reference(manifest, root, run_native, criteria):
    """Compare native execution against exactly bound printed/TMD temperature data.

    A passing comparison is not proof that an input receipt is authentic or that
    a license is valid. Admission to licensed Q1 remains a separate reviewed gate.
    """
    from fcst_contracts import loads,read
    from fcst_app.persistence import encode
    from fcst_exchange.sinda_results import read_print
    from fcst_exchange.esatan_results import TmdBinding,read_tmd
    from fcst_exchange.esatan import EsatanUnits
    fields={'version','execution_mode','ecosystem','source_version','units','model','results','receipt'}
    require(isinstance(manifest,dict) and fields<=set(manifest) and set(manifest)<=fields|{'tmd_binding'})
    require(manifest['version']=='fcst-thermal-captured-reference/1' and manifest['execution_mode']=='reference_external','reference_execution_mode')
    p=criteria['captured_reference']; ecosystem=manifest['ecosystem']; require(ecosystem in p['required_ecosystems'])
    source=artifact(root,manifest['model'],p['maximum_input_bytes'])
    raw=artifact(root,manifest['results'],p['maximum_result_bytes'])
    receipt_raw=artifact(root,manifest['receipt'],p['maximum_input_bytes']); receipt=loads(receipt_raw)
    receipt_fields={'execution_mode','ecosystem','source_version','model_sha256','results_sha256','executable_sha256','settings_sha256','run_id_sha256','review_decision_sha256'}
    require(isinstance(receipt,dict) and set(receipt)==receipt_fields,'reference_receipt')
    require(receipt['execution_mode']=='reference_external' and receipt['ecosystem']==ecosystem and receipt['source_version']==manifest['source_version']
            and receipt['model_sha256']==digest(source) and receipt['results_sha256']==digest(raw),'reference_receipt_binding')
    for key in receipt_fields-{'execution_mode','ecosystem','source_version'}:
        require(isinstance(receipt[key],str) and re.fullmatch('[0-9a-f]{64}',receipt[key]),'reference_receipt')
    model=read('model',import_literal(source,ecosystem,manifest['units'],manifest['source_version']))
    if ecosystem=='sinda':
        require('tmd_binding' not in manifest)
        results=read_print(raw,model,quantity='temperature',unit=manifest['units'][0],time_unit=manifest['units'][4])
    else:
        binding=deepcopy(manifest.get('tmd_binding'))
        require(isinstance(binding,dict),'reference_tmd_binding')
        require(binding.get('source_sha256')==digest(raw) and binding.get('model_sha256')==digest(encode(model)),'reference_tmd_binding')
        binding['models']=tuple(tuple(row) for row in binding['models'])
        if 'inactive_nodes' in binding:binding['inactive_nodes']=tuple(tuple(row) for row in binding['inactive_nodes'])
        results=read_tmd(raw,model,TmdBinding(**binding),EsatanUnits(*manifest['units']))
    require(len(results.time)>=2 and results.time[0]==0 and results.time[-1]>0 and not results.discontinuities,'reference_time_grid')
    request={'thermal_input':{'contract_version':'1.0.0','model':model,'material_laws':[],'node_storage':[]},
             'transient':{'start':0,'end':results.time[-1],'output_times':list(results.time),
                          'absolute_temperature_tolerance':1e-7,'relative_temperature_tolerance':0}}
    native=run_native(request)
    require(native['status']=='passed' and native['valid'] is True and native['backend']['execution_mode']=='fcst_native'
            and native['backend']['external_reference'] is False,'reference_native_execution')
    node_ids=native['node_ids']; require(len(node_ids)==len(set(node_ids)) and set(node_ids)==set(results.entity_ids),'reference_node_grid')
    samples=native['samples'];require([s['time_s'] for s in samples]==list(results.time),'reference_time_grid')
    maximum_error=0
    for sample,expected in zip(samples,results.values):
        require(sample['valid'] is True and len(sample['temperature_K'])==len(node_ids),'reference_sample')
        for identifier,value in zip(results.entity_ids,expected):
            actual=finite(sample['temperature_K'][node_ids.index(identifier)])
            error=abs(actual-value);maximum_error=max(maximum_error,error)
            require(error<=p['maximum_temperature_error_K']+p['maximum_relative_temperature_error']*abs(value),'reference_temperature_mismatch')
    return {'status':'passed','comparison_mode':'owned_vs_captured_reference','ecosystem':ecosystem,
            'model_sha256':digest(source),'results_sha256':digest(raw),'receipt_sha256':digest(receipt_raw),
            'maximum_temperature_error_K':maximum_error,'samples':len(samples),'nodes':len(node_ids),
            'vendor_qualified':False,'q1_qualified':False,'qualification_reason':'reviewed_licensed_profile_admission_required'}
