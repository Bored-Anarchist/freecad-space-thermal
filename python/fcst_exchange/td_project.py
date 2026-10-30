# SPDX-License-Identifier: MIT OR Apache-2.0
"""Immutable local vendor project copies and complete, handle-based inventories."""
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import tempfile
import shutil

from fcst_app.persistence import encode
from fcst_contracts import ContractError,loads,read
from .core import reject,target_id
from .vendor_paths import path_name,checked_path
from .export import rename_new
from .opentd import (PROFILE,ASSEMBLY_SHA256,TdLimits,Runtime,HostAuthorization,run_sidecar,validate_edits)


from .source_tree import ProjectCopy,capture_project


@dataclass(frozen=True)
class TdInventory:
    original:ProjectCopy
    inventory_bytes:bytes
    report_bytes:bytes
    model_bytes:bytes|None
    copied_root:Path|None=None

    @property
    def report(self):return json.loads(self.report_bytes)
    @property
    def inventory(self):return json.loads(self.inventory_bytes)
    @property
    def model(self):return json.loads(self.model_bytes) if self.model_bytes else None
    def require_native(self):
        if not self.report['runnable']:reject('required_td_semantics_unresolved')
        return self.model


def inventory(project,data,*,copied_root=None):
    try:data=loads(encode(data))
    except (ContractError,ValueError,TypeError,RecursionError):reject('td_inventory_contract')
    expected={'profile','api','units','collections','dependency_paths','qualified','execution_mode'}
    if not isinstance(data,dict) or set(data)!=expected or data['profile']!=PROFILE or data['units']!='SI' or data['qualified'] is not False or data['execution_mode']!='reference_external':reject('td_inventory_contract')
    api=data['api']
    if not isinstance(api,dict) or api.get('assembly_version')!='6.3.0.0' or api.get('assembly_sha256')!=ASSEMBLY_SHA256 or api.get('qualified') is not False:reject('td_inventory_version')
    collections=data['collections']
    if not isinstance(collections,dict) or not isinstance(data['dependency_paths'],dict):reject('td_inventory_contract')
    records=[];entities=[];maps=[];handles={};source_keys=set();errors=[];submodels={}
    def numeric(value):
        if type(value) not in (int,float) or not math.isfinite(value):reject('td_number')
        return float(value)
    def dimension(value,kind):
        if not isinstance(value,dict) or set(value)!={'dimension','si_value'} or value['dimension']!=kind:reject('td_dimension')
        return numeric(value['si_value'])
    def identifier(kind,entity):
        handle=entity.get('Handle') if kind not in {'ThermoProps','OpticalProps'} else entity.get('Name')
        if not isinstance(handle,str) or not handle or len(handle)>256:reject('td_source_identity')
        key=(kind,handle.casefold())
        if key in source_keys:reject('td_source_collision')
        source_keys.add(key)
        return handle,target_id((PROFILE,kind,handle.casefold()))
    def source_map(entity_id,kind,handle,submodel='model',node_number=None):
        entry={'namespace':'TD63.'+submodel,'handle':kind+'.'+handle,'entity_id':entity_id}
        if node_number is not None:
            if type(node_number) not in (int,float) or int(node_number)!=node_number or not 0<node_number<=2147483647:reject('td_node_number')
            entry['node_number']=int(node_number)
        maps.append(entry)
    def row(kind,handle,target,status,code=''):
        records.append({'kind':kind,'source_id':project.entry+'#'+kind+':'+handle,'target_id':target,
                        'status':status,'limitations':[code] if code else [],'operation':'import',
                        'source_artifact_sha256':project.drawing_hash})
    def static(entity):
        for key,value in entity.items():
            if key.endswith('Exp') and value:
                text=value.get('Value','') if isinstance(value,dict) else None
                if not isinstance(value,dict) or 'unsupported' in value or text is not None and (not isinstance(text,str) or text!=''):reject('td_expression_requires_review')
            if key=='TCode' and value:
                # The SDK supplies a nonempty units descriptor even when all
                # source-code blocks are empty. It carries no code by itself.
                code_fields={'Variables0','Variables1','Variables2','Flogic0','Flogic1','Flogic2','Output',
                             'BeforeBuild','AfterBuild','PostSolution','Operations'}
                if not isinstance(value,dict) or set(value)-code_fields-{'Comment','TranslateCodeUnits'}:reject('td_source_logic_inert')
                if any(not isinstance(value.get(field,''),str) or value.get(field,'').strip() for field in code_fields):reject('td_source_logic_inert')
    node_data=collections.get('Nodes',[])
    if not isinstance(node_data,list):reject('td_inventory_contract')
    for entity in node_data:
        if not isinstance(entity,dict):reject('td_inventory_contract')
        handle,target=identifier('Node',entity)
        try:
            static(entity)
            if entity.get('UseMaterial')!=0 or entity.get('UseVersusTime',0)!=0:reject('td_material_or_time_node_requires_mapping')
            node_type=entity.get('NodeType')
            if not isinstance(node_type,str) or node_type not in {'DIFFUSION','ARITHMETIC','BOUNDARY'}:reject('td_node_class')
            sm=entity.get('Submodel')
            sm=sm.get('Name') if isinstance(sm,dict) else sm
            if not isinstance(sm,str) or not sm or len(sm)>128:reject('td_submodel_identity')
            if sm not in submodels:
                submodels[sm]=target_id((PROFILE,'submodel',sm))
                entities.append({'id':submodels[sm],'kind':'submodel'});source_map(submodels[sm],'submodel',sm)
            capacity=0 if node_type in {'ARITHMETIC','BOUNDARY'} else numeric(entity.get('MassVol'))
            entities.append({'id':target,'kind':'node','submodel_id':submodels[sm],
                             'classification':{'DIFFUSION':'capacitive','ARITHMETIC':'algebraic','BOUNDARY':'prescribed'}[node_type],
                             'temperature':{'value':dimension(entity.get('InitialTemp'),'Temp'),'unit':'K'},'capacity':{'value':capacity,'unit':'J/K'}})
            handles[handle.casefold()]=target;source_map(target,'Node',handle,sm,entity.get('Id'));row('Node',handle,target,'native-reconstructed')
        except ValueError as error:row('Node',handle,None,'retained-opaque',str(error))
    for collection,kind in [('Conductors','Conductor'),('HeatLoads','HeatLoad')]:
        values=collections.get(collection,[])
        if not isinstance(values,list):reject('td_inventory_contract')
        for entity in values:
            if not isinstance(entity,dict):reject('td_inventory_contract')
            handle,target=identifier(kind,entity)
            try:
                static(entity)
                if any(entity.get(field,0)!=0 for field in ('UseMaterial','IsRadiation','IsPerArea','UseVersusTime','UseVsTempDiff','OneWayAdvection')):reject('td_connection_feature_requires_mapping')
                def connection(value):
                    if not isinstance(value,dict) or value.get('Marker',0)!=0:reject('td_connection_marker')
                    source=value.get('Handle')
                    if not isinstance(source,str) or source.casefold() not in handles:reject('td_connection_identity')
                    return handles[source.casefold()]
                if kind=='Conductor':
                    direction=entity.get('OneWay','NONE')
                    if not isinstance(direction,str) or direction not in {'NONE','BOTH','0'}:reject('td_one_way_requires_mapping')
                    targets=entity.get('To')
                    if not isinstance(targets,list) or len(targets)!=1:reject('td_distributed_conductor')
                    mapped={'id':target,'kind':'conductor','from_node_id':connection(entity.get('From')),
                            'to_node_id':connection(targets[0]),'conductance':{'value':numeric(entity.get('Value')),'unit':'W/K'}}
                else:
                    connections=entity.get('ApplyConnections')
                    if entity.get('Type')!='LOAD' or not isinstance(connections,list) or len(connections)!=1:reject('td_distributed_or_flux_load')
                    mapped={'id':target,'kind':'load','node_id':connection(connections[0]),'power':{'value':numeric(entity.get('Value')),'unit':'W'}}
                entities.append(mapped);source_map(target,kind,handle);row(kind,handle,target,'native-reconstructed')
            except ValueError as error:row(kind,handle,None,'retained-opaque',str(error))
    source_submodels=collections.get('Submodels',[])
    if not isinstance(source_submodels,list):reject('td_inventory_contract')
    for entity in source_submodels:
        if not isinstance(entity,dict) or not isinstance(entity.get('Name'),str) or not entity['Name']:reject('td_submodel_identity')
        name=entity['Name']
        if set(entity)-{'Name','Comment'}:
            row('Submodel',name,None,'retained-opaque','td_submodel_fields_require_mapping');continue
        if name not in submodels:
            submodels[name]=target_id((PROFILE,'submodel',name));entities.append({'id':submodels[name],'kind':'submodel'});source_map(submodels[name],'submodel',name)
        row('Submodel',name,submodels[name],'native-reconstructed')
    # Every nonempty collection, including geometry, GMM/TMM, tables, controls,
    # property databases, source logic and cases, remains in the immutable IR.
    # Never invent native representation for a collection not yet mapped.
    for collection,value in collections.items():
        if collection in {'Nodes','Conductors','HeatLoads','Submodels','DwgUnits'} or not value:continue
        items=value if isinstance(value,list) else [value]
        if len(items)>20000:reject('td_inventory_limit')
        for index,entity in enumerate(items):
            handle=entity.get('Handle',entity.get('Name',str(index))) if isinstance(entity,dict) else str(index)
            row(collection,str(handle),None,'retained-opaque','td_collection_requires_native_mapping')
    for role,path in data['dependency_paths'].items():
        if not isinstance(path,str):reject('td_dependency_contract')
        if not path:continue
        # Full path text stays in private IR. Matching a basename alone cannot
        # prove that an external DB is the exact copied fixture dependency.
        base=Path(copied_root).absolute() if copied_root else project.root
        candidate=Path(path)
        if not candidate.is_absolute():candidate=base/candidate
        try:relative=candidate.absolute().relative_to(base).as_posix()
        except ValueError:relative=None
        if relative not in dict(project.files):errors.append({'code':'td_external_dependency_unresolved','category':role})
    model={'contract_version':'1.0.0','minimum_reader':'1.0.0','project_id':target_id((PROFILE,project.source_hash)),'revision':0,
           'entities':entities,'source_maps':[{'id':target_id((PROFILE,'map',project.source_hash)),'version':'1.0.0',
           'source_revision':project.source_hash,'source_tool':'Thermal Desktop/OpenTD','source_version':'6.3.022','entries':maps}],
           'mappings':[],'attachments':[],'assumptions':['API working units explicitly set to SI'],
           'limitations':['Only explicitly mapped constant network entities are native; remaining TD collections are retained in source IR'],
           'audit':{'timestamp':'source-import'},'gui':{'selection':[]}}
    try:model=read('model',loads(encode(model)))
    except ContractError:model=None;errors.append({'code':'td_native_contract'})
    runnable=model is not None and bool(handles) and not errors and all(r['status']=='native-reconstructed' for r in records)
    report={'profile':PROFILE,'source_revision':project.source_hash,'source_kind':'thermal-model' if node_data else 'geometry-only',
            'runnable':runnable,'qualified':False,'records':records,'diagnostics':errors,
            'native_execution_available':False,'source_tool_execution_mode':'reference_external'}
    return TdInventory(project,encode(data),encode(report),encode(model) if model is not None else None,Path(copied_root).absolute() if copied_root else None)


class OpenTdAdapter:
    profile=PROFILE
    def __init__(self,runtime,sidecar):self.runtime=runtime;self.sidecar=Path(sidecar)
    def probe(self):return self.runtime.probe()
    def inspect(self,project,destination,authorization,limits=TdLimits(),property_databases=None):
        # Missing runtimes and authorization fail before copying or opening source.
        if not self.probe()['available']:reject('licensed_runtime_prerequisite')
        if not isinstance(authorization,HostAuthorization):reject('td_authorization')
        authorization.validate(project.drawing_hash,sha256(self.sidecar.read_bytes()).hexdigest())
        databases=validate_databases(project,property_databases or {})
        job,copy=prepare_job(project,destination,limits)
        data,receipt=run_sidecar(self.runtime,self.sidecar,job,{'profile':PROFILE,'operation':'inspect','drawing':'project/'+project.entry,
                              **{key:'project/'+name for key,name in databases.items()}},authorization=authorization,limits=limits)
        project.check_current(limits)
        return inventory(project,data,copied_root=copy),receipt

    def edit(self,staged,destination,edits,authorization,limits=TdLimits()):
        validate_project_edits(staged,edits)
        if not self.probe()['available']:reject('licensed_runtime_prerequisite')
        if not isinstance(authorization,HostAuthorization):reject('td_authorization')
        authorization.validate(staged.original.drawing_hash,sha256(self.sidecar.read_bytes()).hexdigest())
        if staged.report['diagnostics']:reject('td_dependency_or_contract_hold')
        if any(r['status']=='retained-opaque' and r['kind'] in {'LogicObjects','CaseSets'} for r in staged.report['records']):reject('td_opaque_logic_edit')
        before=staged.inventory
        normalized_before=normalize_dependencies(before,staged.copied_root or staged.original.root,staged.original)
        bindings={('thermal_database' if key=='thermal_properties' else 'optical_database'):name for key,name in normalized_before['dependency_paths'].items() if name}
        validate_databases(staged.original,bindings)
        job,copy=prepare_job(staged.original,destination,limits)
        data,receipt=run_sidecar(self.runtime,self.sidecar,job,{'profile':PROFILE,'operation':'edit','drawing':'project/'+staged.original.entry,'edits':edits,
                                 **{key:'project/'+name for key,name in bindings.items()}},authorization=authorization,limits=limits)
        normalized_after=normalize_dependencies(data,copy,staged.original)
        verify_edited_inventory(normalized_before,normalized_after,edits)
        # A separate process and fresh TD instance must read the saved derivative.
        derivative=capture_project(copy,staged.original.entry,limits)
        reopen_auth=HostAuthorization(authorization.decision_id+'.reopen',authorization.candidate_sha256,derivative.drawing_hash,
                                     authorization.source_open_policy_sha256,'reviewed-source-copy/1')
        reopen_job,reopen_copy=prepare_job(derivative,job/'reopen',limits)
        reopened,reopen_receipt=run_sidecar(self.runtime,self.sidecar,reopen_job,{'profile':PROFILE,'operation':'inspect','drawing':'project/'+derivative.entry,
                                    **{key:'project/'+name for key,name in bindings.items()}},authorization=reopen_auth,limits=limits)
        verify_edited_inventory(normalized_before,normalize_dependencies(reopened,reopen_copy,derivative),edits)
        staged.original.check_current(limits)
        receipt.update(original_source_revision=staged.original.source_hash,derived_source_revision=derivative.source_hash,reopen_receipt=reopen_receipt)
        return inventory(derivative,reopened,copied_root=reopen_copy),receipt


def prepare_job(project,destination,limits):
    job=Path(destination).absolute()
    if job.exists() or job.resolve().is_relative_to(project.root.resolve()) or project.root.resolve().is_relative_to(job.resolve()):reject('td_requires_new_tree')
    checked_path(job.parent,job.name)
    job.mkdir()
    copy=project.copy_to(job/'project',limits)
    return job,copy


def normalize_dependencies(data,root,project):
    normalized=json.loads(encode(data));base=Path(root).absolute()
    if set(normalized['dependency_paths'])-{'thermal_properties','optical_properties'}:reject('td_dependency_contract')
    for role,path in normalized['dependency_paths'].items():
        if not path:continue
        actual=Path(path)
        if not actual.is_absolute():actual=base/actual
        try:name=actual.absolute().relative_to(base).as_posix()
        except ValueError:reject('td_external_dependency_unresolved')
        if name not in dict(project.files):reject('td_external_dependency_unresolved')
        if actual.is_file():
            expected=dict(project.files)[name]
            with actual.open('rb') as stream:raw=stream.read(len(expected)+1)
            if raw!=expected:reject('td_dependency_modified')
        normalized['dependency_paths'][role]=name
    return normalized


def validate_databases(project,databases):
    if not isinstance(databases,dict) or set(databases)-{'thermal_database','optical_database'}:reject('td_database_fields')
    for key,name in databases.items():
        path_name(name)
        if name not in dict(project.files) or Path(name).suffix.lower()!=('.tdp' if key=='thermal_database' else '.rco'):reject('td_database_binding')
    return databases


def verify_edited_inventory(before,after,edits):
    """All unrequested semantic fields must survive the source-tool save/reopen."""
    mapping={'Node':'Nodes','Conductor':'Conductors','HeatLoad':'HeatLoads','Rectangle':'Rectangles','ThermoProps':'ThermoPropss','OpticalProps':'OpticalPropss'}
    expected=json.loads(encode(before))
    for edit in validate_edits(edits):
        entities=expected['collections'].get(mapping[edit['kind']],[])
        key='Name' if edit['kind'] in {'ThermoProps','OpticalProps'} else 'Handle'
        matches=[e for e in entities if str(e.get(key,'')).casefold()==edit['handle'].casefold()]
        if len(matches)!=1:reject('td_edit_source_identity')
        old=matches[0].get(edit['field'])
        if isinstance(old,dict) and set(old)=={'dimension','si_value'}:old['si_value']=edit['value']
        elif type(old) in (int,float):matches[0][edit['field']]=edit['value']
        else:reject('td_edit_source_type')
    # External DB path identity may change only through explicit fixture mapping;
    # no incidental geometry, units, side, property or case change is accepted.
    if encode(expected)!=encode(after):reject('td_export_semantics_changed')
    return True


def validate_project_edits(staged,edits):
    collections={'Node':'Nodes','Conductor':'Conductors','HeatLoad':'HeatLoads','Rectangle':'Rectangles','ThermoProps':'ThermoPropss','OpticalProps':'OpticalPropss'}
    data=staged.inventory
    for edit in validate_edits(edits):
        kind=edit['kind'];field=edit['field'];key='Name' if kind in {'ThermoProps','OpticalProps'} else 'Handle'
        matches=[e for e in data['collections'].get(collections[kind],[]) if str(e.get(key,'')).casefold()==edit['handle'].casefold()]
        if len(matches)!=1:reject('td_edit_source_identity')
        entity=matches[0];expression=entity.get(field+'Exp')
        if expression:
            value=expression.get('Value','') if isinstance(expression,dict) else None
            if not isinstance(value,str) or value.strip():reject('td_dynamic_field_edit')
        if any(entity.get(flag,0)!=0 for flag in ('Var'+field,'UseVar'+field)):reject('td_table_field_edit')
        if kind in {'Node','Conductor','HeatLoad'}:
            row=next((r for r in staged.report['records'] if r['kind']==kind and r['source_id'].endswith(':'+edit['handle'])),None)
            if row is None or row['status']!='native-reconstructed':reject('td_unmapped_entity_edit')
    return edits
