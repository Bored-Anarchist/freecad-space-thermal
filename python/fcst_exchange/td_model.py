# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independent, closed TD constant-network to canonical-model conversion.

Structural decoding alone is insufficient. Every thermal field must match the
declared constant profile, and every connection must resolve to a decoded node.
Source units are supplied explicitly; no TD release or unit system is inferred
from the DWG signature, file extension or an annotation companion.
"""
from dataclasses import dataclass,field
from hashlib import sha256
from fcst_contracts import ContractError,loads,read
from fcst_app.persistence import encode
from .core import ExchangeError,reject,target_id
from .sinda import SindaUnits
from .td_node import _one
from .td_decode import decode_drawing
from .td_writer import node_payload,conductor_payload,load_payload,template_fields

PROFILE='td-independent-network/1'
DRAWING_KINDS=frozenset(('BLOCK_CONTROL LAYER_CONTROL STYLE_CONTROL LTYPE_CONTROL VIEW_CONTROL UCS_CONTROL '
    'VPORT_CONTROL APPID_CONTROL DIMSTYLE_CONTROL DICTIONARY DICTIONARYWDFLT PLACEHOLDER LAYER STYLE APPID '
    'LTYPE MLINESTYLE BLOCK_HEADER BLOCK ENDBLK VPORT LAYOUT').split())


def identity_key(row):
    kind=row['kind']
    if kind=='submodel':return kind,row['submodel']
    if kind not in {'node','conductor','load'}:reject('td_native_annotation_identity')
    value=row['handle']
    if isinstance(value,str):
        import re
        if not re.fullmatch(r'[1-9][0-9]{0,19}',value):reject('td_native_annotation_identity')
        value=int(value)
    elif type(value) is float:
        if not value.is_integer() or not 1<=value<=9007199254740991:reject('td_native_annotation_identity')
        value=int(value)
    if type(value) is not int or not 1<=value<=18446744073709551615:reject('td_native_annotation_identity')
    return kind,value


@dataclass(frozen=True)
class Conversion:
    model_bytes:bytes|None=field(repr=False)
    identities:tuple=field(repr=False)
    diagnostics:tuple

    @property
    def model(self):return loads(self.model_bytes) if self.model_bytes is not None else None

    @property
    def report(self):
        return {'profile':PROFILE,'native_ready':self.model_bytes is not None,
                'mapped_entities':len(self.identities) if self.model_bytes is not None else 0,
                'diagnostics':list(self.diagnostics),'vendor_runtime_required':False,'qualified':False,
                'scope':'Canonical constant network only; production solving and full TD qualification remain separate'}

    def require_native(self):
        if self.model_bytes is None:reject('td_native_semantic_or_dependency_hold')
        return self.model


def _connection(values,nodes):
    if len(values)!=1:reject('td_native_connection_cardinality')
    value=values[0]
    if value['kind']!='entity-node' or value['index']!=1:reject('td_native_connection_selection')
    handle=value['reference']['target']
    if handle not in nodes:reject('td_native_missing_node')
    return handle


def _profile_equal(actual,expected):
    actual=dict(actual);actual.pop('common_handles');expected=dict(expected);expected.pop('common_handles')
    def normalized(value):
        if isinstance(value,dict):
            if set(value)=={'code','value','target'}:return {'target':value['target']}
            return {k:normalized(v) for k,v in value.items()}
        if isinstance(value,(tuple,list)):return tuple(normalized(v) for v in value)
        return value
    if normalized(actual)!=normalized(expected):reject('td_native_nonconstant_or_unmapped_fields')


def convert_network(snapshot,units,source_revision,*,closure_holds=()):
    diagnostics=[{'code':code} for code in closure_holds];identities=[];entities=[];entries=[]
    if not isinstance(units,SindaUnits):
        return Conversion(None,(),tuple(diagnostics+[{'code':'td_native_explicit_units_required'}]))
    inventory=decode_drawing(snapshot);payloads=sorted((p for p in inventory.payloads if p.report['payload_decoded']),key=lambda p:p.record['handle'])
    decoded={p.record['handle'] for p in payloads};all_handles={r['handle'] for r in snapshot.native['objects']}
    classes={c['number']:c for c in snapshot.native['classes']}
    standards={_one(row,'handle')[2]:row for row in _one(snapshot.standard,'OBJECTS')}
    for row in snapshot.native['objects']:
        if (row['handle'] not in decoded and row['kind'] not in DRAWING_KINDS) or row['rest_bits']:
            diagnostics.append({'code':'td_native_required_object_unmapped','handle':row['handle']})
        if row['type']>=500 and row['handle'] not in decoded and classes[row['type']]['cppname'] not in {'AcDbDictionaryWithDefault','AcDbPlaceHolder','AcDbLayout'}:
            diagnostics.append({'code':'td_native_required_class_unmapped','handle':row['handle']})
        if _one(standards[row['handle']],'eed',[]):diagnostics.append({'code':'td_native_extended_data_unmapped','handle':row['handle']})
    if any(r['byte_length'] for r in snapshot.native['opaque_sections']):diagnostics.append({'code':'td_native_datastorage_unmapped'})
    if snapshot.native['read_errors'] & ~4:diagnostics.append({'code':'td_native_container_warning'})
    nodes={p.record['handle']:p for p in payloads if 'initial_temperature' in p.fields}
    handles=[p.record['handle'] for p in payloads];indexes={h:i+1 for i,h in enumerate(handles)}
    node_keys=set();conductor_keys=set();groups={};node_ids={h:target_id((PROFILE,'node',str(h))) for h in nodes}
    def add(kind,key,values,source):
        identifier=node_ids[key] if kind=='node' else target_id((PROFILE,kind,str(key)))
        entities.append({'id':identifier,'kind':kind,**values})
        entries.append({'namespace':'TD.DWG','handle':kind+'.'+str(key),'entity_id':identifier})
        identities.append({'entity_id':identifier,'kind':kind,**source});return identifier
    for h,p in nodes.items():
        name=p.fields['submodel']
        if name not in groups and any(other.casefold()==name.casefold() for other in groups):diagnostics.append({'code':'td_native_submodel_identity_collision'})
        if name not in groups:
            digest=sha256(name.encode('utf-8')).hexdigest()[:32]
            groups[name]=add('submodel',digest,{'label':name},{'submodel':name})
    for p in payloads:
        f=p.fields;h=p.record['handle']
        try:
            if any(v['target'] and v['target'] not in all_handles for values in f['common_handles'].values() for v in values):reject('td_native_common_reference_closure')
            if set(f['common_handles'])-{'layer','ownerhandle'}:reject('td_native_common_dependency_unmapped')
            if 'initial_temperature' in f:
                if f['node_type'] not in {0,1,2}:reject('td_native_clone_unmapped')
                key=(f['submodel'].casefold(),f['identifier'])
                if key in node_keys:reject('td_native_node_identity_collision')
                node_keys.add(key);classification={0:'capacitive',1:'algebraic',2:'prescribed'}[f['node_type']]
                expected=node_payload(f['submodel'],f['identifier'],f['initial_temperature'],f['mass_value'],classification,f['comment'])
                _profile_equal(f,template_fields(expected,handles,handle=h))
                values={'submodel_id':groups[f['submodel']],'classification':classification,
                        'temperature':units.quantity(f['initial_temperature'],'temperature'),
                        'capacity':units.quantity(f['mass_value'],'capacity')}
                kind='node'
            elif 'from' in f:
                a,b=(_connection(f[k],nodes) for k in ('from','to'))
                key=(f['submodel'].casefold(),f['identifier'])
                if key in conductor_keys:reject('td_native_conductor_identity_collision')
                conductor_keys.add(key)
                if f['submodel'] not in groups:reject('td_native_conductor_submodel')
                expected=conductor_payload(f['submodel'],f['identifier'],f['value'],indexes[a],indexes[b],f['comment'])
                _profile_equal(f,template_fields(expected,handles,handle=h));kind='conductor'
                values={'from_node_id':node_ids[a],'to_node_id':node_ids[b],'conductance':units.quantity(f['value'],'conductance')}
            else:
                a=_connection(f['connections'],nodes);expected=load_payload(f['value'],indexes[a],f['comment'])
                wanted=template_fields(expected,handles,handle=h);wanted['name']=f['name']
                _profile_equal(f,wanted);kind='load'
                values={'node_id':node_ids[a],'power':units.quantity(f['value'],'power')}
            label=f['comment'] or (f['name'] if kind=='load' else '')
            if label:values['label']=label
            add(kind,h,values,{'handle':h})
        except ExchangeError as error:diagnostics.append({'code':error.code,'handle':h})
    if not nodes:diagnostics.append({'code':'td_native_network_required'})
    model={'contract_version':'1.0.0','minimum_reader':'1.0.0','project_id':target_id((PROFILE,'project',source_revision)),
           'revision':0,'entities':entities,'source_maps':[{'id':target_id((PROFILE,'map',source_revision)),
           'version':'1.0.0','source_revision':source_revision,'source_tool':'Thermal Desktop DWG',
           'source_version':'RcNode22-RcConductor22-RcHeatLoad17; product release unknown','entries':entries}],
           'mappings':[],'attachments':[],'assumptions':['Explicit source units; closed constant-network serialization profiles'],
           'limitations':['Full TD/source-version, owned-engine and paired ESATAN qualification pending'],
           'audit':{'timestamp':'source-import'},'gui':{'selection':[]}}
    if not diagnostics:
        try:model=read('model',loads(encode(model)))
        except ContractError:diagnostics.append({'code':'td_native_model_contract'})
    return Conversion(encode(model) if not diagnostics else None,tuple(identities),tuple(diagnostics))


def equivalent_entities(expected,actual,mapping,*,annotations=False):
    """Check every thermal field/reference; permit labels only as annotations."""
    index={e['id']:e for e in actual['entities']}
    if set(mapping)!=set(e['id'] for e in expected['entities']) or set(mapping.values())!=set(index):reject('td_native_entity_inventory')
    for entity in expected['entities']:
        other=index[mapping[entity['id']]]
        if entity['kind']!=other['kind']:reject('td_native_entity_kind')
        for key in (set(entity)|set(other))-{'id'}:
            if annotations and key=='label':continue
            a,b=entity.get(key),other.get(key)
            if key.endswith('_id') and a is not None:a=mapping[a]
            if isinstance(a,dict) and set(a)=={'value','unit'}:
                import math
                if not isinstance(b,dict) or a['unit']!=b['unit'] or abs(a['value']-b['value'])>4*max(math.ulp(a['value']),math.ulp(b['value'])):reject('td_native_quantity_mismatch')
            elif a!=b:reject('td_native_field_or_reference_mismatch')


def restore_annotations(conversion,canonical,receipt):
    """Restore owned metadata only after verifying it against decoded semantics."""
    if conversion.model_bytes is None:return conversion
    from copy import deepcopy
    from .sinda_writer import _model
    try:
        canonical=_model(canonical);rows=receipt['identities']
        actual={identity_key(r):r['entity_id'] for r in conversion.identities}
        if not isinstance(rows,list) or len(rows)!=len(actual):reject('td_native_annotation_inventory')
        mapping={};seen=set()
        for row in rows:
            key=identity_key(row)
            if key in seen or key not in actual or row['entity_id'] in mapping:reject('td_native_annotation_identity')
            seen.add(key);mapping[row['entity_id']]=actual[key]
        equivalent_entities(canonical,conversion.model,mapping,annotations=True)
        inverse={v:k for k,v in mapping.items()};model=deepcopy(canonical)
        source=deepcopy(conversion.model['source_maps'][0])
        for entry in source['entries']:entry['entity_id']=inverse[entry['entity_id']]
        model['source_maps']=[s for s in model['source_maps'] if s['id']!=source['id']]+[source]
        model=read('model',loads(encode(model)))
        identities=tuple({**r,'entity_id':inverse[r['entity_id']]} for r in conversion.identities)
        return Conversion(encode(model),identities,())
    except (ExchangeError,ContractError,KeyError,TypeError,ValueError):
        return Conversion(None,(),({'code':'td_native_annotation_semantics_mismatch'},))
