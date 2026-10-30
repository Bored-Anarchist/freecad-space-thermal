# SPDX-License-Identifier: MIT OR Apache-2.0
"""Inert locked-original inspection. No raw models, identifiers or values in reports."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from fcst_exchange import ExchangeError
from fcst_exchange.esatan import EsatanAdapter,EsatanUnits
from fcst_exchange.esatan_native import inspect_native,inspect_project_xml
from fcst_exchange.esatan_results import inspect_tmd
from fcst_exchange.esatan_xml import inspect_postprocess_xml


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,default=ROOT/'.local/esatan-originals.json')
    parser.add_argument('--resolved-xml',type=Path,help='Separately preserved resolved LFS payload; the original pointer remains immutable')
    args=parser.parse_args()
    lock=json.loads((ROOT/'inventory/source-lock.json').read_bytes())
    cases=[]
    for row in lock['files']:
        if not row['source_id'].startswith('ESA-'): continue
        path=ROOT/'.local/corpus/originals'/row['source_id']/row['path']
        family=path.suffix.lower().removeprefix('.')
        if family not in {'erg','ere','erk','xml','tpl','d','tmd'}: continue
        case={'id':'ESA-ORIGINAL-'+str(len(cases)+1).zfill(3),'family':family,'qualified':False}
        try:
            raw=path.read_bytes()
            if sha256(raw).hexdigest()!=row['sha256']: raise ExchangeError('original_hash_mismatch')
            case['source_sha256']=row['sha256']; case['bytes']=len(raw)
            version='2018-sp1' if row['source_id']=='ESA-DISC-TUTORIAL' else '2020'
            if family in {'erg','ere','erk'}:
                inventory=inspect_native(raw,family=family,source_version=version,path='original.'+family).inventory
                case.update(status='inspected',records=len(inventory['records']),unresolved=len(inventory['diagnostics']),runnable=False)
            elif family=='xml':
                if args.resolved_xml:
                    profile=json.loads((ROOT/'ci/esatan-acquisition.json').read_bytes())
                    if sha256(raw).hexdigest()!=profile['pointer_sha256']: raise ExchangeError('original_pointer_mismatch')
                    with args.resolved_xml.open('rb') as stream: inventory=inspect_postprocess_xml(stream)
                    if inventory['source_sha256']!=profile['payload_sha256'] or inventory['bytes']!=profile['payload_bytes']:
                        raise ExchangeError('resolved_xml_hash_mismatch')
                    case.update(status='inspected',runnable=False,payload_sha256=inventory['source_sha256'],
                                elements=inventory['elements'],content_role='postprocessing-xml')
                else:
                    inspect_project_xml(raw); case.update(status='inspected',runnable=False)
            elif family=='tmd':
                inventory=inspect_tmd(raw)
                case.update(status='inspected',groups=inventory['groups'],datasets=inventory['datasets'],runnable=False)
            else:
                staged=EsatanAdapter(EsatanUnits('degC','J/K','W/K','W','s'),source_version=version).preview(path.parent,path.name)
                case.update(status='inspected',records=len(staged.report['records']),unresolved=len(staged.report['diagnostics']),runnable=staged.report['runnable'])
        except (OSError,ValueError) as error:
            case.update(status='held',reason=error.code if isinstance(error,ExchangeError) else 'original_inspection_unavailable')
        cases.append(case)
    report={'schema_version':1,'work_package':'WP-09','scope':'Locked original syntax and safe-container inspection only',
            'cases':cases,'qualified':False,'status':'inspected' if cases else 'failed'}
    args.report.parent.mkdir(parents=True,exist_ok=True); args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'cases':len(cases),'held':sum(c['status']=='held' for c in cases),'qualified':False}))
    return 0 if cases else 1


if __name__=='__main__': raise SystemExit(main())
