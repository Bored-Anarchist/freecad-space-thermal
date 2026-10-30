# SPDX-License-Identifier: MIT OR Apache-2.0
"""Direct native ERG/ERE/ERK inventory and safe XML inspection.

Syntax inventory and exact source retention are deliberately separate from
canonical geometry/campaign reconstruction. Unknown required physics stays held.
"""
from dataclasses import dataclass
from hashlib import sha256
import re
import xml.etree.ElementTree as ET

from fcst_app.persistence import encode
from .core import Limits, reject, fidelity, ExchangeError
from .esatan_syntax import NAME, statements, assignments, split
from .sinda import NUMBER, scalar
from .esatan import ESATAN_LIMITS


@dataclass(frozen=True)
class NativeDocument:
    content: bytes
    records: tuple
    inventory_bytes: bytes

    @property
    def inventory(self):
        import json
        return json.loads(self.inventory_bytes)


def _value(text, depth=0):
    if depth>24: reject('esatan_native_value_depth')
    text = text.strip()
    if NUMBER.fullmatch(text): return {'number':scalar(text,{})}
    if text in {'TRUE','FALSE'}: return {'boolean':text=='TRUE'}
    if re.fullmatch(r'"(?:[^"\x00]|"")*"|\'(?:[^\'\x00]|\'\')*\'',text,re.S):
        return {'string':text[1:-1].replace(text[0]*2,text[0])}
    if len(text)>=2 and text[0] in '[{' and text[-1]=={'[':']','{':'}'}[text[0]]:
        items = split(text[1:-1]) if text[1:-1].strip() else []
        return {'array':[_value(item,depth+1) for item in items]}
    if re.fullmatch(NAME,text): return {'symbol':text}
    call = re.fullmatch('('+NAME+r')\s*\((.*)\)',text,re.S)
    if call:
        if not any('=' in field for field in split(call[2])):
            return {'unresolved_expression':text}
        return {'call':call[1], 'arguments':{k:_value(v,depth+1) for k,v in assignments(call[2]).items()}}
    # Retain algebraic/geometry expressions without guessing degrees, frames,
    # runtime interpolation, symbol scope or source-language evaluation rules.
    return {'unresolved_expression':text}


def inspect_native(raw, *, family, source_version, path='model.erg', limits=ESATAN_LIMITS):
    if family not in {'erg','ere','erk'} or source_version not in {'2018-sp1','2020'}:
        reject('esatan_native_profile')
    records = statements(path,raw,native=True,limits=limits)
    rows = []; symbols = {}; active = False; ended = False; name = None; diagnostics = []
    for r in records:
        if r.kind=='COMMENT': continue
        text = r.value['text'].removesuffix(';').strip()
        row = fidelity(r,'retained-opaque',code='esatan_native_semantics_unmapped')
        syntax = None
        try:
            if r.code: reject(r.code)
            begin = re.fullmatch(r'BEGIN_MODEL\s+('+NAME+r')(?:\s+WORKBENCH_V1\s+ESARAD_GENERATED)?',text)
            declaration = re.fullmatch(r'(?:(CONST)\s+)?(REAL|INTEGER|POINT|VECTOR|MATRIX|BULK|OPTICAL|GEOMETRY|BOUNDARY_CONDITION|RADIATIVE_CASE)\s+('+NAME+r')(\[[^\]]+\])?(?:\s*=\s*(.*))?',text,re.S)
            assignment = re.fullmatch('('+NAME+r')(\[[^\]]+\])?\s*=\s*(.+)',text,re.S)
            if begin and not active and not ended:
                active = True; name = begin[1]; syntax = {'kind':'model','name':name}
            elif text=='END_MODEL' and active:
                active = False; ended = True; syntax = {'kind':'end_model'}
            elif not active: reject('esatan_native_model_context')
            elif declaration:
                symbol = declaration[3]
                if symbol in symbols: reject('esatan_native_symbol_collision')
                syntax = {'kind':'declaration','type':declaration[2],'name':symbol,
                          'constant':bool(declaration[1]),'shape':declaration[4]}
                if declaration[5] is not None: syntax['value'] = _value(declaration[5])
                symbols[symbol] = declaration[2]
            elif assignment:
                # Model composition is also an assignment; every expression is
                # retained even when it does not have a reviewed thermal mapping.
                syntax = {'kind':'assignment','name':assignment[1],'variant':assignment[2],
                          'value':_value(assignment[3])}
            elif re.fullmatch(NAME+r'\s*\(.*\)',text,re.S):
                syntax = {'kind':'definition','value':_value(text)}
            else: reject('esatan_native_unknown_syntax')
        except ExchangeError as error:
            row.update(status='unsupported',limitations=[error.code])
            diagnostics.append({'source_id':r.source_id,'code':error.code})
        row['syntax'] = syntax; rows.append(row)
    if active or not ended: diagnostics.append({'source_id':'project','code':'esatan_native_model_balance'})
    inventory = {'profile':'esatan-'+family+'-syntax/1','source_version':source_version,
                 'source_sha256':sha256(raw).hexdigest(),'model_name':name,'records':rows,
                 'diagnostics':diagnostics,'syntax_complete':not diagnostics,'runnable':False,'qualified':False,
                 'limitations':['Syntax retention does not implement geometry, environments, motion, campaign or mesh semantics']}
    return NativeDocument(raw,records,encode(inventory))


def inspect_project_xml(raw, *, limits=Limits()):
    """Inspect bounded UTF-8 XML inertly; never expand DTDs, entities or includes.

    XML schema/profile acquisition is still required before project semantics can
    be reconstructed. A Git LFS pointer is explicitly distinct from XML content.
    """
    if not isinstance(raw,bytes) or len(raw)>limits.file_bytes: reject('esatan_xml_byte_limit')
    if raw.startswith(b'version https://git-lfs.github.com/spec/v1'):
        reject('esatan_project_lfs_content_missing')
    try: text = raw.decode('utf-8-sig')
    except UnicodeError: reject('esatan_xml_encoding')
    if '\x00' in text or re.search(r'<!\s*(?:DOCTYPE|ENTITY)|<\?(?!xml\s)',text,re.I):
        reject('esatan_xml_external_construct')
    try: root = ET.fromstring(text)
    except (ET.ParseError,ValueError,RecursionError): reject('esatan_xml_syntax')
    pending = [(root,0)]; tags = {}; count = 0
    while pending:
        node,depth = pending.pop(); count += 1
        if depth>limits.include_depth or count>limits.records: reject('esatan_xml_limit')
        if not isinstance(node.tag,str) or node.tag.startswith('{http://www.w3.org/2001/XInclude}'):
            reject('esatan_xml_external_construct')
        tags[node.tag] = tags.get(node.tag,0)+1
        pending.extend((child,depth+1) for child in node)
    return {'profile':'esatan-project-xml-inspection/1','source_sha256':sha256(raw).hexdigest(),
            'elements':count,'tags':tags,'runnable':False,'qualified':False,
            'limitations':['Project/campaign schema unresolved; XML syntax alone cannot establish dependency closure']}
