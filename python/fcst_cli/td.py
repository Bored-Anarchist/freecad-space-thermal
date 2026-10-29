# SPDX-License-Identifier: MIT OR Apache-2.0
import json
from pathlib import Path
from fcst_exchange.sinda import SindaAdapter,SindaUnits


def parsers(commands):
    commands.add_parser('td-probe')
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
    units=SindaUnits(args.temperature_unit,args.capacity_unit,args.conductance_unit,args.power_unit,args.time_unit)
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
