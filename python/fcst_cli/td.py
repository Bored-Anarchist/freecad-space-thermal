# SPDX-License-Identifier: MIT OR Apache-2.0
import json
from pathlib import Path
from fcst_exchange.sinda import SindaAdapter,SindaUnits


def parsers(commands):
    commands.add_parser('td-probe')
    properties=commands.add_parser('td-write-properties');properties.add_argument('project');properties.add_argument('destination')
    properties_read=commands.add_parser('td-read-properties');properties_read.add_argument('root');properties_read.add_argument('destination')
    properties_import=commands.add_parser('td-import-properties')
    properties_import.add_argument('root');properties_import.add_argument('entry');properties_import.add_argument('destination')
    properties_import.add_argument('--kind',required=True,choices=['tdp','rco']);properties_import.add_argument('--temperature-min',type=float)
    properties_import.add_argument('--temperature-max',type=float);properties_import.add_argument('--name',action='append')
    property_export=commands.add_parser('td-export-property-source');property_export.add_argument('project');property_export.add_argument('destination')
    td_writer=commands.add_parser('td-write-model')
    td_writer.add_argument('project');td_writer.add_argument('destination')
    td_writer.add_argument('--backend',required=True);td_writer.add_argument('--work',required=True)
    native_export=commands.add_parser('td-export-native')
    native_export.add_argument('project');native_export.add_argument('destination')
    native_export.add_argument('--backend',required=True);native_export.add_argument('--work',required=True)
    writer=commands.add_parser('sinda-write-model')
    writer.add_argument('project');writer.add_argument('destination')
    for field in ('temperature','capacity','conductance','power','time'):
        writer.add_argument('--'+field+'-unit',required=True)
    for name in ('td-preview','td-export-source','td-audit-rewrite','td-package'):
        parser=commands.add_parser(name);parser.add_argument('root');parser.add_argument('entry')
        parser.add_argument('--backend',required=True);parser.add_argument('--work',required=True)
        if name!='td-preview':parser.add_argument('destination')
        if name=='td-export-source':parser.add_argument('--edits')
        for field in ('temperature','capacity','conductance','power','time'):
            parser.add_argument('--'+field+'-unit',required=name=='td-package')
    for name in ('sinda-preview','sinda-export','sinda-package','sinda-result'):
        parser=commands.add_parser(name);parser.add_argument('root');parser.add_argument('entry')
        parser.add_argument('--temperature-unit',required=True);parser.add_argument('--capacity-unit',required=True)
        parser.add_argument('--conductance-unit',required=True);parser.add_argument('--power-unit',required=True);parser.add_argument('--time-unit',required=True)
        if name in {'sinda-export','sinda-package'}:parser.add_argument('destination')
        if name=='sinda-result':parser.add_argument('result');parser.add_argument('time',type=float)


def execute(args):
    if args.command=='td-probe':
        from fcst_exchange.opentd import discover_runtime
        return discover_runtime().probe()
    if args.command=='td-write-properties':
        from fcst_app.persistence import recover_package
        from fcst_exchange.td_property_model import export_library
        return export_library(recover_package(args.project).model,args.destination)
    if args.command=='td-export-property-source':
        from fcst_app.persistence import recover_package
        from fcst_exchange.td_property_model import export_document_package
        return export_document_package(recover_package(args.project),args.destination)
    if args.command=='td-import-properties':
        from fcst_app.persistence import Package,encode,save_package
        from fcst_exchange.td_property_model import import_document
        from fcst_exchange.vendor_paths import checked_path
        from fcst_exchange.core import target_id,reject
        from hashlib import sha256
        if Path(args.destination).exists():reject('package_requires_new_target')
        with checked_path(Path(args.root),args.entry).open('rb') as stream:raw=stream.read(1048577)
        if len(raw)>1048576:reject('td_property_library_limit')
        if args.kind=='rco' and (args.temperature_min is not None or args.temperature_max is not None):reject('td_property_optics_temperature_interval_unmapped')
        bounds=[args.temperature_min,args.temperature_max] if args.kind=='tdp' else None
        model,report=import_document(raw,args.kind,bounds,names=args.name)
        source='source/'+sha256(args.entry.encode()).hexdigest()+'.original';files={'model.json':encode(model),source:raw,
            'exchange/property-source-map.json':encode({'profile':'td-property-document/1','source_paths':{args.entry:source},'report':report,
                'entries':[e['label'] for e in model['entities']]})}
        model_id=target_id(('property-document-model',model['project_id']));source_id=target_id(('property-document-original',args.entry));records=[]
        for name,data in files.items():
            records.append({'id':model_id if name=='model.json' else source_id if name==source else target_id(('property-document-evidence',name)),
                'role':'model' if name=='model.json' else 'source_original' if name==source else 'evidence',
                'artifact':{'path':name,'sha256':sha256(data).hexdigest(),'byte_length':len(data)},'dependencies':[source_id] if name=='model.json' else []})
        save_package(Package({'contract_version':'2.0.0','minimum_reader':'2.0.0','project_id':model['project_id'],'revision':0,'model_artifact_id':model_id,'artifacts':records},files),args.destination)
        return {'operation':'td-import-properties','status':'saved',**report}
    if args.command=='td-read-properties':
        from fcst_app.persistence import Package,encode,save_package
        from fcst_exchange.td_property_model import read_library
        from fcst_exchange.core import target_id,reject
        from hashlib import sha256
        if Path(args.destination).exists():reject('package_requires_new_target')
        model,originals=read_library(args.root);files={'model.json':encode(model)};records=[];source_ids=[];aliases={}
        for name,raw in originals.items():
            alias='source/'+sha256(name.encode()).hexdigest()+'.original';identifier=target_id(('property-original',name));source_ids.append(identifier);files[alias]=raw
            aliases[name]=alias
            records.append({'id':identifier,'role':'source_original','artifact':{'path':alias,'sha256':sha256(raw).hexdigest(),'byte_length':len(raw)},'dependencies':[]})
        map_name='exchange/property-source-map.json';files[map_name]=encode({'profile':'td-property-library/1','source_paths':aliases})
        records.append({'id':target_id(('property-evidence','source-map')),'role':'evidence',
                        'artifact':{'path':map_name,'sha256':sha256(files[map_name]).hexdigest(),'byte_length':len(files[map_name])},'dependencies':source_ids})
        identifier=target_id(('property-model',model['project_id']))
        records.append({'id':identifier,'role':'model','artifact':{'path':'model.json','sha256':sha256(files['model.json']).hexdigest(),'byte_length':len(files['model.json'])},'dependencies':source_ids})
        package=Package({'contract_version':'2.0.0','minimum_reader':'2.0.0','project_id':model['project_id'],'revision':model['revision'],'model_artifact_id':identifier,'artifacts':records},files)
        save_package(package,args.destination)
        return {'operation':'td-read-properties','status':'saved','entities':len(model['entities']),'vendor_runtime_required':False,'qualified':False}
    if args.command.startswith('td-'):
        from fcst_exchange.dwg_native import NativeRuntime
        from fcst_exchange.independent_td import IndependentTdAdapter
        runtime=NativeRuntime.from_receipt(args.backend)
        if args.command=='td-write-model':
            from fcst_app.persistence import recover_package
            from fcst_exchange.td_writer import export_model
            return export_model(recover_package(args.project).model,runtime,args.destination,args.work)
        if args.command=='td-export-native':
            from fcst_app.persistence import recover_package
            from fcst_exchange.source_package import export_td_package
            return export_td_package(recover_package(args.project),runtime,args.destination,args.work)
        unit_values=[getattr(args,field+'_unit') for field in ('temperature','capacity','conductance','power','time')]
        if any(unit_values) and not all(unit_values):
            from fcst_exchange.core import reject
            reject('td_native_all_units_required')
        units=SindaUnits(*unit_values) if all(unit_values) else None
        adapter=IndependentTdAdapter(runtime,units)
        staged=adapter.preview(args.root,args.entry,args.work)
        if args.command=='td-preview':return staged.report
        if args.command=='td-package':
            from fcst_app.persistence import save_package
            from fcst_exchange.source_package import package_td
            from fcst_exchange.core import reject
            if Path(args.destination).exists():reject('package_requires_new_target')
            save_package(package_td(staged),args.destination)
            return {'operation':'td-package','status':'saved','source_revision':staged.original.source_hash,'native_ready':True,'qualified':False}
        if args.command=='td-export-source':
            edits=()
            if args.edits:
                from fcst_contracts import loads
                from fcst_exchange.core import reject
                with Path(args.edits).open('rb') as stream:raw=stream.read(1048577)
                if len(raw)>1048576:reject('td_source_edit_file_limit')
                edits=loads(raw)
            return adapter.export_source(staged,args.destination,edits,work=Path(args.work).with_name(Path(args.work).name+'-export'))
        return adapter.audit_rewrite(staged,args.destination)
    units=SindaUnits(args.temperature_unit,args.capacity_unit,args.conductance_unit,args.power_unit,args.time_unit)
    if args.command=='sinda-write-model':
        from fcst_app.persistence import recover_package
        from fcst_exchange.sinda_writer import export_model
        return export_model(recover_package(args.project).model,units,args.destination)
    adapter=SindaAdapter(units);staged=adapter.preview(args.root,args.entry)
    if args.command=='sinda-preview':return staged.report
    if args.command=='sinda-export':return adapter.export(staged,args.destination)
    if args.command=='sinda-package':
        from fcst_exchange.source_package import package_sinda
        from fcst_app.persistence import save_package
        from fcst_exchange.core import reject
        if Path(args.destination).exists():reject('package_requires_new_target')
        package=package_sinda(staged);save_package(package,args.destination)
        return {'operation':'sinda-package','status':'saved','source_revision':staged.report['source_revision']}
    from fcst_exchange.sinda_results import read_print
    from fcst_exchange.results import query
    from fcst_exchange.vendor_paths import checked_path
    from fcst_exchange.core import reject
    with checked_path(Path(args.root),args.result).open('rb') as stream:raw=stream.read(16777217)
    if len(raw)>16777216:reject('sinda_result_limit')
    result=read_print(raw,staged.require_native(),quantity='temperature',unit=units.temperature,time_unit=units.time)
    return query(result,args.time)
