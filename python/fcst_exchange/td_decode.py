# SPDX-License-Identifier: MIT OR Apache-2.0
"""Direct typed TD inventory. Undecoded objects remain explicit model holds."""
from dataclasses import dataclass,field
from collections import Counter
from .core import ExchangeError
from .dwg_native import _one
from .td_node import decode_node
from .td_conductor import decode_conductor
from .td_load import decode_load
from .td_geometry import decode_rectangle,decode_brick

DECODERS={'RcNode':decode_node,'RcConductor':decode_conductor,'RcHeatLoad':decode_load,'RcRectangle':decode_rectangle,'RcFdBrick':decode_brick}
GEOMETRY_CLASSES={'RcRectangle':'RCRECTANGLE','RcFdBrick':'RCTD_FDBRICK'}


@dataclass(frozen=True)
class ThermalInventory:
    payloads:tuple=field(repr=False)
    records:tuple

    @property
    def report(self):
        counts=Counter(row['status'] for row in self.records)
        return {'profile':'td-typed-payloads/1','decoded_objects':counts['payload-decoded'],
                'partial_objects':counts['partial-payload'],
                'retained_objects':counts['retained-opaque']+counts['partial-payload'],'records':list(self.records),
                'native_ready':False,'qualified':False,
                'limitations':['full_model_dependency_and_semantic_closure_unqualified']}


def decode_drawing(snapshot):
    classes={c['number']:c for c in snapshot.native['classes']};names={k:c['cppname'] for k,c in classes.items()}
    standards={_one(row,'handle')[2]:row for row in _one(snapshot.standard,'OBJECTS')}
    payloads=[];records=[]
    for row in snapshot.native['objects']:
        if row['type']<500:continue
        decoder=DECODERS.get(names[row['type']]);code='td_class_profile_unmapped'
        if names[row['type']] in GEOMETRY_CLASSES and classes[row['type']]['dxfname']!=GEOMETRY_CLASSES[names[row['type']]]:
            decoder=None;code='td_geometry_class_identity_unmapped'
        if decoder is None and row['kind'] not in {'UNKNOWN_ENT','UNKNOWN_OBJ'}:continue
        if decoder:
            try:
                payload=decoder(row,standards[row['handle']]);payloads.append(payload)
                records.append({'handle':row['handle'],'status':'payload-decoded' if payload.report['payload_decoded'] else 'partial-payload',**payload.report});continue
            except ExchangeError as error:code=error.code
        records.append({'handle':row['handle'],'status':'retained-opaque','limitation':code,
                        'native_ready':False,'qualified':False})
    return ThermalInventory(tuple(payloads),tuple(records))
