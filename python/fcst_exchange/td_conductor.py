# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned version-22 RcConductor structural codec; inactive law data is retained."""
from dataclasses import dataclass,field
from hashlib import sha256
import math
from .core import reject
from .dwg_bits import scalar_record
from .td_filer import Filer,expression_is_constant,logic_is_empty
from .td_node import common_handles

PROFILE='td-rcconductor-v22/1'


@dataclass(frozen=True)
class ConductorPayload:
    fields:dict=field(repr=False)
    spans:dict=field(repr=False)
    record:dict=field(repr=False)
    standard:object=field(repr=False)

    @property
    def report(self):
        return {'profile':PROFILE,'handle':self.record['handle'],'payload_decoded':True,
                'source_logic_present':not logic_is_empty(self.fields['logic']),
                'native_ready':False,'qualified':False,
                'scope':'Complete conductor payload structure; law and model closure require separate assessment'}

    def edited_record(self,changes):
        f=self.fields
        if not isinstance(changes,dict) or set(changes)!={'value'}:reject('td_conductor_edit_fields')
        expressions=(f['expression'],f['extra_expression'],*f['law_expressions'],*(x[1] for x in f['extra_values']))
        if (not logic_is_empty(f['logic']) or not all(expression_is_constant(x) for x in expressions)
                or f['mode']!=0 or f['law_selectors']!=(0,1) or f['selector_e']!=1 or f['selector_f']!=1 or f['selector_g']!=0
                or f['extra_text'] or any(f['selectors_a']) or f['selector_b'] or f['selector_c']
                or any(f['arrays_a']) or any(f['arrays_b'])):reject('td_conductor_dynamic_or_nonconstant_law')
        value=changes['value']
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:reject('td_conductor_edit_range')
        row=scalar_record(self.record,self.spans,changes);raw=bytes.fromhex(row['data']);after=decode_conductor(row,self.standard)
        if after.fields!={**f,**changes}:reject('td_conductor_edit_reopen_mismatch')
        return row,{'profile':PROFILE,'changed_fields':['value'],'bit_length_preserved':row['bits']==self.record['bits'],'qualified':False,
                    'before_sha256':sha256(bytes.fromhex(self.record['data'])).hexdigest(),'after_sha256':sha256(raw).hexdigest()}


def decode_conductor(row,standard):
    filer=Filer(row);b=filer.data
    f={'common_handles':common_handles(filer,standard)};filer.version(22)
    f.update(submodel=filer.text(),identifier=b.bl(),value=filer.number('value'),mode=b.bl(),material=filer.text(),comment=filer.text())
    if not f['submodel'] or f['identifier']<0:reject('td_conductor_identity')
    f['selectors_a']=tuple(b.bl() for _ in range(5));f['arrays_a']=(filer.doubles(),filer.doubles())
    f['selector_b']=b.bl();f['expression']=filer.expression();f['selector_c']=b.bl()
    f['arrays_b']=(filer.doubles(),filer.doubles());f['law_selectors']=(b.bl(),b.bl())
    f['law_values']=tuple(b.bd() for _ in range(11));f['law_expressions']=tuple(filer.expression() for _ in range(11))
    f['source_identifier']=b.bl();f['logic']=filer.logic();f['selector_e']=b.bl();f['extra_expression']=filer.expression();f['extra_text']=filer.text()
    f['from']=filer.connections();f['to']=filer.connections()
    f['extra_values']=tuple((b.bd(),filer.expression()) for _ in range(4))
    f['selector_f']=b.bl();f['selector_g']=b.bl();filer.finish()
    return ConductorPayload(f,dict(filer.spans),dict(row),standard)
