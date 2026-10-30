# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned RcHeatLoad payload version 17 structural reader and scalar patches."""
from dataclasses import dataclass,field
from hashlib import sha256
import math
from .core import reject
from .dwg_bits import scalar_record
from .td_filer import Filer,expression_is_constant
from .td_node import common_handles

PROFILE='td-rcheatload-v17/1'


@dataclass(frozen=True)
class LoadPayload:
    fields:dict=field(repr=False)
    spans:dict=field(repr=False)
    record:dict=field(repr=False)
    standard:object=field(repr=False)

    @property
    def report(self):
        return {'profile':PROFILE,'handle':self.record['handle'],'payload_decoded':True,
                'native_ready':False,'qualified':False,
                'scope':'Complete heat-load payload structure; distribution and model closure require separate assessment'}

    def edited_record(self,changes):
        f=self.fields
        if not isinstance(changes,dict) or set(changes)!={'value'}:reject('td_load_edit_fields')
        expressions=tuple(f[k] for k in ('expression','expression_b','expression_c','expression_d','expression_g'))
        if (not all(expression_is_constant(x) for x in expressions) or f['time_table']
                or any(f['selectors_a']) or f['selector_b']!=1 or f['selector_c'] or f['selector_d'] or f['selector_f']
                or f['selectors_e']!=(0,-1,-1,-1) or f['selectors_f']!=(0,-1,-1) or f['selector_g']!=1 or f['selector_h'] or f['selector_i']
                or f['text_d'] or f['text_f'] or any(f[k]!=1 for k in ('value_b','value_c','value_d'))
                or any(f['arrays_a']) or any(f['arrays_b'])
                or any(x['texts'] or x['text'] or any(x['table'].values()) for x in f['multi_expressions'])):
            reject('td_load_dynamic_edit')
        value=changes['value']
        if type(value) not in (int,float) or not math.isfinite(value):reject('td_load_edit_range')
        row=scalar_record(self.record,self.spans,changes);raw=bytes.fromhex(row['data']);after=decode_load(row,self.standard)
        if after.fields!={**f,**changes}:reject('td_load_edit_reopen_mismatch')
        return row,{'profile':PROFILE,'changed_fields':['value'],'bit_length_preserved':row['bits']==self.record['bits'],'qualified':False,
                    'before_sha256':sha256(bytes.fromhex(self.record['data'])).hexdigest(),'after_sha256':sha256(raw).hexdigest()}


def decode_load(row,standard):
    filer=Filer(row);b=filer.data;f={'common_handles':common_handles(filer,standard)};filer.version(17)
    f['name']=filer.text();f['comment']=filer.text();f['value']=filer.number('value')
    f['selectors_a']=tuple(b.bl() for _ in range(4))
    if f['selectors_a'][3] not in {0,1,2}:reject('td_load_type')
    f['time_table']=tuple((b.bd(),b.bd()) for _ in range(filer.count()));f['selector_b']=b.bl();f['expression']=filer.expression()
    f['value_b']=b.bd();f['expression_b']=filer.expression();f['selector_c']=b.bl();f['value_c']=b.bd();f['expression_c']=filer.expression()
    f['arrays_a']=tuple(filer.doubles() for _ in range(3));f['selector_d']=b.bl();f['text_d']=filer.text();f['selectors_e']=tuple(b.bl() for _ in range(4))
    f['value_d']=b.bd();f['expression_d']=filer.expression();f['arrays_b']=tuple(filer.doubles() for _ in range(2))
    f['selector_f']=b.bl();f['text_f']=filer.text();f['selectors_f']=tuple(b.bl() for _ in range(3));f['selector_g']=b.bl();f['expression_g']=filer.expression()
    f['connections']=filer.connections();f['selector_h']=b.bl();f['multi_expressions']=tuple(filer.multi_expression() for _ in range(7));f['selector_i']=b.bl()
    filer.finish();return LoadPayload(f,dict(filer.spans),dict(row),standard)
