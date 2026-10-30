# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned complete surface-attribute and subdivision serialization profiles.

The revision marker identifies a wire layout, not a TD product release. Numeric
selectors are retained explicitly; structural coverage does not establish their
physical meaning or qualify a thermal model.
"""
from .core import reject

ATTRIBUTE_REVISION=5.4e22


def _array(value,*,size=None,limit=10000):
    if not isinstance(value,(tuple,list)) or len(value)>limit or size is not None and len(value)!=size:reject('td_surface_array_shape')
    return value
# Ordered groups preserve every field without inventing meanings for switches
# whose physical interpretation has not yet been independently established.
ATTRIBUTE_LAYOUT=(
    ('subdivision','breakdown',2),('primary_selector','integer',1),
    ('property_names','text',2),('property_scalars','double',2),
    ('property_label','text',1),('property_value','double',1),
    ('selectors_a','integer',6),('values_a','double',6),('selectors_b','integer',2),
    ('names_b','text',2),('values_b','double',2),('names_c','text',2),('selectors_c','integer',4),
    ('name_d','text',1),('selector_d','integer',1),('references_a','handles',2),
    ('names_e','text',2),('references_b','handles',1),('selector_e','integer',1),
    ('references_c','handles',1),('name_f','text',1),('selectors_f','integer',9),
    ('values_f','double',2),('selector_g','integer',1),('expressions_a','expression',13),
    ('values_g','double',4),('expressions_b','expression',4),('selectors_h','integer',2),
    ('references_d','handles',1),('name_maps','text_pairs',2),('expressions_c','expression',2),
    ('name_lists','texts',2),('names_i','text',4),('selectors_i','integer',2),
    ('selector_j','integer',1),('expression_j','expression',1),('references_e','handles',1),
    ('flag_j','flag',1))


def read_breakdown(filer):
    filer.version(-1000);mode=filer.data.bl();count=filer.count()
    # The source stores count intervals and count+1 boundary coordinates.
    return {'mode':mode,'intervals':count,'boundaries':tuple(filer.data.bd() for _ in range(count+1)),
            'expression':filer.expression()}


def read_value(filer,kind):
    b=filer.data
    if kind=='integer':return b.bl()
    if kind=='double':return b.bd()
    if kind=='flag':return bool(b.take(1))
    if kind=='text':return filer.text()
    if kind=='expression':return filer.expression()
    if kind=='breakdown':return read_breakdown(filer)
    if kind=='handles':return tuple(filer.handle() for _ in range(filer.count()))
    if kind=='text_pairs':return tuple((filer.text(),filer.text()) for _ in range(filer.count()))
    if kind=='texts':return filer.texts()
    if kind=='integers':return filer.integers()
    if kind=='doubles':return filer.doubles()
    if kind=='expressions':return tuple(filer.expression() for _ in range(filer.count()))
    if kind=='integer_lists':return tuple(filer.integers() for _ in range(filer.count()))
    if kind=='text_pair_lists':return tuple(read_value(filer,'text_pairs') for _ in range(filer.count()))
    if kind=='mesh_controls':return read_mesh_controls(filer)
    if kind=='advection':
        filer.version(1)
        return {'selectors':filer.integers(),'values':filer.doubles(),'expressions':read_value(filer,'expressions')}
    reject('td_surface_field_kind')


def read_attributes(filer):
    b=filer.data
    fields={'groups':tuple((filer.text(),b.bl()) for _ in range(filer.count())),
            'legacy_names':tuple(filer.text() for _ in range(2)),
            'legacy_selectors':tuple(b.bl() for _ in range(2)),
            'names':tuple(filer.text() for _ in range(3))}
    if b.bd()!=ATTRIBUTE_REVISION:reject('td_surface_attribute_revision')
    for name,kind,count in ATTRIBUTE_LAYOUT:
        values=tuple(read_value(filer,kind) for _ in range(count))
        fields[name]=values[0] if count==1 else values
    return fields


def read_mesh_controls(filer):
    filer.version(3);b=filer.data
    return {'values':tuple(b.bd() for _ in range(6)),'selectors':tuple(b.bl() for _ in range(3)),
            'expressions':tuple(filer.expression() for _ in range(6))}


def write_expression(filer,record):
    if not isinstance(record,dict) or set(record)!={'selectors','text','alternate','table','mode','dimension','dimensional','dimension_table'}:reject('td_surface_expression_shape')
    b=filer.data;b.bl(5)
    for value in _array(record['selectors'],size=3):b.bl(value)
    filer.text(record['text']);filer.text(record['alternate']);write_table(filer,record['table'])
    b.bl(record['mode']);b.bl(record['dimension'])
    if type(record['dimensional']) is not bool:reject('td_surface_expression_shape')
    b.put(int(record['dimensional']),1);write_table(filer,record['dimension_table'])


def write_table(filer,record):
    if not isinstance(record,dict) or set(record)!={'column_a','column_b','enabled'}:reject('td_surface_table_shape')
    for value in record.values():_array(value)
    filer.data.bl(1);filer.integers(record['column_a']);filer.integers(record['column_b'])
    if any(type(value) not in (bool,int) or value not in (0,1) for value in record['enabled']):reject('td_surface_table_shape')
    filer.flags(record['enabled'])


def write_value(filer,kind,value):
    b=filer.data
    if kind=='integer':b.bl(value)
    elif kind=='double':b.bd(value)
    elif kind=='text':filer.text(value)
    elif kind=='flag':
        if type(value) is not bool:reject('td_surface_flag')
        b.put(int(value),1)
    elif kind=='expression':write_expression(filer,value)
    elif kind=='mesh_controls':write_mesh_controls(filer,value)
    elif kind=='advection':
        if not isinstance(value,dict) or set(value)!={'selectors','values','expressions'}:reject('td_solid_advection_shape')
        b.bl(1)
        for name,op in (('selectors','integers'),('values','doubles'),('expressions','expressions')):write_value(filer,op,value[name])
    elif kind=='breakdown':
        if not isinstance(value,dict) or set(value)!={'mode','intervals','boundaries','expression'}:reject('td_surface_breakdown_shape')
        count=value['intervals']
        if type(count) is not int or not 0<=count<=10000:reject('td_surface_breakdown_shape')
        _array(value['boundaries'],size=count+1,limit=10001)
        b.bl(-1000);b.bl(value['mode']);b.bl(count)
        for x in value['boundaries']:b.bd(x)
        write_expression(filer,value['expression'])
    elif kind in {'handles','text_pairs','texts','integers','doubles','expressions','integer_lists','text_pair_lists'}:
        if not isinstance(value,(tuple,list)) or len(value)>10000:reject('td_surface_array_limit')
        b.bl(len(value))
        for row in value:
            if kind=='handles':
                # New-file references are packet indices, never imported handles.
                if type(row) is not int or row<0:reject('td_surface_writer_reference')
                filer.references.append(row)
            elif kind=='texts':filer.text(row)
            elif kind=='integers':b.bl(row)
            elif kind=='doubles':b.bd(row)
            elif kind=='expressions':write_expression(filer,row)
            elif kind=='integer_lists':write_value(filer,'integers',row)
            elif kind=='text_pair_lists':write_value(filer,'text_pairs',row)
            else:
                if not isinstance(row,(tuple,list)) or len(row)!=2:reject('td_surface_pair_shape')
                filer.text(row[0]);filer.text(row[1])
    else:reject('td_surface_field_kind')


def write_attributes(filer,fields):
    required={'groups','legacy_names','legacy_selectors','names',*(row[0] for row in ATTRIBUTE_LAYOUT)}
    if not isinstance(fields,dict) or set(fields)!=required:reject('td_surface_attribute_shape')
    groups=_array(fields['groups']);b=filer.data
    b.bl(len(groups))
    for pair in groups:
        name,selector=_array(pair,size=2);filer.text(name);b.bl(selector)
    for name,count,kind in (('legacy_names',2,'text'),('legacy_selectors',2,'integer'),('names',3,'text')):
        for value in _array(fields[name],size=count):write_value(filer,kind,value)
    b.bd(ATTRIBUTE_REVISION)
    for name,kind,count in ATTRIBUTE_LAYOUT:
        values=(fields[name],) if count==1 else fields[name]
        if not isinstance(values,(tuple,list)) or len(values)!=count:reject('td_surface_attribute_shape')
        for value in values:write_value(filer,kind,value)


def write_mesh_controls(filer,fields):
    if not isinstance(fields,dict) or set(fields)!={'values','selectors','expressions'}:reject('td_surface_mesh_shape')
    filer.data.bl(3)
    for name,count,kind in (('values',6,'double'),('selectors',3,'integer'),('expressions',6,'expression')):
        for value in _array(fields[name],size=count):write_value(filer,kind,value)


SOLID_LAYOUT=(
    ('selector_a','integer',1),('names_a','text',3),('selector_b','integer',1),('subdivision','breakdown',3),
    ('references_a','handles',2),('name_lists_a','texts',2),('index_lists','integer_lists',1),
    ('indices_a','integers',1),('selector_c','integer',1),('indices_b','integers',1),
    ('values_a','doubles',1),('indices_c','integers',1),('references_b','handles',1),
    ('scalars_a','double',4),('selector_d','integer',1),('expressions_a','expression',4),
    ('face_expressions','expression',6),('parameter_expressions','expressions',1),
    ('indices_d','integers',1),('names_b','texts',1),('values_b','doubles',1),('expressions_b','expressions',1),
    ('indices_e','integers',1),('indices_f','integers',1),('values_c','doubles',1),('expressions_c','expressions',1),
    ('references_c','handles',1),('mesh_controls','mesh_controls',1),('names_c','texts',1),
    ('expressions_d','expressions',1),('indices_g','integers',1),('face_names','texts',6),
    ('advection','advection',1),('name_lists_d','texts',2),('name_maps','text_pair_lists',1),
    ('names_e','texts',1),('indices_h','integers',1),('selector_e','integer',1),
    ('expression_e','expression',1),('entity_flags','integer',1),('references_d','handles',1))


def read_solid_attributes(filer):
    fields={}
    for name,kind,count in SOLID_LAYOUT:
        values=tuple(read_value(filer,kind) for _ in range(count))
        fields[name]=values[0] if count==1 else values
    return fields


def write_solid_attributes(filer,fields):
    if not isinstance(fields,dict) or set(fields)!={row[0] for row in SOLID_LAYOUT}:reject('td_solid_attribute_shape')
    for name,kind,count in SOLID_LAYOUT:
        values=(fields[name],) if count==1 else fields[name]
        if not isinstance(values,(tuple,list)) or len(values)!=count:reject('td_solid_attribute_shape')
        for value in values:write_value(filer,kind,value)
