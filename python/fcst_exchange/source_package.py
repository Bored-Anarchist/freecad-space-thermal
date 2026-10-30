# SPDX-License-Identifier: MIT OR Apache-2.0
"""Vendor names map to safe package paths; exact original bytes stay unchanged."""
from hashlib import sha256
from pathlib import Path
from fcst_app.persistence import Package,encode
from .core import target_id,reject


def package_sinda(staged):
    model=staged.require_native()
    files={'model.json':encode(model),'exchange/fidelity.json':staged.report_bytes}
    aliases={source.path:'source/'+sha256(source.path.encode()).hexdigest()+'.original' for source in staged.sources}
    ids={name:target_id(('vendor-original',name)) for name in aliases}
    graph={row['path']:row['includes'] for row in staged.report['dependencies']}
    records=[]
    for source in staged.sources:
        name=aliases[source.path];files[name]=source.content
        records.append({'id':ids[source.path],'role':'source_original' if source.path==staged.entry else 'source_dependency',
                        'artifact':{'path':name,'sha256':sha256(source.content).hexdigest(),'byte_length':len(source.content)},
                        'dependencies':[ids[child] for child in graph[source.path]]})
    files['exchange/source-map.json']=encode({'source_paths':aliases,'source_revision':staged.report['source_revision']})
    model_id=target_id(('vendor-model',model['project_id']))
    for name in ('model.json','exchange/fidelity.json','exchange/source-map.json'):
        records.append({'id':model_id if name=='model.json' else target_id(('vendor-evidence',name)),
                        'role':'model' if name=='model.json' else 'evidence',
                        'artifact':{'path':name,'sha256':sha256(files[name]).hexdigest(),'byte_length':len(files[name])},
                        'dependencies':list(ids.values()) if name=='model.json' else []})
    return Package({'contract_version':'2.0.0','minimum_reader':'2.0.0','project_id':model['project_id'],'revision':model['revision'],
                    'model_artifact_id':model_id,'artifacts':records},files)


def package_td(staged):
    """Store the complete source closure and an independently reconstructed model."""
    model=staged.require_native();staged.original.check_current()
    original=staged.original;files={'model.json':encode(model),'exchange/fidelity.json':encode(staged.fidelity)}
    aliases={name:'source/'+sha256(name.encode()).hexdigest()+'.original' for name,_ in original.files}
    source_ids={name:target_id(('td-original',name)) for name in aliases};records=[]
    for name,raw in original.files:
        alias=aliases[name];files[alias]=raw
        records.append({'id':source_ids[name],'role':'source_original' if name==original.entry else 'source_dependency',
                        'artifact':{'path':alias,'sha256':sha256(raw).hexdigest(),'byte_length':len(raw)},'dependencies':[]})
    files['exchange/td-source-map.json']=encode({'profile':'td-portable-source/1','entry':original.entry,
        'source_paths':aliases,'directories':list(original.directories),'source_revision':original.source_hash,
        'units':dict(staged.units.__dict__)})
    model_id=target_id(('td-native-model',model['project_id']))
    for name in ('model.json','exchange/fidelity.json','exchange/td-source-map.json'):
        records.append({'id':model_id if name=='model.json' else target_id(('td-evidence',name)),
                        'role':'model' if name=='model.json' else 'evidence',
                        'artifact':{'path':name,'sha256':sha256(files[name]).hexdigest(),'byte_length':len(files[name])},
                        'dependencies':list(source_ids.values()) if name=='model.json' else []})
    return Package({'contract_version':'2.0.0','minimum_reader':'2.0.0','project_id':model['project_id'],'revision':model['revision'],
                    'model_artifact_id':model_id,'artifacts':records},files)


def restore_td(package,destination):
    """Restore exact source bytes safely; manifests never supply executable paths."""
    import tempfile,shutil
    from .source_tree import ProjectCopy,ProjectLimits,capture_project
    from .vendor_paths import path_name,checked_path
    from .sinda import SindaUnits
    from fcst_contracts import loads
    if not isinstance(package,Package):reject('td_portable_package_required')
    package=Package(package.manifest,package.files)
    try:
        meta=loads(package.files['exchange/td-source-map.json'])
        if set(meta)!={'profile','entry','source_paths','directories','source_revision','units'} or meta['profile']!='td-portable-source/1':reject('td_portable_metadata')
        if not isinstance(meta['units'],dict) or set(meta['units'])!={'temperature','capacity','conductance','power','time'}:reject('td_portable_units')
        units=SindaUnits(**meta['units']);aliases=meta['source_paths'];directories=meta['directories'];entry=path_name(meta['entry'])
        if not isinstance(aliases,dict) or not aliases or not isinstance(directories,list):reject('td_portable_metadata')
        source_records={r['artifact']['path'] for r in package.manifest['artifacts'] if r['role'] in {'source_original','source_dependency'}}
        if set(aliases.values())!=source_records or len(set(aliases.values()))!=len(aliases) or entry not in aliases:reject('td_portable_closure')
        limits=ProjectLimits()
        if len(aliases)+len(directories)>limits.files*4:reject('td_portable_limit')
        seen=set()
        for name in [*aliases,*directories]:
            path_name(name)
            if len(Path(name).parts)>limits.include_depth:reject('td_portable_limit')
            if name.casefold() in seen:reject('td_portable_path_collision')
            seen.add(name.casefold())
        files=tuple(sorted((name,package.files[alias]) for name,alias in aliases.items()))
        if not dict(files)[entry].startswith(b'AC1032'):reject('td_portable_drawing')
        if len(files)>limits.files or len(directories)>limits.files*4 or any(len(raw)>limits.file_bytes for _,raw in files) or sum(len(raw) for _,raw in files)>limits.total_bytes:reject('td_portable_limit')
    except (KeyError,TypeError,AttributeError):reject('td_portable_metadata')
    destination=Path(destination).absolute()
    if destination.exists() or not destination.parent.is_dir():reject('td_portable_new_target')
    checked_path(destination.parent,destination.name)
    temporary=Path(tempfile.mkdtemp(prefix='.fcst-td-restore-',dir=destination.parent))
    try:
        for name in directories:(temporary/name).mkdir(parents=True,exist_ok=True)
        for name,raw in files:
            path=checked_path(temporary,name);path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:stream.write(raw)
        current=capture_project(temporary,entry)
        if current.files!=files or current.directories!=tuple(sorted(directories)) or current.source_hash!=meta['source_revision']:reject('td_portable_source_revision')
        current.copy_to(destination)
    finally:
        if temporary.exists():
            if temporary.parent.resolve()!=destination.parent.resolve() or not temporary.name.startswith('.fcst-td-restore-'):reject('td_portable_cleanup')
            shutil.rmtree(temporary)
    return entry,units


def export_td_package(package,runtime,destination,work):
    from fcst_app.persistence import is_link
    from .independent_td import IndependentTdAdapter
    if not isinstance(package,Package):reject('td_portable_package_required')
    package=Package(package.manifest,package.files)
    work=Path(work).absolute();destination=Path(destination).absolute()
    if (work.exists() or not work.parent.is_dir() or any(is_link(p) for p in (work,*work.parents))
            or work.resolve().is_relative_to(destination.resolve()) or destination.resolve().is_relative_to(work.resolve())):reject('td_portable_work_tree')
    work.mkdir();entry,units=restore_td(package,work/'source')
    adapter=IndependentTdAdapter(runtime,units);staged=adapter.preview(work/'source',entry,work/'preview')
    return adapter.export_native(staged,package.model,destination,work/'edit')
