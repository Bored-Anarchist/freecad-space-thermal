# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned analytic serialization records, without acquired model fields or bytes."""
from copy import deepcopy
from fcst_exchange.td_surface import ATTRIBUTE_LAYOUT,SOLID_LAYOUT


def expression():
    return {'selectors':(-1,0,0),'text':'','alternate':'',
            'table':{'column_a':(),'column_b':(),'enabled':()},'mode':0,'dimension':-1,'dimensional':False,
            'dimension_table':{'column_a':(),'column_b':(),'enabled':()}}


def mesh():
    return {'values':(1,2,3,4,5,6),'selectors':(0,1,2),'expressions':tuple(expression() for _ in range(6))}


def value(kind):
    if kind=='integer':return 2
    if kind=='double':return 1.25
    if kind=='flag':return False
    if kind=='text':return 'OWNED surface \u03b1'
    if kind=='expression':return expression()
    if kind=='breakdown':return {'mode':0,'intervals':2,'boundaries':(0,.5,1),'expression':expression()}
    if kind=='mesh_controls':return mesh()
    if kind=='advection':return {'selectors':(1,2),'values':(.25,.75),'expressions':(expression(),)}
    if kind in {'handles','texts','expressions','integer_lists','text_pair_lists'}:return ()
    if kind=='integers':return (0,1,2)
    if kind=='doubles':return (.25,.5,.75)
    if kind=='text_pairs':return (('OWNED key','OWNED value'),)
    raise AssertionError('unhandled owned fixture field')


def groups(layout):
    return {name:value(kind) if count==1 else tuple(value(kind) for _ in range(count)) for name,kind,count in layout}


def rectangle_fields():
    attrs=groups(ATTRIBUTE_LAYOUT)
    attrs.update(groups=(('MAIN',1),),legacy_names=('',''),legacy_selectors=(0,0),names=('OWNED A','OWNED B',''))
    attrs['name_lists']=(('OWNED first','OWNED second'),())
    attrs['expressions_a'][0]['text']='SOURCE_EXPRESSION';attrs['flag_j']=True
    return {'serialized_parameters':(0,1,0,2,0,0),'origin':(1,2,3),'axes':((1,0,0),(0,1,0),(0,0,1)),
            'attributes':attrs,'additional_parameters':(0,0,0,0,0,0),'mesh_controls':mesh(),
            'parameter_expressions':tuple(expression() for _ in range(12)),'entity_flags':1}


def brick_fields():
    attrs=groups(SOLID_LAYOUT);attrs['parameter_expressions']=tuple(expression() for _ in range(12))
    attrs['name_maps']=((('OWNED A','OWNED B'),),())
    attrs['index_lists']=((1,2),(3,4,5));attrs['face_names']=tuple((f'OWNED face {i}',) for i in range(6))
    return {'serialized_parameters':(0,1,0,2,0,3,0,0,0,0,0,0),'origin':(1,2,3),'axes':((1,0,0),(0,1,0),(0,0,1)),
            'attributes':attrs}
