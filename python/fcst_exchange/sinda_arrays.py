# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned static SINDA ARRAY DATA reader and explicit table-IR construction.

The declared syntax is numbered '=' arrays, including line continuations,
SPACE and ALLSAME. Integer/real storage kinds are retained. No array is assumed
to be a temperature/time table and no source interpolation routine is executed.
"""
from dataclasses import dataclass,field
import math
import re
from .core import reject,ExchangeError,Limits


@dataclass(frozen=True)
class StaticArray:
    submodel:str
    identifier:int
    storage:str
    values:tuple=field(repr=False)
    source_ids:tuple

    @property
    def report(self):
        return {'submodel':self.submodel,'identifier':self.identifier,'storage':self.storage,'values':len(self.values),
                'source_ids':list(self.source_ids),'interpolation':'unassigned','native_table':False}


def array_values(parts,registers,limit):
    from .sinda import scalar,split_fields
    tokens=split_fields(','.join(p.rstrip().removesuffix(',') for p in parts))
    if tokens and not tokens[-1]:tokens.pop()
    if not tokens or any(not s for s in tokens):reject('sinda_array_values')
    values=[];kinds=set();i=0
    while i<len(tokens):
        token=tokens[i];i+=1;name=token.upper()
        if name in {'SPACE','ALLSAME'}:
            if i>=len(tokens):reject('sinda_array_allocator')
            count=scalar(tokens[i],registers);i+=1
            if not count.is_integer() or not 0<=count<=limit-len(values):reject('sinda_array_allocation_limit')
            value=0
            if name=='ALLSAME':
                if i>=len(tokens):reject('sinda_array_allocator')
                token=tokens[i];i+=1;value=scalar(token,registers)
                kinds.add('integer' if re.fullmatch(r'[+-]?\d+',token) else 'real')
            values.extend([value]*int(count))
        else:
            values.append(scalar(token,registers));kinds.add('integer' if re.fullmatch(r'[+-]?\d+',token) else 'real')
        if len(values)>limit:reject('sinda_array_allocation_limit')
    if not values:reject('sinda_array_empty')
    if len(kinds)>1:reject('sinda_array_mixed_storage_requires_explicit_source_option')
    storage=next(iter(kinds),'integer')
    if storage=='integer' and any(not -2147483648<=v<=2147483647 for v in values):reject('sinda_array_integer_range')
    return tuple(values),storage


def parse_arrays(sources,registers,*,limits=Limits()):
    arrays={};errors={};record_keys={};total=0
    for source in sources:
        active=None;parts=[];members=[]
        def finish():
            nonlocal active,parts,members,total
            if active is None:return
            try:
                if active in arrays:reject('sinda_array_identity_collision')
                values,storage=array_values(parts,registers,limits.records-total);total+=len(values)
                arrays[active]=StaticArray(*active,storage,values,tuple(r.source_id for r in members))
                for row in members:record_keys[row.source_id]=active
            except ExchangeError as error:
                for row in members:errors[row.source_id]=error.code
            active=None;parts=[];members=[]
        for row in source.records:
            if row.kind=='COMMENT':continue
            if row.kind!='ARRAY' or row.code:
                finish();continue
            text=row.value['text'];match=re.fullmatch(r'\s*(\d{1,8})\s*=\s*(.*)',text)
            if match:
                finish();identifier=int(match[1])
                if not 1<=identifier<=99999999:errors[row.source_id]='sinda_array_identity';continue
                active=(row.value['submodel'],identifier);parts=[match[2]];members=[row]
            elif active is not None and '=' not in text:parts.append(text);members.append(row)
            else:errors[row.source_id]='sinda_array_declaration'
        finish()
    return arrays,record_keys,errors


def table_ast(array,input_ast,*,x_unit,y_unit,interpolation,extrapolation,discontinuities=()):
    """Only explicit caller bindings turn interleaved array values into a table."""
    from fcst_contracts import BUNDLE,validate,ContractError
    if not isinstance(array,StaticArray) or len(array.values)<4 or len(array.values)%2:reject('sinda_array_table_shape')
    if x_unit not in BUNDLE['units'] or y_unit not in BUNDLE['units']:reject('sinda_array_table_units')
    x,y=array.values[::2],array.values[1::2]
    if any(b<=a for a,b in zip(x,x[1:])):reject('sinda_array_table_axis')
    if (not isinstance(discontinuities,(tuple,list)) or any(type(i) is not int or not 1<=i<len(x) for i in discontinuities)
            or len(set(discontinuities))!=len(discontinuities) or discontinuities and interpolation!='previous'):reject('sinda_array_table_discontinuities')
    result={'op':'table','input':input_ast,'x':[{'value':v,'unit':x_unit} for v in x],
            'y':[{'value':v,'unit':y_unit} for v in y],'interpolation':interpolation,'extrapolation':extrapolation,
            'discontinuities':list(discontinuities)}
    schema=BUNDLE['schemas']['model']
    try:validate(schema['$defs']['ast'],result,schema)
    except ContractError:reject('sinda_array_table_contract')
    return result
