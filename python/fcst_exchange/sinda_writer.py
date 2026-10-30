# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independent canonical-to-SINDA constant-network export with verified reopen.

This writes new source, never overwrites an original or requires a vendor tool.
Every entity/field must be representable; source identity mappings accompany the
receipt. Existing-source syntax-preserving edits remain SindaAdapter.export.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import shutil
import tempfile

from fcst_contracts import BUNDLE, ContractError, loads, read
from fcst_app.persistence import encode
from .core import reject, Limits
from .export import rename_new
from .sinda import SindaAdapter, SindaUnits, PROFILE
from .vendor_paths import checked_path, path_name


FIELDS = {'submodel': {'id','kind','label'},
          'node': {'id','kind','label','submodel_id','classification','temperature','capacity'},
          'conductor': {'id','kind','label','from_node_id','to_node_id','conductance'},
          'load': {'id','kind','label','node_id','power'}}


def _model(model):
    try:
        result=read('model',loads(encode(deepcopy(model))))
    except (ContractError,ValueError,TypeError,RecursionError):
        reject('sinda_writer_model_contract')
    if result['mappings'] or result['attachments']:
        reject('sinda_writer_unmapped_associations')
    for entity in result['entities']:
        if entity['kind'] not in FIELDS or set(entity)-FIELDS[entity['kind']]:
            reject('sinda_writer_unmapped_entity_or_field')
    if not any(e['kind']=='node' for e in result['entities']):
        reject('sinda_writer_network_required')
    return result


def _number(quantity,unit):
    # read(model) normalizes quantities to the native SI dimensions first.
    dimension,scale,offset=BUNDLE['units'][unit]
    value=(quantity['value']-offset)/scale
    if not math.isfinite(value):reject('sinda_writer_number')
    return format(value,'.17g')


def render(model,units,*,limits=Limits()):
    if not isinstance(units,SindaUnits):reject('explicit_sinda_units_required')
    model=_model(model)
    if len(model['entities'])>limits.records:reject('sinda_writer_entity_limit')
    entities={e['id']:e for e in model['entities']}
    groups={e['id']:'F'+str(i+1).zfill(6) for i,e in enumerate(sorted(
        (e for e in entities.values() if e['kind']=='submodel'),key=lambda e:e['id']))}
    if len(groups)>999999:reject('sinda_writer_submodel_limit')
    if any('submodel_id' not in e for e in entities.values() if e['kind']=='node'):
        groups[None]='MAIN'
    identity={}; rows={name:{'NODE':[],'CONDUCTOR':[],'SOURCE':[]} for name in groups.values()}
    nodes=sorted((e for e in entities.values() if e['kind']=='node'),key=lambda e:e['id'])
    counters={name:0 for name in rows}
    for node in nodes:
        name=groups[node.get('submodel_id')];counters[name]+=1;number=counters[name]
        if number>2147483647:reject('sinda_writer_node_limit')
        identity[node['id']]={'kind':'node','submodel':name,'number':number}
        sign=-1 if node['classification']=='prescribed' else 1
        rows[name]['NODE'].append((node, f"{sign*number},{_number(node['temperature'],units.temperature)},{_number(node['capacity'],units.capacity)}"))
    for identifier,name in groups.items():
        if identifier is not None:identity[identifier]={'kind':'submodel','submodel':name,'number':None}
    def ref(identifier,context):
        target=identity[identifier]
        return str(target['number']) if target['submodel']==context else target['submodel']+'.'+str(target['number'])
    counters={name:0 for name in rows};load_nodes=set()
    for entity in sorted(entities.values(),key=lambda e:e['id']):
        if entity['kind']=='conductor':
            name=identity[entity['from_node_id']]['submodel'];counters[name]+=1;number=counters[name]
            identity[entity['id']]={'kind':'conductor','submodel':name,'number':number}
            line=f"{number},{ref(entity['from_node_id'],name)},{ref(entity['to_node_id'],name)},{_number(entity['conductance'],units.conductance)}"
            rows[name]['CONDUCTOR'].append((entity,line))
        elif entity['kind']=='load':
            node=entity['node_id']
            if node in load_nodes:reject('sinda_writer_multiple_loads_on_node')
            load_nodes.add(node);target=identity[node];name=target['submodel'];number=target['number']
            identity[entity['id']]={'kind':'load','submodel':name,'number':number}
            rows[name]['SOURCE'].append((entity,f"{number},{_number(entity['power'],units.power)}"))
    lines=['C FCST independent SINDA constant-network export v1']
    for name in sorted(rows):
        # Empty declared submodels still need a header so their identity survives.
        lines.append('HEADER NODE DATA, '+name)
        for section in ('NODE','CONDUCTOR','SOURCE'):
            if section!='NODE' and not rows[name][section]:continue
            if section!='NODE':lines.append('HEADER '+section+' DATA, '+name)
            for entity,line in rows[name][section]:
                lines.append('C FCST-ID '+entity['id'])
                if 'label' in entity:
                    lines.append('C FCST-LABEL '+json.dumps(entity['label'],ensure_ascii=True))
                lines.append(' '+line)
    lines.append('END OF DATA')
    raw=('\r\n'.join(lines)+'\r\n').encode('ascii')
    if len(raw)>limits.file_bytes or max(map(len,raw.splitlines()),default=0)>limits.line_bytes:
        reject('sinda_writer_byte_limit')
    return raw,identity


def _check_roundtrip(model,staged,identity):
    actual=staged.require_native(); index={e['id']:e for e in actual['entities']}
    imported={}
    for source in actual['source_maps']:
        for item in source['entries']:
            imported[(item['namespace'],item['handle'])]=item['entity_id']
    mapped={}
    for original,row in identity.items():
        number='submodel' if row['kind']=='submodel' else str(row['number'])
        key=('SINDA63.'+row['submodel'],row['kind']+'.'+number)
        if key not in imported:reject('sinda_writer_reopen_identity')
        mapped[original]=imported[key]
    expected_nodes=sum(e['kind']=='node' for e in model['entities'])
    expected_non_submodels=sum(e['kind']!='submodel' for e in model['entities'])
    if sum(e['kind']=='node' for e in index.values())!=expected_nodes or sum(e['kind']!='submodel' for e in index.values())!=expected_non_submodels:
        reject('sinda_writer_reopen_inventory')
    for entity in model['entities']:
        if entity['id'] not in mapped:reject('sinda_writer_reopen_identity')
        reopened=index[mapped[entity['id']]]
        if entity['kind']!=reopened['kind']:reject('sinda_writer_reopen_kind')
        for field,value in entity.items():
            if field in {'id','kind','label'}:continue
            if field.endswith('_id'):
                if mapped[value]!=reopened.get(field):reject('sinda_writer_reopen_reference')
            elif isinstance(value,dict) and set(value)=={'value','unit'}:
                other=reopened.get(field)
                if (not isinstance(other,dict) or value['unit']!=other['unit'] or
                        abs(value['value']-other['value'])>4*max(math.ulp(value['value']),math.ulp(other['value']))):
                    reject('sinda_writer_reopen_quantity')
            elif value!=reopened.get(field):reject('sinda_writer_reopen_field')
    return mapped


def export_model(model,units,destination,*,entry='network.sin',limits=Limits()):
    normalized=_model(model);raw,identity=render(normalized,units,limits=limits)
    entry=path_name(entry);destination=Path(destination).absolute()
    if destination.exists() or not destination.parent.is_dir():reject('sinda_writer_new_target')
    checked_path(destination.parent,destination.name)
    temporary=Path(tempfile.mkdtemp(prefix='.fcst-sinda-',dir=destination.parent))
    try:
        path=temporary/entry;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        staged=SindaAdapter(units).preview(temporary,entry,limits=limits)
        mapped=_check_roundtrip(normalized,staged,identity)
        receipt={'operation':'sinda-write-model','profile':PROFILE,'source_sha256':sha256(raw).hexdigest(),
                 'canonical_input_sha256':sha256(encode(normalized)).hexdigest(),
                 'vendor_runtime_required':False,'roundtrip_verified':True,'qualified':False,
                 'scope':'New constant node/conductor/load network; annotations retained in source comments; no geometry cases or source-tool qualification',
                 'identities':[{'entity_id':key,**row,'reimported_entity_id':mapped[key]} for key,row in sorted(identity.items())]}
        rename_new(temporary,destination)
        return receipt
    finally:
        if temporary.exists():
            if temporary.parent.resolve()!=destination.parent.resolve() or not temporary.name.startswith('.fcst-sinda-'):
                reject('sinda_writer_cleanup')
            shutil.rmtree(temporary)
