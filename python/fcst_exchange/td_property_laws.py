# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independent basic TD property laws, including temperature/pressure grids.

This interchange retains separate optical bands and inactive source settings.
It is not the constant-only canonical material contract. Interpolation and
extrapolation are explicit evaluation policies, never inferred vendor behavior.
"""
from bisect import bisect_right
from dataclasses import dataclass,field
import math
from .core import Limits,reject
from .td_properties import (parse_properties,MATERIAL,OPTICS,
    MATERIAL_FLAGS,MATERIAL_TABLES,OPTICAL_FLAGS,OPTICAL_TABLES,GRID_FIELDS)

PROFILE='td-property-laws/1'
SCALARS={'tdp':MATERIAL|MATERIAL_FLAGS|{'TYPE','COLOR'},'rco':(OPTICS-OPTICAL_TABLES)|OPTICAL_FLAGS}
TABLES={'tdp':MATERIAL_TABLES,'rco':OPTICAL_TABLES}
AGGREGATE_SETTINGS={'WEIGHTTYPE','AGGREGATE_OVERRIDE_CONDUCTIVITY','AGGREGATE_OVERRIDE_SPECIFIC_HEAT_DENSITY'}
COMPONENT_SCALARS={'THICKNESS','ORIENTATIONANGLE','KXP','KYP','KZP','MASSFRACTION','WEIGHT'}


def _name(name):
    if isinstance(name,str):
        try:name.encode('utf-8')
        except UnicodeError:return False
    return (isinstance(name,str) and bool(name) and name==name.strip() and len(name)<=256
            and not any(ord(c)<32 for c in name) and not (name.startswith('[') and name.endswith(']')))


def _aggregate(entry):
    roots=[b for b in entry.blocks if b.tag=='AGGREGATE' and b.depth==0]
    components=sorted((b for b in entry.blocks if b.tag=='COMPONENT' and b.depth==1),key=lambda b:b.start)
    if len(roots)!=1 or len(entry.blocks)!=len(components)+1 or not components:reject('td_property_law_composite_structure')
    root=roots[0]
    if any(not root.start<b.start<b.end<root.end for b in components):reject('td_property_law_composite_structure')
    settings={};rows=[]
    for f in entry.fields:
        if f.depth==1:
            if f.tag not in AGGREGATE_SETTINGS or f.tag in settings:reject('td_property_law_composite_field')
            settings[f.tag]=f.scalar()
        elif f.depth>2:reject('td_property_law_composite_structure')
    for b in components:
        fields={};material=None
        for f in entry.fields:
            if not b.start<=f.start<b.end or f.depth!=2:continue
            if f.tag=='MATERIALNAME':
                if material is not None:reject('td_property_law_composite_field')
                material=f.value.decode('utf-8').strip()
            elif f.tag in COMPONENT_SCALARS and f.tag not in fields:fields[f.tag]=f.scalar()
            else:reject('td_property_law_composite_field')
        if not _name(material):reject('td_property_law_composite_reference')
        rows.append({'material':material,'scalars':fields})
    return {'scalars':settings,'components':rows}


def _number(value):
    try:valid=type(value) in (int,float) and math.isfinite(value)
    except OverflowError:valid=False
    if not valid:reject('td_property_law_number')
    return float(value)


def read_laws(raw,kind,*,limits=Limits()):
    if not isinstance(kind,str) or kind not in SCALARS:reject('td_property_law_profile')
    doc=parse_properties(raw,kind,limits=limits);entries=[]
    for entry in doc.entries:
        row={'name':entry.name,'scalars':{},'tables':{},'vectors':{}}
        for f in entry.fields:
            if f.depth:continue
            if f.tag in {'NAME','COMMENT_MULTILINE'}:continue
            if f.tag in SCALARS[kind]:row['scalars'][f.tag]=f.scalar()
            elif f.tag in TABLES[kind]:row['tables'][f.tag]=[list(p) for p in f.table(limit=limits.records).points]
            elif kind=='tdp' and f.tag in GRID_FIELDS:row['vectors'][f.tag]=list(f.vector(limit=limits.records))
            else:reject('td_property_law_field_unmapped')
        if entry.blocks:
            if kind!='tdp':reject('td_property_law_composite_structure')
            row['aggregate']=_aggregate(entry)
        entries.append(row)
    library={'profile':PROFILE,'kind':kind,'entries':entries}
    validate_laws(library,limits=limits)
    return library


def validate_laws(library,*,limits=Limits()):
    if (not isinstance(library,dict) or set(library)!={'profile','kind','entries'}
            or library['profile']!=PROFILE or not isinstance(library['kind'],str) or library['kind'] not in SCALARS):reject('td_property_law_profile')
    kind=library['kind'];rows=library['entries'];names=set();total=0
    if not isinstance(rows,list) or not rows or len(rows)>limits.records:reject('td_property_law_inventory')
    for row in rows:
        if not isinstance(row,dict) or set(row) not in ({'name','scalars','tables','vectors'},{'name','scalars','tables','vectors','aggregate'}):reject('td_property_law_entry')
        name=row['name']
        if not _name(name) or name.casefold() in names:reject('td_property_law_name')
        names.add(name.casefold())
        for group,allowed in (('scalars',SCALARS[kind]),('tables',TABLES[kind]),('vectors',GRID_FIELDS if kind=='tdp' else set())):
            values=row[group]
            if not isinstance(values,dict) or set(values)-allowed:reject('td_property_law_field_unmapped')
            for tag,value in values.items():
                if group=='scalars':_number(value);continue
                if not isinstance(value,list) or len(value)>limits.records:reject('td_property_law_table_shape')
                total+=len(value)*(2 if group=='tables' else 1)
                if total>limits.records:reject('td_property_law_table_limit')
                if group=='tables':
                    if any(not isinstance(p,list) or len(p)!=2 for p in value):reject('td_property_law_table_shape')
                    for p in value:
                        for v in p:_number(v)
                    if any(b[0]<=a[0] for a,b in zip(value,value[1:])):reject('td_property_law_table_axis')
                else:
                    for v in value:_number(v)
        if kind=='tdp' and row['scalars'].get('TYPE',0) in (1,2):
            _validate_aggregate(row,limits)
            total+=len(row['aggregate']['components'])
            if total>limits.records:reject('td_property_law_table_limit')
            # Validate retained basic overrides using the same physical ranges,
            # without pretending those overrides define the composite mixture.
            base={**row,'scalars':{**row['scalars'],'TYPE':0}}
            material_laws(base)
        elif kind=='tdp':
            if 'aggregate' in row:reject('td_property_law_composite_structure')
            material_laws(row)
        else:optical_laws(row)
        if kind=='rco' and 'aggregate' in row:reject('td_property_law_composite_structure')
    if kind=='tdp':
        catalog={r['name']:r for r in rows}
        for row in rows:
            for component in row.get('aggregate',{}).get('components',[]):
                target=catalog.get(component['material'])
                if target is None or target['scalars'].get('TYPE',0)!=0:reject('td_property_law_composite_reference')
    return library


def _validate_aggregate(row,limits):
    aggregate=row.get('aggregate')
    if not isinstance(aggregate,dict) or set(aggregate)!={'scalars','components'}:reject('td_property_law_composite_structure')
    settings=aggregate['scalars'];components=aggregate['components']
    if not isinstance(settings,dict) or set(settings)-AGGREGATE_SETTINGS:reject('td_property_law_composite_field')
    for value in settings.values():
        if _number(value) not in (0,1):reject('td_property_law_switch')
    if not isinstance(components,list) or not components or len(components)>limits.records:reject('td_property_law_composite_structure')
    for component in components:
        if (not isinstance(component,dict) or set(component)!={'material','scalars'} or not _name(component['material'])
                or not isinstance(component['scalars'],dict) or set(component['scalars'])-COMPONENT_SCALARS):reject('td_property_law_composite_field')
        for tag,value in component['scalars'].items():
            _number(value)
            if tag=='THICKNESS' and value<=0 or tag not in {'THICKNESS','ORIENTATIONANGLE'} and not 0<=value<=1:reject('td_property_law_composite_range')
        if row['scalars']['TYPE']==1 and component['scalars'].get('THICKNESS',0)<=0:reject('td_property_law_composite_thickness')


def write_laws(library,*,limits=Limits()):
    """Create an original-format database without any vendor file/template."""
    validate_laws(library,limits=limits);lines=['[UNICODE]']
    for row in library['entries']:
        lines+=['[START]','[NAME]',row['name']]
        for group in ('scalars','tables','vectors'):
            for tag,value in sorted(row[group].items()):
                lines.append('['+tag+']')
                if group=='scalars':lines.append(format(value,'.17g'))
                else:
                    lines.append(str(len(value)))
                    if group=='tables':lines.extend(' '.join(format(v,'.17g') for v in p) for p in value)
                    else:lines.extend(format(v,'.17g') for v in value)
        if 'aggregate' in row:
            lines.append('[AGGREGATE]')
            for tag,value in sorted(row['aggregate']['scalars'].items()):lines+=['['+tag+']',format(value,'.17g')]
            for component in row['aggregate']['components']:
                lines+=['[COMPONENT]','[MATERIALNAME]',component['material']]
                for tag,value in sorted(component['scalars'].items()):lines+=['['+tag+']',format(value,'.17g')]
                lines.append('[ENDCOMPONENT]')
            lines.append('[ENDAGGREGATE]')
        lines.append('[END]')
    raw=('\r\n'.join(lines)+'\r\n').encode('utf-8')
    if len(raw)>limits.file_bytes:reject('td_property_law_file_limit')
    if read_laws(raw,library['kind'],limits=limits)!=library:reject('td_property_law_reopen_mismatch')
    return raw


def _axis(values,*,positive=False):
    if any(_number(v)<0 or positive and v<=0 for v in values) or any(b<=a for a,b in zip(values,values[1:])):reject('td_property_law_axis')


def _span(axis,x,interpolation,extrapolation):
    if interpolation not in {'linear','previous'} or extrapolation not in {'error','clamp'}:reject('td_property_law_policy')
    x=_number(x)
    if x<axis[0] or x>axis[-1]:
        if extrapolation=='error':reject('td_property_law_domain')
        x=min(max(x,axis[0]),axis[-1])
    if len(axis)==1:return 0,0,0.
    index=min(bisect_right(axis,x)-1,len(axis)-2)
    fraction=(x-axis[index])/(axis[index+1]-axis[index])
    if interpolation=='previous':return (index+1,index+1,0.) if fraction==1 else (index,index,0.)
    return index,index+1,fraction


@dataclass(frozen=True)
class PropertyLaw:
    mode:str
    unit:str
    values:tuple=field(repr=False)
    temperature:tuple=field(default=(),repr=False)
    pressure:tuple=field(default=(),repr=False)
    angle:tuple=field(default=(),repr=False)
    scale:float=1.

    def __post_init__(self):
        if self.mode not in {'constant','temperature-table','temperature-pressure-table','angle-table'}:reject('td_property_law_mode')
        if not self.values or any(not math.isfinite(_number(v)) for v in self.values) or _number(self.scale)<=0:reject('td_property_law_number')
        for axis,positive in ((self.temperature,True),(self.pressure,False),(self.angle,False)):_axis(axis,positive=positive)
        if self.mode=='constant':valid=len(self.values)==1 and not (self.temperature or self.pressure or self.angle)
        elif self.mode=='angle-table':valid=len(self.values)==len(self.angle) and not (self.temperature or self.pressure)
        elif self.mode=='temperature-table':valid=len(self.values)==len(self.temperature) and not (self.pressure or self.angle)
        else:valid=bool(self.temperature and self.pressure) and len(self.values)==len(self.temperature)*len(self.pressure) and not self.angle
        if not valid:reject('td_property_law_table_shape')

    def evaluate(self,*,temperature=None,pressure=None,angle=None,interpolation,extrapolation):
        # Validate policies even for constants so an invalid caller policy cannot
        # appear to work and then change behavior when a source mode is enabled.
        if interpolation not in {'linear','previous'} or extrapolation not in {'error','clamp'}:reject('td_property_law_policy')
        if self.mode=='constant':
            result=self.values[0]*self.scale
            if not math.isfinite(result):reject('td_property_law_number')
            return result
        axis=self.angle if self.mode=='angle-table' else self.temperature
        x=angle if self.mode=='angle-table' else temperature
        a,b,t=_span(axis,x,interpolation,extrapolation)
        if self.mode=='temperature-pressure-table':
            c,d,u=_span(self.pressure,pressure,interpolation,extrapolation);n=len(axis)
            # Original storage varies temperature first, then pressure.
            low=self.values[c*n+a]*(1-t)+self.values[c*n+b]*t
            high=self.values[d*n+a]*(1-t)+self.values[d*n+b]*t
            result=low*(1-u)+high*u
        else:result=self.values[a]*(1-t)+self.values[b]*t
        result*=self.scale
        if not math.isfinite(result):reject('td_property_law_number')
        return result


def _switch(s,tag):
    value=s.get(tag,0)
    if value not in (0,1):reject('td_property_law_switch')
    return value==1


def _table(row,tag,unit,*,scale=1.,angle=False):
    points=row['tables'].get(tag,[])
    if not points:reject('td_property_law_active_table_missing')
    axis=tuple(p[0] for p in points);_axis(axis,positive=not angle)
    return PropertyLaw('angle-table' if angle else 'temperature-table',unit,tuple(p[1] for p in points),angle=axis if angle else (),temperature=() if angle else axis,scale=scale)


def material_laws(row):
    s=row['scalars'];tables=row['tables'];vectors=row['vectors']
    if s.get('TYPE',0)!=0:reject('td_property_law_composite_unmapped')
    if s.get('COLOR',1)!=int(s.get('COLOR',1)) or not 1<=s.get('COLOR',1)<=255:reject('td_property_color_range')
    if not 0<=s.get('EFFECTIVEEMISS',0)<=1:reject('td_property_material_range')
    if any(_number(s.get(k,1))<=0 for k in ('DENSITY','DENSITYMULT','SPECHEAT','CONDUCT','CONDUCTY','CONDUCTZ','KUMULT','KVMULT','KWMULT')):reject('td_property_material_range')
    if any(p[0]<=0 or p[1]<=0 for points in tables.values() for p in points):reject('td_property_material_range')
    for tag in MATERIAL_FLAGS:_switch(s,tag)
    axes=[]
    for suffix,mult in (('','KUMULT'),('Y','KVMULT'),('Z','KWMULT')):
        tag='CONDUCT'+suffix;scale=s.get(mult,1);use_table=_switch(s,'USEVAR'+tag);use_grid=_switch(s,'USEVARCONDTEMPPRES'+suffix)
        if use_table and use_grid:reject('td_property_law_conflicting_modes')
        t=vectors.get('BIVARTEMPERATURE'+suffix,[]);p=vectors.get('BIVARPRESSURE'+suffix,[]);v=vectors.get('BIVARCONDUCTIVITY'+suffix,[])
        if t or p or v:
            _axis(t,positive=True);_axis(p)
            if not t or not p or len(v)!=len(t)*len(p) or any(x<=0 for x in v):reject('td_property_grid_shape')
        if use_grid:
            if not v:reject('td_property_law_active_table_missing')
            law=PropertyLaw('temperature-pressure-table','W/(m*K)',tuple(v),tuple(t),tuple(p),scale=scale)
        elif use_table:law=_table(row,'VAR'+tag,'W/(m*K)',scale=scale)
        else:law=PropertyLaw('constant','W/(m*K)',(s.get(tag,1),),scale=scale)
        axes.append(law)
    cp=_table(row,'VARSPECHEAT','J/(kg*K)') if _switch(s,'USEVARSPECHEAT') else PropertyLaw('constant','J/(kg*K)',(s.get('SPECHEAT',1),))
    density=s.get('DENSITY',1)*s.get('DENSITYMULT',1)
    if not math.isfinite(density) or density<=0 or any(not math.isfinite(v*law.scale) or v*law.scale<=0 for law in [*axes,cp] for v in law.values):reject('td_property_material_range')
    return {'mode':'orthotropic' if _switch(s,'USEANISO') else 'isotropic','density':{'value':density,'unit':'kg/m3'},
            'conductivity':tuple(axes),'specific_heat':cp,'effective_emissivity':s.get('EFFECTIVEEMISS',0)}


def optical_laws(row):
    s=row['scalars'];result={}
    for flag in OPTICAL_FLAGS|{k for k in OPTICS if k.startswith('USE')}:_switch(s,flag)
    for tag in ('ALPHA','EMISS','SOLTRANS','IRTRANS','SOLSPEC','IRSPEC','SOLTSPEC','IRTSPEC'):
        if not 0<=s.get(tag,1 if tag in {'ALPHA','EMISS'} else 0)<=1:reject('td_property_optical_range')
    if any(not 0<=p[1]<=1 or (p[0]<=0 if tag in {'TEMPALPHA','TEMPEMIS'} else p[0]<0) for tag,points in row['tables'].items() for p in points):reject('td_property_optical_range')
    for prefix,absorb,flags,tags,tempflag,temptag in (
        ('SOL','ALPHA',('USEVSA','USEVST','USEVSS','USEVSZ'),('VARALPHA','VARSOLT','VARSOLS','VARSOLZ'),'USETEMPSOLABS','TEMPALPHA'),
        ('IR','EMISS',('USEVIE','USEVIT','USEVIS','USEVIZ'),('VAREMISS','VARIRT','VARIRS','VARIRZ'),'USETEMPIREMIS','TEMPEMIS')):
        temp=_switch(s,tempflag);laws={}
        for key,scalar,flag,tag in zip(('absorptivity','transmissivity','specular_fraction','transmissive_specular_fraction'),
                (absorb,prefix+'TRANS',prefix+'SPEC',prefix+'TSPEC'),flags,tags):
            if temp and key=='absorptivity':law=_table(row,temptag,'1')
            elif not temp and _switch(s,flag):law=_table(row,tag,'1',angle=True)
            else:law=PropertyLaw('constant','1',(s.get(scalar,1 if scalar==absorb else 0),))
            laws[key]=law
        ratio=s.get(prefix+'REFRAC',1)
        if ratio<=0:reject('td_property_optical_range')
        laws['refractive_index_ratio']=ratio;result['solar' if prefix=='SOL' else 'infrared']=laws
        # Independently varying angle tables must obey energy balance at every
        # knot. Temperature/angle cross products are never silently assumed.
        a= laws['absorptivity'];t=laws['transmissivity']
        axes=sorted(set(a.angle+t.angle)) if a.angle or t.angle else sorted(set(a.temperature+t.temperature))
        for x in axes or [0]:
            kwargs={'angle':x,'temperature':x,'interpolation':'linear','extrapolation':'clamp'}
            if a.evaluate(**kwargs)+t.evaluate(**kwargs)>1:reject('td_property_optical_range')
    result['wavelength_dependent_radks']=_switch(s,'USEWAVELENGTHDEPPROPS')
    return result


def law_report(library):
    validate_laws(library)
    return {'profile':PROFILE,'kind':library['kind'],'entries':len(library['entries']),
            'tables':sum(len(r['tables']) for r in library['entries']),'grid_vectors':sum(len(r['vectors']) for r in library['entries']),
            'composite_entries':sum('aggregate' in r for r in library['entries']),
            'vendor_runtime_required':False,'native_ready':False,'qualified':False,
            'scope':'Basic property laws and composite definitions; explicit evaluation policies; composite physics and canonical variable/spectral bindings remain pending'}


def export_laws(library,destination,*,json_output=False):
    """Atomic new-tree output, with an independent readback before publication."""
    import os
    from pathlib import Path
    import shutil
    import tempfile
    from fcst_app.persistence import encode
    from fcst_contracts import loads
    from .vendor_paths import checked_path
    from .export import rename_new
    validate_laws(library)
    raw=encode(library) if json_output else write_laws(library)
    if len(raw)>Limits().file_bytes:reject('td_property_law_file_limit')
    name='property-laws.json' if json_output else 'materials.tdp' if library['kind']=='tdp' else 'optics.rco'
    destination=Path(destination).absolute()
    if destination.exists() or not destination.parent.is_dir():reject('td_property_library_new_target')
    checked_path(destination.parent,destination.name)
    temporary=Path(tempfile.mkdtemp(prefix='.fcst-laws-',dir=destination.parent))
    try:
        with (temporary/name).open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        after=(temporary/name).read_bytes()
        if (loads(after) if json_output else read_laws(after,library['kind']))!=library:reject('td_property_law_reopen_mismatch')
        rename_new(temporary,destination)
    finally:
        if temporary.exists():
            if temporary.resolve().parent!=destination.parent.resolve() or not temporary.name.startswith('.fcst-laws-'):reject('td_property_library_cleanup')
            shutil.rmtree(temporary)
    return {'reopen_verified':True,**law_report(library)}


def edit_composite(document,changes):
    """Edit selected existing component numbers, keeping all other source bytes."""
    from hashlib import sha256
    from .td_properties import NUMBER
    before=read_laws(document.raw,document.kind);pending=[];seen=set()
    for change in changes:
        if not isinstance(change,dict) or set(change)!={'entry','component','field','value'}:reject('td_property_composite_edit_shape')
        name,index,tag,value=(change[k] for k in ('entry','component','field','value'))
        if not isinstance(name,str) or type(index) is not int or index<0 or not isinstance(tag,str) or tag not in COMPONENT_SCALARS:reject('td_property_composite_edit_field')
        key=(name,index,tag)
        if key in seen:reject('td_property_composite_edit_duplicate')
        seen.add(key);_number(value)
        entry=next((e for e in document.entries if e.name==name),None)
        if entry is None:reject('td_property_composite_edit_entry')
        blocks=sorted((b for b in entry.blocks if b.tag=='COMPONENT'),key=lambda b:b.start)
        if index>=len(blocks):reject('td_property_composite_edit_component')
        block=blocks[index];fields=[f for f in entry.fields if f.depth==2 and block.start<=f.start<block.end and f.tag==tag]
        if len(fields)!=1:reject('td_property_composite_edit_field')
        f=fields[0];f.scalar();match=NUMBER.fullmatch(f.value)
        pending.append((f.start+match.start(2),f.start+match.end(2),format(value,'.17g').encode()))
    raw=document.raw
    for start,end,replacement in sorted(pending,reverse=True):raw=raw[:start]+replacement+raw[end:]
    actual=read_laws(raw,document.kind)
    from copy import deepcopy
    expected=deepcopy(before)
    for change in changes:
        row=next(r for r in expected['entries'] if r['name']==change['entry'])
        row['aggregate']['components'][change['component']]['scalars'][change['field']]=change['value']
    if actual!=expected:reject('td_property_composite_edit_reopen')
    return raw,{'profile':PROFILE,'edited_fields':len(pending),'reopen_verified':True,
        'before_sha256':sha256(document.raw).hexdigest(),'after_sha256':sha256(raw).hexdigest(),
        'vendor_runtime_required':False,'native_ready':False,'qualified':False}
