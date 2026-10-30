# SPDX-License-Identifier: MIT OR Apache-2.0
"""Explicit constant thermophysical/optical semantics and owned library writer."""
from copy import deepcopy
from hashlib import sha256
import math
import os
from pathlib import Path
import shutil
import tempfile
from fcst_contracts import BUNDLE,ContractError,loads,read,validate
from fcst_app.persistence import encode
from .core import reject,target_id
from .td_properties import parse_properties,MATERIAL,OPTICS,MATERIAL_FLAGS,MATERIAL_TABLES,OPTICAL_FLAGS,OPTICAL_TABLES,TABLE_FIELDS
from .vendor_paths import checked_path
from .export import rename_new


def _values(entry,kind):
    allowed=MATERIAL|MATERIAL_FLAGS|MATERIAL_TABLES|{'NAME','TYPE','COLOR','COMMENT_MULTILINE'} if kind=='tdp' else OPTICS|OPTICAL_FLAGS|OPTICAL_TABLES|{'NAME','COMMENT_MULTILINE'}
    if any(f.depth or f.tag not in allowed for f in entry.fields):reject('td_property_required_fields_unmapped')
    values={}
    for f in entry.fields:
        if f.tag in {'NAME','COMMENT_MULTILINE'}:continue
        if f.tag in TABLE_FIELDS:
            f.table();values[f.tag]=0 # Valid but inactive table data is retained in the original.
        else:values[f.tag]=f.scalar()
    return values


def material_entity(entry,temperature_range,*,identifier=None):
    """The source has no validity interval: callers must declare one in kelvin."""
    v=_values(entry,'tdp')
    if (not isinstance(temperature_range,(tuple,list)) or len(temperature_range)!=2
            or any(type(x) not in (int,float) or not math.isfinite(x) for x in temperature_range)
            or not 0<temperature_range[0]<temperature_range[1]):reject('td_property_temperature_interval_required')
    if v.get('TYPE',0)!=0 or v.get('USEANISO',0)!=0 or v.get('EFFECTIVEEMISS',0)!=0 or any(v.get(k,0)!=0 for k in MATERIAL_FLAGS):reject('td_property_material_mode_unmapped')
    color=v.get('COLOR',1)
    if not 1<=color<=255 or int(color)!=color:reject('td_property_color_range')
    if any(v.get(k,1)<=0 for k in ('DENSITY','SPECHEAT','CONDUCT','DENSITYMULT','KUMULT')):reject('td_property_material_range')
    result={'id':identifier or target_id(('td-property','material',entry.name.casefold())),'kind':'material','label':entry.name,
            'density':{'value':v.get('DENSITY',1)*v.get('DENSITYMULT',1),'unit':'kg/m3'},
            'specific_heat':{'value':v.get('SPECHEAT',1),'unit':'J/(kg*K)'},
            'conductivity':{'value':v.get('CONDUCT',1)*v.get('KUMULT',1),'unit':'W/(m*K)'},
            'valid_temperature':[{'value':x,'unit':'K'} for x in temperature_range]}
    if any(not math.isfinite(result[k]['value']) for k in ('density','specific_heat','conductivity')):reject('td_property_material_range')
    return result


def import_document(raw,kind,temperature_range=None,*,names=None):
    """Import original property text; selection and material validity are explicit."""
    document=parse_properties(raw,kind);selected=list(document.entries)
    if names is not None:
        if (not isinstance(names,(list,tuple)) or not names or any(not isinstance(n,str) for n in names)
                or len({n.casefold() for n in names})!=len(names)):reject('td_property_selection')
        requested={n.casefold() for n in names};selected=[e for e in selected if e.name.casefold() in requested]
        if len(selected)!=len(requested):reject('td_property_selection')
    entities=[material_entity(e,temperature_range) if kind=='tdp' else optics_entity(e) for e in selected]
    revision=sha256(raw).hexdigest();entries=[{'namespace':'TD.PROPERTIES','handle':kind+'.'+sha256(e.name.casefold().encode()).hexdigest()[:32],
                                            'entity_id':native['id']} for e,native in zip(selected,entities)]
    model={'contract_version':'1.0.0','minimum_reader':'1.0.0','project_id':target_id(('td-property-document',kind,revision)),
           'revision':0,'entities':entities,'source_maps':[{'id':target_id(('td-property-map',kind,revision)),
           'version':'1.0.0','source_revision':revision,'source_tool':'Thermal Desktop property text','source_version':'UNICODE bracket-tagged profile 1',
           'entries':entries}],'mappings':[],'attachments':[],
           'assumptions':['Stored SI thermophysical values; caller-declared material validity; explicitly selected constant entries' if names else 'Stored SI thermophysical values; caller-declared material validity; all entries reconstructed'],
           'limitations':['Variable/composite or spectral semantics and full TD qualification are outside this profile'],
           'audit':{'timestamp':'source-import'},'gui':{'selection':[]}}
    try:model=read('model',loads(encode(model)))
    except ContractError:reject('td_property_model_contract')
    return model,{'profile':'td-property-document/1','kind':kind,'selected_entries':len(selected),
                  'retained_unselected_entries':len(document.entries)-len(selected),'vendor_runtime_required':False,'qualified':False}


def optics_entity(entry,*,identifier=None):
    v=_values(entry,'rco')
    if any(v.get(k,0)!=0 for k in OPTICS|OPTICAL_FLAGS if k.startswith(('USE','VAR'))):reject('td_property_variable_optics_unmapped')
    v={'ALPHA':1,'EMISS':1,'SOLSPEC':0,'IRSPEC':0,'SOLTRANS':0,'IRTRANS':0,**v}
    if (v['SOLSPEC']!=v['IRSPEC'] or v['SOLTRANS']!=v['IRTRANS']
            or any(v.get(k,0)!=0 for k in ('SOLTSPEC','IRTSPEC'))
            or any(v.get(k,1)!=1 for k in ('SOLREFRAC','IRREFRAC'))):reject('td_property_spectral_or_refraction_unmapped')
    if any(not 0<=v[k]<=1 for k in ('ALPHA','EMISS','SOLSPEC','IRSPEC','SOLTRANS','IRTRANS')) or v['ALPHA']+v['SOLTRANS']>1 or v['EMISS']+v['IRTRANS']>1:reject('td_property_optical_range')
    return {'id':identifier or target_id(('td-property','optics',entry.name.casefold())),'kind':'optics','label':entry.name,
            'solar_absorptivity':v['ALPHA'],'ir_emissivity':v['EMISS'],'specular_fraction':v['SOLSPEC'],'transmissivity':v['SOLTRANS']}


def dependency_catalog(snapshot,files):
    """Resolve property-name references of decoded objects without guessing others."""
    from .td_decode import decode_drawing
    catalogs={};diagnostics=[];references=[]
    for name,raw in files:
        kind=Path(name).suffix.lower()[1:]
        if kind not in {'tdp','rco'}:continue
        try:doc=parse_properties(raw,kind)
        except ValueError:diagnostics.append({'code':'td_property_dependency_unreadable'});continue
        for entry in doc.entries:catalogs.setdefault((kind,entry.name.casefold()),[]).append((name,entry))
    for payload in decode_drawing(snapshot).payloads:
        f=payload.fields
        active=f.get('use_material',False) or ('law_selectors' in f and f['law_selectors'][0]!=0 and bool(f['material']))
        if not active:continue
        values=catalogs.get(('tdp',f['material'].casefold()),[])
        references.append({'handle':payload.record['handle'],'property_kind':'tdp',
                           'status':'resolved' if len(values)==1 else 'missing' if not values else 'ambiguous'})
    return {'profile':'td-property-dependencies/1','databases':sum(Path(n).suffix.lower() in {'.tdp','.rco'} for n,_ in files),
            'references':references,'diagnostics':diagnostics,'complete_for_decoded_material_references':not diagnostics and all(r['status']=='resolved' for r in references),
            'full_drawing_dependency_closure':False,'qualified':False}


def _property_model(model):
    try:model=read('model',loads(encode(deepcopy(model))))
    except (ContractError,TypeError,ValueError):reject('td_property_model_contract')
    if model['mappings'] or model['attachments'] or not model['entities']:reject('td_property_model_scope')
    for entity in model['entities']:
        kind=entity['kind']
        if kind not in {'material','optics'} or set(entity)-set(BUNDLE['schemas']['model']['$defs'][kind]['required'])-{'label'}:reject('td_property_model_scope')
    model['entities'].sort(key=lambda e:e['id']);return model


def render_library(model):
    model=_property_model(model);records={'tdp':[],'rco':[]};identities=[]
    def numeric(value):
        if not math.isfinite(value):reject('td_property_writer_number')
        return format(value,'.17g')
    for e in model['entities']:
        name='F'+e['id'].replace('-','');kind='tdp' if e['kind']=='material' else 'rco'
        fields=[('NAME',name)]
        if kind=='tdp':
            fields += [('TYPE',0),('CONDUCT',e['conductivity']['value']),('CONDUCTY',e['conductivity']['value']),
                       ('CONDUCTZ',e['conductivity']['value']),('DENSITY',e['density']['value']),('SPECHEAT',e['specific_heat']['value']),
                       ('DENSITYMULT',1),('KUMULT',1),('KVMULT',1),('KWMULT',1),('USEANISO',0),('EFFECTIVEEMISS',0)]
        else:
            fields += [('ALPHA',e['solar_absorptivity']),('EMISS',e['ir_emissivity']),('SOLSPEC',e['specular_fraction']),
                       ('IRSPEC',e['specular_fraction']),('SOLTRANS',e['transmissivity']),('IRTRANS',e['transmissivity']),
                       ('SOLTSPEC',0),('IRTSPEC',0),('SOLREFRAC',1),('IRREFRAC',1)]
            fields += [(tag,0) for tag in sorted(OPTICS) if tag.startswith(('USE','VAR'))]
        records[kind].append('[START]\r\n'+''.join('['+tag+']\r\n'+(value if isinstance(value,str) else numeric(value))+'\r\n' for tag,value in fields)+'[END]\r\n')
        identities.append({'entity_id':e['id'],'kind':e['kind'],'name':name})
    files={('materials.tdp' if kind=='tdp' else 'optics.rco'):b'\xef\xbb\xbf[UNICODE]\r\n'+''.join(rows).encode('utf-8') for kind,rows in records.items() if rows}
    return files,identities,model


def read_library_files(files):
    """Reconstruct the library and verify canonical companions, never trust them."""
    try:
        canonical=_property_model(loads(files['canonical.json']));meta=loads(files['property-map.json'])
        if set(meta)!={'profile','canonical_sha256','files','identities'} or meta['profile']!='td-property-library/1':reject('td_property_library_metadata')
        if sha256(encode(canonical)).hexdigest()!=meta['canonical_sha256']:reject('td_property_library_binding')
        if set(files)!={'canonical.json','property-map.json',*meta['files']}:reject('td_property_library_closure')
        if set(meta['files'])-{'materials.tdp','optics.rco'}:reject('td_property_library_path')
        docs={}
        for name,digest in meta['files'].items():
            if sha256(files[name]).hexdigest()!=digest:reject('td_property_library_binding')
            docs[Path(name).suffix[1:]]=parse_properties(files[name],Path(name).suffix[1:])
        native={e['id']:e for e in canonical['entities']};seen=set();source_seen=set()
        if len(meta['identities'])!=len(native):reject('td_property_library_inventory')
        for row in meta['identities']:
            if set(row)!={'entity_id','kind','name'} or row['entity_id'] in seen:reject('td_property_library_identity')
            expected=native[row['entity_id']];kind='tdp' if expected['kind']=='material' else 'rco'
            if row['kind']!=expected['kind'] or (kind,row['name']) in source_seen:reject('td_property_library_identity')
            source_seen.add((kind,row['name']));entry=next(e for e in docs[kind].entries if e.name==row['name'])
            actual=material_entity(entry,[q['value'] for q in expected['valid_temperature']],identifier=expected['id']) if kind=='tdp' else optics_entity(entry,identifier=expected['id'])
            actual.pop('label');wanted={k:v for k,v in expected.items() if k!='label'}
            if actual!=wanted:reject('td_property_library_semantic_mismatch')
            seen.add(row['entity_id'])
        if len(source_seen)!=sum(len(doc.entries) for doc in docs.values()):reject('td_property_library_inventory')
        return canonical
    except (KeyError,TypeError,AttributeError,StopIteration):reject('td_property_library_metadata')


def export_library(model,destination):
    files,identities,canonical=render_library(model);files['canonical.json']=encode(canonical)
    files['property-map.json']=encode({'profile':'td-property-library/1','canonical_sha256':sha256(files['canonical.json']).hexdigest(),
        'files':{name:sha256(raw).hexdigest() for name,raw in files.items() if name!='canonical.json'},'identities':identities})
    read_library_files(files)
    destination=Path(destination).absolute()
    if destination.exists() or not destination.parent.is_dir():reject('td_property_library_new_target')
    checked_path(destination.parent,destination.name);temporary=Path(tempfile.mkdtemp(prefix='.fcst-properties-',dir=destination.parent))
    try:
        for name,raw in files.items():
            with (temporary/name).open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        read_library_files({name:(temporary/name).read_bytes() for name in files});rename_new(temporary,destination)
    finally:
        if temporary.exists():
            if temporary.parent.resolve()!=destination.parent.resolve() or not temporary.name.startswith('.fcst-properties-'):reject('td_property_library_cleanup')
            shutil.rmtree(temporary)
    return {'operation':'td-write-properties','entities':len(identities),'independent_reopen_verified':True,
            'vendor_runtime_required':False,'qualified':False,'scope':'Constant isotropic material/equivalent-band optics; validity/annotations in verified canonical companion'}


def export_document_package(package,destination):
    """Apply native constant-property edits to the retained original document."""
    from fcst_app.persistence import Package
    from .vendor_paths import path_name
    if not isinstance(package,Package):reject('td_property_package_required')
    package=Package(package.manifest,package.files);target=_property_model(package.model)
    try:
        meta=loads(package.files['exchange/property-source-map.json'])
        if meta['profile']!='td-property-document/1' or len(meta['source_paths'])!=1:reject('td_property_document_package')
        name,alias=next(iter(meta['source_paths'].items()));path_name(name);kind=meta['report']['kind']
        sources={r['artifact']['path'] for r in package.manifest['artifacts'] if r['role'] in {'source_original','source_dependency'}}
        if sources!={alias}:reject('td_property_document_closure')
        raw=package.files[alias];document=parse_properties(raw,kind);selected=meta['entries']
        if not isinstance(selected,list) or not selected or len(set(selected))!=len(selected):reject('td_property_selection')
        entries=[entry for entry in document.entries if entry.name in selected]
        if len(entries)!=len(selected):reject('td_property_selection')
        expected_ids={target_id(('td-property','material' if kind=='tdp' else 'optics',e.name.casefold())) for e in entries}
        entities={e['id']:e for e in target['entities']}
        if expected_ids!=set(entities):reject('td_property_document_identity')
        changes=[]
        for entry in entries:
            identifier=target_id(('td-property','material' if kind=='tdp' else 'optics',entry.name.casefold()));entity=entities[identifier]
            if entity['kind']!=('material' if kind=='tdp' else 'optics') or entity.get('label')!=entry.name:reject('td_property_document_identity')
            if kind=='tdp':
                v=_values(entry,kind);material_entity(entry,[q['value'] for q in entity['valid_temperature']])
                fields={'DENSITY':entity['density']['value']/v.get('DENSITYMULT',1),'SPECHEAT':entity['specific_heat']['value'],
                        'CONDUCT':entity['conductivity']['value']/v.get('KUMULT',1)}
                defaults={'DENSITY':1,'SPECHEAT':1,'CONDUCT':1}
            else:
                v=_values(entry,kind);optics_entity(entry)
                fields={'ALPHA':entity['solar_absorptivity'],'EMISS':entity['ir_emissivity'],
                        'SOLSPEC':entity['specular_fraction'],'IRSPEC':entity['specular_fraction'],
                        'SOLTRANS':entity['transmissivity'],'IRTRANS':entity['transmissivity']}
                defaults={'ALPHA':1,'EMISS':1}
            changes.extend({'entry':entry.name,'field':tag,'value':value} for tag,value in fields.items() if value!=v.get(tag,defaults.get(tag,0)))
        derived,report=document.edited(changes) if changes else (raw,{'edited_fields':0,'reopen_verified':True})
        reopened=parse_properties(derived,kind)
        for entry in reopened.entries:
            if entry.name not in selected:continue
            identifier=target_id(('td-property','material' if kind=='tdp' else 'optics',entry.name.casefold()));expected=entities[identifier]
            actual=material_entity(entry,[q['value'] for q in expected['valid_temperature']],identifier=identifier) if kind=='tdp' else optics_entity(entry,identifier=identifier)
            if actual!=expected:reject('td_property_document_reopen_mismatch')
    except (KeyError,TypeError,AttributeError,ZeroDivisionError):reject('td_property_document_package')
    destination=Path(destination).absolute()
    if destination.exists() or not destination.parent.is_dir():reject('td_property_library_new_target')
    if Path(name).parts[0].casefold() in {'canonical.json','property-export.json'}:reject('td_property_document_path_collision')
    checked_path(destination.parent,destination.name);temporary=Path(tempfile.mkdtemp(prefix='.fcst-property-edit-',dir=destination.parent))
    try:
        path=temporary/name;path.parent.mkdir(parents=True,exist_ok=True)
        files={name:derived,'canonical.json':encode(target),'property-export.json':encode({'profile':'td-property-document-export/1',
            'source_sha256':sha256(raw).hexdigest(),'derived_sha256':sha256(derived).hexdigest(),'kind':kind,'entries':selected})}
        for filename,data in files.items():
            with (temporary/filename).open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        if any((temporary/filename).read_bytes()!=data for filename,data in files.items()):reject('td_property_document_publication_bytes')
        rename_new(temporary,destination)
    finally:
        if temporary.exists():
            if temporary.parent.resolve()!=destination.parent.resolve() or not temporary.name.startswith('.fcst-property-edit-'):reject('td_property_library_cleanup')
            shutil.rmtree(temporary)
    return {'operation':'td-export-property-source',**report,'vendor_runtime_required':False,'qualified':False,
            'original_unchanged':True,'canonical_roundtrip_verified':True,'scope':'Selected constant properties; unselected source data/comments preserved'}


def read_library(root):
    import os
    root=Path(root).absolute();files={};checked_path(root,'canonical.json')
    with os.scandir(root) as items:
        for item in items:
            if not item.is_file(follow_symlinks=False) or item.name not in {'canonical.json','property-map.json','materials.tdp','optics.rco'}:reject('td_property_library_closure')
            path=checked_path(root,item.name)
            with path.open('rb') as stream:raw=stream.read(1048577)
            if len(raw)>1048576:reject('td_property_library_limit')
            files[item.name]=raw
    return read_library_files(files),files
