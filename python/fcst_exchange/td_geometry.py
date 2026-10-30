# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned RcRectangle v7 serialization, with an explicit partial fallback.

The serialization sentinel is a format discriminator, never a model parameter.
No units, surface properties, mesh or thermal assignments are inferred here.
"""
from dataclasses import dataclass,field
from hashlib import sha256
import math
from .core import reject,ExchangeError
from .td_filer import Filer
from .td_node import common_handles
from .td_surface import (read_attributes,read_mesh_controls,write_attributes,write_mesh_controls,write_expression,
    read_solid_attributes,write_solid_attributes)

SENTINEL=float.fromhex('0x1.f07c18386f74ep+295')


@dataclass(frozen=True)
class RectangleEnvelope:
    fields:dict=field(repr=False)
    record:dict=field(repr=False)
    standard:object=field(repr=False)

    @property
    def report(self):
        return {'profile':'td-rcrectangle-envelope-v7/1','handle':self.record['handle'],
                'payload_decoded':False,'geometric_envelope_decoded':True,
                'native_ready':False,'qualified':False,
                'scope':'Six serialized geometric parameters, origin and basis; thermal attributes and units unresolved'}

    def edited_record(self,changes):reject('td_rectangle_thermal_attributes_unmapped')


@dataclass(frozen=True)
class RectanglePayload:
    fields:dict=field(repr=False)
    spans:dict=field(repr=False)
    record:dict=field(repr=False)
    standard:object=field(repr=False)

    @property
    def report(self):
        return {'profile':'td-rcrectangle-v7-attributes54/1','handle':self.record['handle'],
                'payload_decoded':True,'geometric_envelope_decoded':True,'thermal_semantics_decoded':False,
                'native_ready':False,'qualified':False,
                'scope':'Complete serialized rectangle, surface attributes and mesh controls; physical selector mappings and mesh regeneration pending'}

    def edited_record(self,changes):
        return _edit_geometry(self,changes,decode_rectangle_complete,6,self.fields['parameter_expressions'])


def _edit_geometry(payload,changes,decoder,count,expressions):
    from .dwg_bits import scalar_record
    from .td_filer import expression_is_constant
    if (not isinstance(changes,dict) or not changes or set(changes)!={'serialized_parameters'}
            or not isinstance(changes['serialized_parameters'],(list,tuple)) or len(changes['serialized_parameters'])!=count):reject('td_geometry_edit_shape')
    values=tuple(changes['serialized_parameters'])
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):reject('td_geometry_edit_number')
    if len(expressions)!=12 or any(not expression_is_constant(e) for e in expressions):reject('td_geometry_dynamic_edit')
    selected={f'parameter_{i}':v for i,v in enumerate(values) if v!=payload.fields['serialized_parameters'][i]}
    if not 1<=len(selected)<=2:reject('td_geometry_edit_field_limit')
    row=scalar_record(payload.record,payload.spans,selected);after=decoder(row,payload.standard)
    if after.fields!={**payload.fields,'serialized_parameters':values}:reject('td_geometry_edit_reopen')
    return row,{'profile':payload.report['profile'],'changed_fields':sorted(selected),
                'before_sha256':sha256(bytes.fromhex(payload.record['data'])).hexdigest(),
                'after_sha256':sha256(bytes.fromhex(row['data'])).hexdigest(),
                'bit_length_preserved':row['bits']==payload.record['bits'],'native_ready':False,'qualified':False,
                'scope':'Serialized parameter edit only; no mesh regeneration or thermal qualification'}

def _prefix(filer,standard):
    b=filer.data
    if b.bd()!=SENTINEL:reject('td_rectangle_profile_marker')
    filer.version(7)
    return {'serialized_parameters':tuple(filer.number(f'parameter_{i}') for i in range(6)),
            'origin':b.point(),'axes':tuple(b.point() for _ in range(3)),
            'common_handles':common_handles(filer,standard)}


def decode_rectangle_complete(row,standard):
    filer=Filer(row);fields=_prefix(filer,standard);b=filer.data
    fields['attributes']=read_attributes(filer)
    fields['additional_parameters']=tuple(b.bd() for _ in range(6))
    fields['mesh_controls']=read_mesh_controls(filer)
    fields['parameter_expressions']=tuple(filer.expression() for _ in range(filer.count()))
    fields['entity_flags']=b.bl();filer.finish()
    return RectanglePayload(fields,dict(filer.spans),dict(row),standard)


def decode_rectangle(row,standard):
    try:return decode_rectangle_complete(row,standard)
    except ExchangeError as error:limitation=error.code
    filer=Filer(row);b=filer.data;fields=_prefix(filer,standard)
    if b.position==b.end:reject('td_rectangle_missing_thermal_attributes')
    fields['opaque_data_range']=(b.position,b.end)
    fields['opaque_text_range']=(filer.strings.position,filer.strings.end)
    fields['opaque_handle_range']=(filer.handles.position,filer.handles.end)
    fields['complete_profile_limitation']=limitation
    return RectangleEnvelope(fields,dict(row),standard)


def rectangle_payload(fields):
    """Serialize a complete declared profile from owned inputs, without a DWG."""
    from .td_writer import FilerWriter
    expected={'serialized_parameters','origin','axes','attributes','additional_parameters','mesh_controls','parameter_expressions','entity_flags'}
    if not isinstance(fields,dict) or set(fields)!=expected:reject('td_rectangle_writer_shape')
    if len(fields['serialized_parameters'])!=6 or len(fields['axes'])!=3 or len(fields['additional_parameters'])!=6:reject('td_rectangle_writer_shape')
    f=FilerWriter();b=f.data;b.bd(SENTINEL);b.bl(7)
    for value in fields['serialized_parameters']:b.bd(value)
    b.point(fields['origin'])
    for axis in fields['axes']:b.point(axis)
    write_attributes(f,fields['attributes'])
    for value in fields['additional_parameters']:b.bd(value)
    write_mesh_controls(f,fields['mesh_controls'])
    if len(fields['parameter_expressions'])>10000:reject('td_rectangle_writer_limit')
    b.bl(len(fields['parameter_expressions']))
    for expression in fields['parameter_expressions']:write_expression(f,expression)
    b.bl(fields['entity_flags']);return f.result(4)


@dataclass(frozen=True)
class BrickPayload(RectanglePayload):
    @property
    def report(self):
        return {'profile':'td-rcfdbrick-v21/1','handle':self.record['handle'],'payload_decoded':True,
                'geometric_envelope_decoded':True,'thermal_semantics_decoded':False,'native_ready':False,'qualified':False,
                'scope':'Complete serialized brick, subdivision, material/face fields, mesh controls and advection; physical selector bindings and mesh regeneration pending'}

    def edited_record(self,changes):
        return _edit_geometry(self,changes,decode_brick,12,self.fields['attributes']['parameter_expressions'])


def decode_brick(row,standard):
    f=Filer(row);b=f.data;f.version(21)
    fields={'serialized_parameters':tuple(f.number(f'parameter_{i}') for i in range(12)),
            'origin':b.point(),'axes':tuple(b.point() for _ in range(3)),
            'common_handles':common_handles(f,standard),'attributes':read_solid_attributes(f)}
    f.finish();return BrickPayload(fields,dict(f.spans),dict(row),standard)


def brick_payload(fields):
    from .td_writer import FilerWriter
    if not isinstance(fields,dict) or set(fields)!={'serialized_parameters','origin','axes','attributes'}:reject('td_solid_writer_shape')
    if len(fields['serialized_parameters'])!=12 or len(fields['axes'])!=3:reject('td_solid_writer_shape')
    f=FilerWriter();b=f.data;b.bl(21)
    for value in fields['serialized_parameters']:b.bd(value)
    b.point(fields['origin'])
    for axis in fields['axes']:b.point(axis)
    write_solid_attributes(f,fields['attributes']);return f.result(5)
