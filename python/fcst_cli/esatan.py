# SPDX-License-Identifier: MIT OR Apache-2.0
"""ESATAN commands over owned direct readers; engineering output stays local."""
from pathlib import Path
from fcst_app.persistence import encode, recover_package, save_package
from fcst_contracts import loads
from fcst_exchange.core import reject
from fcst_exchange.esatan import EsatanAdapter, EsatanUnits


def parsers(commands):
    for name in ('esatan-preview','esatan-export','esatan-package','esatan-write-model','esatan-tmd-query'):
        p=commands.add_parser(name)
        if name in {'esatan-write-model','esatan-tmd-query'}: p.add_argument('project')
        else: p.add_argument('root'); p.add_argument('entry')
        if name in {'esatan-export','esatan-package','esatan-write-model'}: p.add_argument('destination')
        if name=='esatan-export': p.add_argument('--patches')
        if name=='esatan-tmd-query':
            p.add_argument('result'); p.add_argument('binding'); p.add_argument('time',type=float)
            p.add_argument('--attribute',choices=['Temperature','Total_Internal_Heat_Source'],default='Temperature')
            p.add_argument('--interpolation',choices=['none','linear','previous'],default='none')
            p.add_argument('--discontinuity',type=int,action='append',default=[])
            p.add_argument('--discontinuity-policy',choices=['error','previous'],default='error')
        else: p.add_argument('--source-version',choices=['2018-sp1','2020'],required=True)
        for field in ('temperature','capacity','conductance','power','time'):
            p.add_argument('--'+field+'-unit',required=True)
    p=commands.add_parser('esatan-native-inspect')
    p.add_argument('root'); p.add_argument('entry'); p.add_argument('destination')
    p.add_argument('--family',choices=['erg','ere','erk','xml','postprocess-xml'],required=True)
    p.add_argument('--source-version',choices=['2018-sp1','2020'],required=True)


def bounded(path,limit=1048576):
    with Path(path).open('rb') as stream: raw=stream.read(limit+1)
    if len(raw)>limit: reject('esatan_input_limit')
    return raw


def execute(args):
    if args.command=='esatan-native-inspect':
        from fcst_exchange.vendor_paths import checked_path
        from fcst_exchange.esatan_native import inspect_native,inspect_project_xml
        path=checked_path(Path(args.root),args.entry)
        if args.family=='postprocess-xml':
            from fcst_exchange.esatan_xml import inspect_postprocess_xml
            with path.open('rb') as stream: result=inspect_postprocess_xml(stream)
        else:
            raw=bounded(path,16777216)
            result=inspect_project_xml(raw) if args.family=='xml' else inspect_native(
                raw,family=args.family,source_version=args.source_version,path=args.entry).inventory
        destination=Path(args.destination)
        if destination.exists(): reject('esatan_requires_new_target')
        # Detailed expressions and identifiers are local data, never CI assets.
        with destination.open('xb') as stream: stream.write(encode(result))
        return {'operation':args.command,'runnable':False,'qualified':False,
                'source_sha256':result['source_sha256'],'status':'inspected'}
    units=EsatanUnits(*(getattr(args,k+'_unit') for k in ('temperature','capacity','conductance','power','time')))
    if args.command=='esatan-tmd-query':
        from fcst_exchange.esatan_results import TmdBinding,read_tmd
        from fcst_exchange.results import query
        data=loads(bounded(args.binding))
        try: binding=TmdBinding(**{**data,'models':tuple(tuple(row) for row in data['models']),
                                  'inactive_nodes':tuple(tuple(row) for row in data.get('inactive_nodes',()))})
        except (TypeError,KeyError,ValueError): reject('esatan_tmd_binding')
        result=read_tmd(bounded(args.result,67108864),recover_package(args.project).model,binding,units,
                        attribute=args.attribute,interpolation=args.interpolation,discontinuities=args.discontinuity)
        return query(result,args.time,discontinuity_policy=args.discontinuity_policy)
    if args.command=='esatan-write-model':
        from fcst_exchange.esatan_writer import export_model
        return export_model(recover_package(args.project).model,units,args.destination,source_version=args.source_version)
    adapter=EsatanAdapter(units,source_version=args.source_version)
    staged=adapter.preview(args.root,args.entry)
    if args.command=='esatan-preview':
        return {'operation':args.command,'runnable':staged.report['runnable'],'qualified':False,
                'source_revision':staged.report['source_revision'],'files':len(staged.sources),
                'records':len(staged.report['records']),'unresolved':len(staged.report['diagnostics'])}
    if args.command=='esatan-export':
        from fcst_exchange import Patch
        changes=loads(bounded(args.patches)) if args.patches else []
        if not isinstance(changes,list) or len(changes)>10000: reject('esatan_patch_list')
        patches=[]
        for change in changes:
            if not isinstance(change,dict) or set(change)!={'path','start','end','original_sha256','replacement_utf8'}:
                reject('esatan_patch_fields')
            if not isinstance(change['replacement_utf8'],str): reject('esatan_patch_fields')
            patches.append(Patch(change['path'],change['start'],change['end'],change['original_sha256'],change['replacement_utf8'].encode('utf-8')))
        return adapter.export(staged,args.destination,patches)
    if args.command=='esatan-package':
        from fcst_exchange.export import source_package
        if Path(args.destination).exists(): reject('esatan_requires_new_target')
        save_package(source_package(staged),args.destination)
        return {'operation':args.command,'status':'saved','source_revision':staged.report['source_revision'],'qualified':False}
    reject('esatan_command')
