# SPDX-License-Identifier: MIT OR Apache-2.0
"""Direct byte-preserving TD thermophysical/optical text databases.

The declared profile reads bracket-tagged UTF-8 databases with their UNICODE
marker. Thermophysical values use stored SI units. Variable/table/aggregate
forms remain typed source blocks until a reviewed semantic codec covers them.
"""
from dataclasses import dataclass,field
from hashlib import sha256
import math
from pathlib import Path
import re
from .core import reject,Limits
from .vendor_paths import checked_path,path_name

PROFILE='td-property-text/1'
TAG=re.compile(rb'^\[([A-Z][A-Z0-9_]*)\][ \t]*(?:\r\n|\n|\r|$)')
NUMBER=re.compile(rb'([ \t]*)([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?)([ \t]*(?:\r\n|\n|\r)?)$')
MATERIAL={'CONDUCT','CONDUCTY','CONDUCTZ','DENSITY','SPECHEAT','DENSITYMULT','KUMULT','KVMULT','KWMULT','USEANISO','EFFECTIVEEMISS'}
OPTICS={'ALPHA','EMISS','SOLSPEC','IRSPEC','SOLTRANS','IRTRANS','SOLTSPEC','IRTSPEC','SOLREFRAC','IRREFRAC',
        'USEVSA','USEVST','USEVSS','USEVSZ','USEVIE','USEVIT','USEVIS','USEVIZ',
        'VARALPHA','VARSOLT','VARSOLS','VARSOLZ','VAREMISS','VARIRT','VARIRS','VARIRZ'}
NONNEGATIVE=MATERIAL|OPTICS
FRACTIONS={'ALPHA','EMISS','SOLSPEC','IRSPEC','SOLTRANS','IRTRANS','SOLTSPEC','IRTSPEC','EFFECTIVEEMISS'}
SWITCHES={'USEANISO',*(x for x in OPTICS if x.startswith('USE'))}
MATERIAL_FLAGS={'USEVARCONDUCT','USEVARCONDUCTY','USEVARCONDUCTZ','USEVARSPECHEAT',
                'USEVARCONDTEMPPRES','USEVARCONDTEMPPRESY','USEVARCONDTEMPPRESZ'}
MATERIAL_TABLES={'VARCONDUCT','VARCONDUCTY','VARCONDUCTZ','VARSPECHEAT'}
OPTICAL_FLAGS={'USETEMPSOLABS','USETEMPIREMIS','USEWAVELENGTHDEPPROPS'}
OPTICAL_TABLES={x for x in OPTICS if x.startswith('VAR')}|{'TEMPALPHA','TEMPEMIS'}
TABLE_FIELDS=MATERIAL_TABLES|OPTICAL_TABLES


@dataclass(frozen=True)
class PropertyTable:
    points:tuple=field(repr=False)

    def as_ast(self,input_ast,*,x_unit,y_unit,interpolation,extrapolation):
        from .sinda_arrays import StaticArray,table_ast
        data=StaticArray('PROPERTY',1,'real',tuple(v for row in self.points for v in row),())
        return table_ast(data,input_ast,x_unit=x_unit,y_unit=y_unit,interpolation=interpolation,extrapolation=extrapolation)


@dataclass(frozen=True)
class PropertyField:
    tag:str
    depth:int
    start:int
    end:int
    value:bytes=field(repr=False)

    def scalar(self):
        m=NUMBER.fullmatch(self.value)
        if not m:reject('td_property_nonconstant_value')
        try:value=float(m[2].replace(b'D',b'E').replace(b'd',b'e'))
        except (ValueError,OverflowError):reject('td_property_number')
        if not math.isfinite(value):reject('td_property_number')
        mantissa=m[2].replace(b'd',b'E').replace(b'D',b'E').replace(b'e',b'E').split(b'E')[0]
        if value==0 and any(c in b'123456789' for c in mantissa):reject('td_property_number_underflow')
        return value

    def table(self,*,limit=10000):
        if self.tag not in TABLE_FIELDS:reject('td_property_table_profile')
        tokens=self.value.split()
        if not tokens or not re.fullmatch(rb'\d{1,8}',tokens[0]):reject('td_property_table_count')
        count=int(tokens[0])
        if count>limit or len(tokens)!=1+2*count:reject('td_property_table_shape')
        values=[PropertyField(self.tag,0,0,len(token),token).scalar() for token in tokens[1:]]
        return PropertyTable(tuple(zip(values[::2],values[1::2])))


@dataclass(frozen=True)
class PropertyEntry:
    name:str=field(repr=False)
    fields:tuple=field(repr=False)
    insert_position:int=field(default=0,repr=False)

    def get(self,tag):
        values=[f for f in self.fields if f.tag==tag and f.depth==0]
        if len(values)!=1:reject('td_property_missing_or_duplicate_field')
        return values[0]


@dataclass(frozen=True)
class PropertyDocument:
    raw:bytes=field(repr=False)
    kind:str
    entries:tuple=field(repr=False)

    @property
    def report(self):
        known=MATERIAL|MATERIAL_FLAGS|MATERIAL_TABLES|{'TYPE','NAME','COLOR','COMMENT_MULTILINE'} if self.kind=='tdp' else OPTICS|OPTICAL_FLAGS|OPTICAL_TABLES|{'NAME','COMMENT_MULTILINE'}
        unknown=sum(f.depth==0 and f.tag not in known for e in self.entries for f in e.fields)
        variable=0
        for entry in self.entries:
            for f in entry.fields:
                if f.depth==0 and f.tag in MATERIAL|OPTICS|TABLE_FIELDS:
                    try:f.scalar()
                    except ValueError:variable+=1
        return {'profile':PROFILE,'kind':self.kind,'entries':len(self.entries),'unknown_root_fields':unknown,
                'nonconstant_fields':variable,'source_sha256':sha256(self.raw).hexdigest(),
                'vendor_runtime_required':False,'qualified':False,
                'scope':'Direct property syntax/scalars and bounded 1D tables; active table/composite physics remains separate'}

    def edited(self,changes):
        if not isinstance(changes,(list,tuple)) or not changes:reject('td_property_edits')
        pending=[];seen=set();allowed=MATERIAL if self.kind=='tdp' else OPTICS-OPTICAL_TABLES
        for change in changes:
            is_table=isinstance(change,dict) and set(change)=={'entry','field','points'}
            if not isinstance(change,dict) or not is_table and set(change)!={'entry','field','value'}:reject('td_property_edit_shape')
            name,tag=(change[k] for k in ('entry','field'));value=change.get('value')
            table_allowed=MATERIAL_TABLES if self.kind=='tdp' else OPTICAL_TABLES
            if not isinstance(name,str) or not isinstance(tag,str) or tag not in (table_allowed if is_table else allowed) or (name,tag) in seen:reject('td_property_edit_field')
            seen.add((name,tag));entry=next((e for e in self.entries if e.name==name),None)
            if entry is None:reject('td_property_edit_entry')
            types=[f for f in entry.fields if f.depth==0 and f.tag=='TYPE']
            if self.kind=='tdp' and types and types[0].scalar()!=0:reject('td_property_composite_or_variable_edit')
            if is_table:
                f=entry.get(tag);old=f.table().points;points=change['points']
                if (not isinstance(points,(tuple,list)) or len(points)!=len(old) or not old
                        or any(not isinstance(p,(tuple,list)) or len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) for p in points)):reject('td_property_table_edit_shape')
                if any(b[0]<=a[0] for values in (old,points) for a,b in zip(values,values[1:])):reject('td_property_table_axis')
                if self.kind=='rco' and any(not 0<=p[1]<=1 for p in points) or self.kind=='tdp' and any(p[1]<=0 for p in points):reject('td_property_table_range')
                ending=b'\r\n' if b'\r\n' in f.value else b'\r' if b'\r' in f.value else b'\n'
                raw=ending.join([str(len(points)).encode(),*(format(v,'.17g').encode() for p in points for v in p)])+ending
                pending.append((f.start,f.end,raw));continue
            active={'ALPHA':'USEVSA','SOLTRANS':'USEVST','SOLSPEC':'USEVSS','SOLREFRAC':'USEVSZ',
                    'EMISS':'USEVIE','IRTRANS':'USEVIT','IRSPEC':'USEVIS','IRREFRAC':'USEVIZ'}
            flags=[active[tag]] if self.kind=='rco' and tag in active else []
            if self.kind=='rco' and tag in {'ALPHA','EMISS'}:flags.append('USETEMPSOLABS' if tag=='ALPHA' else 'USETEMPIREMIS')
            if self.kind=='tdp':flags.extend({'CONDUCT':['USEVARCONDUCT','USEVARCONDTEMPPRES'],
                'CONDUCTY':['USEVARCONDUCTY','USEVARCONDTEMPPRESY'],'CONDUCTZ':['USEVARCONDUCTZ','USEVARCONDTEMPPRESZ'],
                'SPECHEAT':['USEVARSPECHEAT']}.get(tag,[]))
            if any(f.scalar()!=0 for f in entry.fields if f.depth==0 and f.tag in flags):reject('td_property_variable_edit')
            fields=[f for f in entry.fields if f.depth==0 and f.tag==tag];f=fields[0] if fields else None
            defaults={k:1 for k in ('CONDUCT','CONDUCTY','CONDUCTZ','DENSITY','SPECHEAT','DENSITYMULT','KUMULT','KVMULT','KWMULT','ALPHA','EMISS','SOLREFRAC','IRREFRAC')}
            prior=f.scalar() if f is not None else defaults.get(tag,0)
            m=NUMBER.fullmatch(f.value) if f is not None else None
            if type(value) not in (int,float) or not math.isfinite(value):reject('td_property_edit_number')
            if value<0 and tag in NONNEGATIVE or tag in FRACTIONS and value>1 or tag in SWITCHES and value not in (0,1):reject('td_property_edit_range')
            if tag in {'DENSITY','SPECHEAT','CONDUCT','CONDUCTY','CONDUCTZ'} and value<=0:reject('td_property_edit_range')
            # Switching semantic modes is not a scalar-property edit.
            if tag in SWITCHES and value!=prior:reject('td_property_edit_mode')
            replacement=format(value,'.17g').encode('ascii')
            if f is not None:pending.append((f.start+m.start(2),f.start+m.end(2),replacement))
            else:
                ending=b'\r\n' if b'\r\n' in self.raw else b'\r' if b'\r' in self.raw else b'\n'
                pending.append((entry.insert_position,entry.insert_position,b'['+tag.encode()+b']'+ending+replacement+ending))
        raw=self.raw
        for start,end,replacement in sorted(pending,reverse=True):raw=raw[:start]+replacement+raw[end:]
        reopened=parse_properties(raw,self.kind)
        if [e.name for e in reopened.entries]!=[e.name for e in self.entries]:reject('td_property_edit_reopen_identity')
        for change in changes:
            f=next(e for e in reopened.entries if e.name==change['entry']).get(change['field'])
            if 'points' in change:
                if f.table().points!=tuple(tuple(p) for p in change['points']):reject('td_property_edit_precision')
            elif f.scalar()!=float(change['value']):reject('td_property_edit_precision')
        # All bytes outside the selected numeric spans are retained by construction.
        return raw,{'profile':PROFILE,'edited_fields':len(pending),'reopen_verified':True,
                    'before_sha256':sha256(self.raw).hexdigest(),'after_sha256':sha256(raw).hexdigest(),
                    'vendor_runtime_required':False,'qualified':False}


def parse_properties(raw,kind,*,limits=Limits()):
    if kind not in {'tdp','rco'} or not isinstance(raw,bytes) or len(raw)>limits.file_bytes:reject('td_property_profile_or_size')
    try:raw.decode('utf-8-sig')
    except UnicodeError:reject('td_property_encoding')
    if b'\0' in raw:reject('td_property_encoding')
    prefix=3 if raw.startswith(b'\xef\xbb\xbf') else 0
    if not raw[prefix:].startswith(b'[UNICODE]'):reject('td_property_unicode_marker')
    lines=raw[prefix:].splitlines(keepends=True);offset=prefix;tokens=[];comment=False
    for line in lines:
        if len(line)>limits.line_bytes or len(tokens)>limits.records:reject('td_property_limit')
        m=TAG.fullmatch(line)
        if m:
            tag=m[1].decode('ascii')
            if not comment or tag=='ENDCOMMENT':tokens.append((tag,offset,offset+len(line)))
            if tag=='COMMENT_MULTILINE' and not comment:comment=True
            elif tag=='ENDCOMMENT' and comment:comment=False
        offset+=len(line)
    if comment:reject('td_property_unterminated_comment')
    if not tokens or tokens[0][0]!='UNICODE':reject('td_property_header')
    entries=[];current=None;fields=[];stack=[];names=set()
    opens={'AGGREGATE':'ENDAGGREGATE','COMPONENT':'ENDCOMPONENT'}
    for index,(tag,start,end) in enumerate(tokens):
        next_start=tokens[index+1][1] if index+1<len(tokens) else len(raw)
        value=raw[end:next_start]
        if tag=='UNICODE':
            if index or value.strip():reject('td_property_header')
        elif tag=='START':
            if current is not None or value.strip():reject('td_property_record_structure')
            current=start;fields=[];stack=[]
        elif current is None:
            if tag=='ENDCOMMENT':reject('td_property_comment_structure')
            reject('td_property_outside_record')
        elif tag=='END':
            if stack or value.strip():reject('td_property_record_structure')
            namefields=[f for f in fields if f.depth==0 and f.tag=='NAME']
            if len(namefields)!=1:reject('td_property_name')
            name=namefields[0].value.decode('utf-8').strip()
            if not name or len(name)>256 or any(ord(c)<32 for c in name) or name.casefold() in names:reject('td_property_name')
            names.add(name.casefold());entries.append(PropertyEntry(name,tuple(fields),start));current=None
        elif tag in opens:
            if value.strip() or len(stack)>=limits.include_depth:reject('td_property_nested_structure')
            stack.append(opens[tag])
        elif tag in opens.values():
            if not stack or stack.pop()!=tag or value.strip():reject('td_property_nested_structure')
        elif tag=='ENDCOMMENT':
            if value.strip():reject('td_property_comment_structure')
        else:
            if not stack and any(f.tag==tag and f.depth==0 for f in fields):reject('td_property_duplicate_field')
            fields.append(PropertyField(tag,len(stack),end,next_start,value))
    if current is not None or not entries:reject('td_property_record_structure')
    return PropertyDocument(raw,kind,tuple(entries))


def read_properties(root,entry,*,limits=Limits()):
    entry=path_name(entry);kind=Path(entry).suffix.lower()[1:]
    with checked_path(Path(root),entry).open('rb') as stream:raw=stream.read(limits.file_bytes+1)
    return parse_properties(raw,kind,limits=limits)
