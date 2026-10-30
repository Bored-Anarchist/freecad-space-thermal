# SPDX-License-Identifier: MIT OR Apache-2.0
"""Declared RcRectangle v7 geometric envelope; thermal attributes stay opaque.

The serialization sentinel is a format discriminator, never a model parameter.
No units, surface properties, mesh or thermal assignments are inferred here.
"""
from dataclasses import dataclass,field
from .core import reject
from .td_filer import Filer
from .td_node import common_handles

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


def decode_rectangle(row,standard):
    filer=Filer(row);b=filer.data
    if b.bd()!=SENTINEL:reject('td_rectangle_profile_marker')
    filer.version(7)
    fields={'serialized_parameters':tuple(b.bd() for _ in range(6)),
            'origin':b.point(),'axes':tuple(b.point() for _ in range(3)),
            'common_handles':common_handles(filer,standard)}
    if b.position==b.end:reject('td_rectangle_missing_thermal_attributes')
    fields['opaque_data_range']=(b.position,b.end)
    fields['opaque_text_range']=(filer.strings.position,filer.strings.end)
    fields['opaque_handle_range']=(filer.handles.position,filer.handles.end)
    return RectangleEnvelope(fields,dict(row),standard)
