# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned RcNode payload version 22 reader and guarded scalar edits.

Payload version is a serialization profile, not an inferred TD product release.
Geometry-derived capacitance, clones, variable expressions and source logic
remain separately classified. Parsing them never grants native execution.
"""
from dataclasses import dataclass,field
from hashlib import sha256
import math
from .core import reject
from .dwg_bits import scalar_record
from .td_filer import Filer,expression_is_constant,logic_is_empty

PROFILE='td-rcnode-v22/1'


def _one(row,key,default=None):
    values=[v for k,v in row if k==key]
    if not values:return default
    if len(values)!=1:reject('td_node_ambiguous_common_field')
    return values[0]


def common_handles(filer,standard):
    """Verify every common handle against the separately decoded field stream."""
    fields=[]
    if _one(standard,'entmode')==0:fields.append(('ownerhandle',_one(standard,'ownerhandle')))
    fields.extend(('reactor',value) for value in _one(standard,'reactors',[]))
    if not _one(standard,'is_xdic_missing',0):fields.append(('xdicobjhandle',_one(standard,'xdicobjhandle')))
    fields.append(('layer',_one(standard,'layer')))
    for flag,name in (('ltype_flags','ltype'),('material_flags','material'),('shadow_flags','shadow'),('plotstyle_flags','plotstyle')):
        if _one(standard,flag,0)==3:fields.append((name,_one(standard,name)))
    for flag,name in (('has_full_visualstyle','full_visualstyle'),('has_face_visualstyle','face_visualstyle'),('has_edge_visualstyle','edge_visualstyle')):
        if _one(standard,flag,0):fields.append((name,_one(standard,name)))
    result={}
    for name,value in fields:
        if not isinstance(value,list) or len(value) not in {3,4}:reject('td_node_common_handle')
        decoded=filer.handle()
        expected=value[-1] if len(value)==4 else value[2]
        if len(value)==3 and value[0] in {6,8,10,12}:
            expected=filer.row['handle']+(1 if value[0]==6 else -1 if value[0]==8 else value[2] if value[0]==10 else -value[2])
        if decoded['target']!=expected:reject('td_node_common_handle_mismatch')
        result.setdefault(name,[]).append(decoded)
    return result


@dataclass(frozen=True)
class NodePayload:
    fields:dict=field(repr=False)
    spans:dict=field(repr=False)
    record:dict=field(repr=False)
    standard:object=field(repr=False)

    @property
    def report(self):
        f=self.fields
        return {'profile':PROFILE,'handle':self.record['handle'],'payload_decoded':True,
                'source_logic_present':not logic_is_empty(f['logic']),
                'variable_expressions':sum(not expression_is_constant(x) for x in (f['mass_expression'],f['temperature_expression'],f['selector_expression'])),
                'association_references':len(f['associations']),'qualified':False,
                'native_ready':False,'scope':'Complete node payload structure; full-model semantics and closure require separate assessment'}

    def edited_record(self,changes,*,temperature_unit='K'):
        if not isinstance(changes,dict) or not changes or set(changes)-{'initial_temperature','mass_value'}:reject('td_node_edit_fields')
        f=self.fields
        if (not logic_is_empty(f['logic']) or not expression_is_constant(f['temperature_expression'])
                or not expression_is_constant(f['mass_expression']) or not expression_is_constant(f['selector_expression'])
                or f['temperature_mode']!=0 or f['time_table']):reject('td_node_dynamic_edit')
        for name,value in changes.items():
            if type(value) not in (int,float) or not math.isfinite(value):reject('td_node_edit_range')
            if name=='mass_value' and value<0:reject('td_node_edit_range')
            if name=='initial_temperature':
                from fcst_contracts import BUNDLE
                if not isinstance(temperature_unit,str) or temperature_unit not in BUNDLE['units'] or BUNDLE['units'][temperature_unit][0]!='temperature':reject('td_node_temperature_unit')
                _,scale,offset=BUNDLE['units'][temperature_unit]
                if value*scale+offset<=0:reject('td_node_edit_range')
        row=scalar_record(self.record,self.spans,changes);raw=bytes.fromhex(row['data']);after=decode_node(row,self.standard)
        expected={**f,**changes}
        if after.fields!=expected:reject('td_node_edit_reopen_mismatch')
        return row,{'profile':PROFILE,'before_sha256':sha256(bytes.fromhex(self.record['data'])).hexdigest(),
                    'after_sha256':sha256(raw).hexdigest(),'changed_fields':sorted(changes),
                    'bit_length_preserved':row['bits']==self.record['bits'],'qualified':False}


def decode_node(row,standard):
    filer=Filer(row);b=filer.data;filer.version(22)
    f={'basis':tuple(b.point() for _ in range(4)),'submodel':filer.text(),'identifier':b.bl(),
       'node_type':b.bl(),'mass_value':filer.number('mass_value'),
       'initial_temperature':filer.number('initial_temperature'),'temperature_mode':b.bl(),'material':filer.text()}
    if not f['submodel'] or f['identifier']<=0 or f['node_type'] not in {0,1,2,3}:reject('td_node_identity_or_type')
    counts=[filer.count()];f['use_material']=bool(b.take(1));counts.append(filer.count())
    # These three serialized switches are retained without inventing meanings
    # from one observed drawing. They are not accepted as native solver policy.
    f['source_switches']=tuple(bool(b.take(1)) for _ in range(3))
    f['time_table']=tuple((b.bd(),b.bd()) for _ in range(filer.count()))
    f['time_table_mode']=b.bl();counts.append(filer.count());f['display_scale']=b.bd()
    f['mass_expression']=filer.expression();f['temperature_expression']=filer.expression()
    f['comment']=filer.text();f['mass_volume_type']=b.bl();f['selector_mode']=b.bl();f['selector_expression']=filer.expression()
    f['source_selector']=b.bl();f['source_flag']=bool(b.take(1));f['logic']=filer.logic()
    f['offsets']=tuple(b.bd() for _ in range(3))
    f['common_handles']=common_handles(filer,standard)
    f['connections']=tuple(filer.handle() for _ in range(counts[0]))
    f['associations']=tuple(filer.handle() for _ in range(counts[1]))
    f['additional_connections']=tuple(filer.handle() for _ in range(counts[2]));f['parent']=filer.handle()
    filer.finish()
    return NodePayload(f,dict(filer.spans),dict(row),standard)
