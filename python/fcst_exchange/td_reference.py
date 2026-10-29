# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned synthetic source-model creation/run, ASCII queries and analytic checks."""
from hashlib import sha256
import math
from pathlib import Path

from fcst_app.persistence import encode
from .core import reject
from .opentd import PROFILE,HostAuthorization,TdLimits,run_sidecar
from .td_project import capture_project,inventory
from .vendor_paths import path_name,checked_path
from .sinda_results import read_print


def compare(results,model,criteria):
    nodes={n['classification']:n['id'] for n in model['entities'] if n['kind']=='node'}
    if set(nodes)!={'capacitive','prescribed'} or len([n for n in model['entities'] if n['kind']=='node'])!=2:reject('reference_node_identity')
    if set(results)!=set(criteria['required_modes']):reject('reference_modes_missing')
    equilibrium=criteria['boundary_temperature_K']+criteria['load_W']/criteria['conductance_W_per_K']
    tau=criteria['capacity_J_per_K']/criteria['conductance_W_per_K'];maximum_error=0
    for mode,result in results.items():
        if result.quantity!='temperature' or result.unit!='K' or set(result.entity_ids)!=set(nodes.values()):reject('reference_result_identity')
        if mode=='transient' and (result.time[0]!=0 or result.time[-1]!=criteria['transient_end_s']):reject('reference_time_grid')
        for time,values in zip(result.time,result.values):
            warm=equilibrium if mode=='steady' else equilibrium+(criteria['initial_temperature_K']-equilibrium)*math.exp(-time/tau)
            expected={nodes['capacitive']:warm,nodes['prescribed']:criteria['boundary_temperature_K']}
            for entity,value in zip(result.entity_ids,values):
                error=abs(value-expected[entity]);maximum_error=max(maximum_error,error)
                if error>criteria['absolute_temperature_tolerance_K']+criteria['relative_temperature_tolerance']*abs(expected[entity]):reject('reference_temperature_mismatch')
    return {'status':'passed','profile':'fcst-synthetic-reference/1','execution_mode':'reference_external',
            'qualified':False,'maximum_temperature_error_K':maximum_error,'criteria_sha256':sha256(encode(criteria)).hexdigest(),
            'source_results_sha256':{mode:result.source_sha256 for mode,result in results.items()}}


def run_reference(runtime,sidecar,destination,authorization,outputs,criteria,*,limits=TdLimits()):
    if not runtime.probe()['available']:reject('licensed_runtime_prerequisite')
    sidecar=Path(sidecar).absolute()
    if not isinstance(authorization,HostAuthorization):reject('td_authorization')
    authorization.validate(sha256(b'fcst-synthetic-reference/1').hexdigest(),sha256(sidecar.read_bytes()).hexdigest(),True)
    if not isinstance(outputs,dict) or set(outputs)!={'steady','transient'}:reject('reference_output_mapping')
    for path in outputs.values():path_name(path)
    target=Path(destination).absolute()
    if target.exists():reject('reference_requires_new_root')
    checked_path(target.parent,target.name);target.mkdir();(target/'project').mkdir()
    data,receipt=run_sidecar(runtime,sidecar,target,{'profile':PROFILE,'operation':'run-reference','drawing':'project/reference.dwg'},
                             authorization=authorization,limits=limits)
    original=capture_project(target/'project','reference.dwg',limits)
    mapped=inventory(original,data,copied_root=target/'project')
    if mapped.model is None:reject('reference_network_unmapped')
    results={}
    for mode,name in outputs.items():
        path=checked_path(target,name)
        if not path.is_file():reject('reference_output_missing')
        with path.open('rb') as stream:raw=stream.read(16777217)
        results[mode]=read_print(raw,mapped.model,quantity='temperature',unit='K',time_unit='s',namespace_prefix='TD63.')
    assessment=compare(results,mapped.model,criteria)
    return {'profile':PROFILE,'fixture_kind':'fcst-synthetic-reference/1','receipt':receipt,'assessment':assessment,'qualified':False}
