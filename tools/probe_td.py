# SPDX-License-Identifier: MIT OR Apache-2.0
"""Local discovery and optional offline installed-API smoke; never opens a DWG."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from fcst_exchange.opentd import discover_runtime,build_sidecar,run_sidecar,PROFILE
from fcst_exchange.core import ExchangeError
from fcst_exchange.td_qualification import assess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-smoke',action='store_true')
    parser.add_argument('--require-qualified',action='store_true')
    parser.add_argument('--report',type=Path,default=ROOT/'.local/td-probe.json')
    args=parser.parse_args();runtime=discover_runtime();probe=runtime.probe()
    candidate=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    report={'work_package':'WP-08','candidate':candidate,'discovery':probe,
            'scope':'Installation metadata and optional offline API smoke only; no DWG open or vendor solve',
            'qualified':False,'qualification':assess([],candidate=candidate),'api_smoke':{'status':'not_requested'}}
    if args.api_smoke:
        work=ROOT/'.local/opentd63';work.mkdir(exist_ok=True)
        try:
            build=build_sidecar(runtime,ROOT/'adapters/opentd63/Program.cs',work/'fcst-opentd63.exe')
            with tempfile.TemporaryDirectory(prefix='api-smoke-',dir=work) as job:
                response,receipt=run_sidecar(runtime,work/'fcst-opentd63.exe',job,{'profile':PROFILE,'operation':'api-smoke'})
                from fcst_exchange.td_project import capture_project,inventory
                fixture=Path(job)/'offline-dto';fixture.mkdir()
                (fixture/'synthetic.dwg').write_bytes(b'AC1032 synthetic offline DTO fixture; not a real drawing')
                data={'profile':PROFILE,'api':response['api'],'units':'SI','collections':{'Nodes':[response['node_example']]},
                      'dependency_paths':{},'qualified':False,'execution_mode':'reference_external'}
                mapped=inventory(capture_project(fixture,'synthetic.dwg'),data)
                if not mapped.report['runnable']:raise ExchangeError('offline_api_node_mapping_failed')
                node_hash=sha256(mapped.model_bytes).hexdigest()
            report['api_smoke']={'status':'passed','build':build,'receipt':receipt,'offline_node_mapping_sha256':node_hash,'scope':response['scope']}
        except (ExchangeError,OSError,subprocess.SubprocessError) as error:
            report['api_smoke']={'status':'blocked','code':str(error) if isinstance(error,ExchangeError) else 'api_smoke_unavailable'}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'profile':PROFILE,'api_available':probe['api_available'],'host_available':probe['host_installed'],
                      'api_smoke':report['api_smoke']['status'],'qualified':False,'blockers':probe['blockers']}))
    if args.require_qualified:return 1
    return 1 if args.api_smoke and report['api_smoke']['status']!='passed' else 0


if __name__=='__main__':raise SystemExit(main())
