# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded SINDA 6.3 assigned-value TPRINT/QPRINT tables, with explicit units."""
import re
from hashlib import sha256
from fcst_contracts import read,ContractError
from fcst_app.persistence import encode
from .core import reject
from .results import read_results
from .sinda import NUMBER


def read_print(raw,model,*,quantity,unit,time_unit,namespace_prefix='SINDA63.',interpolation='none',discontinuities=()):
    if not isinstance(raw,bytes) or len(raw)>16777216:reject('sinda_result_limit')
    if not isinstance(quantity,str) or quantity not in {'temperature','power'}:reject('sinda_result_quantity')
    try:text=raw.decode('ascii');model=read('model',model)
    except (UnicodeError,ContractError):reject('sinda_result_contract')
    index={};identities=[]
    for source in model['source_maps']:
        for entry in source['entries']:
            if not entry['namespace'].startswith(namespace_prefix):continue
            number=entry.get('node_number')
            if number is None:
                match=re.fullmatch(r'node\.(\d+)',entry['handle'])
                if not match:continue
                number=int(match[1])
            submodel=entry['namespace'][len(namespace_prefix):].upper()
            key=(submodel,int(number))
            if key in index:reject('sinda_result_identity_collision')
            index[key]=len(identities);identities.append([entry['namespace'],entry['handle']])
    if not identities:reject('sinda_result_identity_missing')
    marker='T' if quantity=='temperature' else 'Q'
    assignments=re.compile(r'\b'+marker+r'\s*(\d+)\s*=\s*('+NUMBER.pattern+r')',re.I)
    time_pattern=re.compile(r'\bTIMEN\s*=\s*('+NUMBER.pattern+r')',re.I)
    submodel_pattern=re.compile(r'\bSUBMODEL\s+NAME\s*=\s*([A-Za-z][A-Za-z0-9_]*)\s*$',re.I)
    times=[];values=[];current=None;submodel=None;frame={};seen_samples=0
    def flush():
        nonlocal frame,seen_samples
        if not frame:return
        if len(frame)!=len(identities):reject('sinda_result_incomplete_frame')
        if current is None:reject('sinda_result_missing_time')
        times.append(current);values.append([frame[i] for i in range(len(identities))]);frame={}
        seen_samples+=len(identities)
        if len(times)>10000 or seen_samples>1000000:reject('sinda_result_limit')
    for line in text.splitlines():
        t=time_pattern.search(line)
        if t:
            value=float(t[1].replace('D','E').replace('d','e'))
            if current!=value:flush();current=value;submodel=None
            continue
        sm=submodel_pattern.search(line)
        if sm:submodel=sm[1].upper();continue
        matches=list(assignments.finditer(line))
        if not matches:continue
        if assignments.sub('',line).strip():continue  # Input echoes/procedures are not data rows.
        if submodel is None or current is None:reject('sinda_result_missing_context')
        for match in matches:
            key=(submodel,int(match[1]))
            if key not in index:reject('sinda_result_unmapped_node')
            column=index[key]
            if column in frame:reject('sinda_result_duplicate_sample')
            frame[column]=float(match[2].replace('D','E').replace('d','e'))
    flush()
    if not values:reject('sinda_result_samples_missing')
    table={'version':'fcst-results/1','identities':identities,'quantity':quantity,'unit':unit,'time_unit':time_unit,
           'sign':'absolute' if quantity=='temperature' else 'positive_into_node','time':times,'values':values,
           'interpolation':interpolation,'discontinuities':list(discontinuities)}
    result=read_results(encode(table),model)
    # Keep the original printed-artifact hash, not the intermediate JSON hash.
    from dataclasses import replace
    return replace(result,source_sha256=sha256(raw).hexdigest())
