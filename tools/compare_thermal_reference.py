# SPDX-License-Identifier: MIT OR Apache-2.0
"""Restricted offline comparison; raw source/result/receipt artifacts stay local."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from fcst_contracts import loads
from fcst_tools.thermal_qualification import captured_reference,require


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path)
    parser.add_argument('--worker',type=Path)
    parser.add_argument('--report',type=Path,default=ROOT/'.local/thermal-reference.json')
    args=parser.parse_args()
    candidate=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    report={'schema_version':1,'candidate':candidate,'status':'blocked','vendor_qualified':False,'q1_qualified':False,
            'reason':'approved_reference_pair_unavailable'}
    if args.manifest:
        try:
            require(args.worker is not None)
            worker=args.worker.resolve();env={k:v for k,v in os.environ.items() if k.upper() not in
                {'PYTHONPATH','PYTHONHOME','FREECAD_LIB','FREECAD_USER_HOME','SINDAPATH','ESATAN'}}
            env['PATH']=str(worker.parent)
            build=subprocess.run([str(worker),'--build-info'],capture_output=True,env=env,timeout=30)
            info=loads(build.stdout)
            require(build.returncode==0 and not build.stderr and info['engine']=='fcst_native'
                    and info['source_revision']==candidate and info['transient_available'] is True)
            def native(request):
                result=subprocess.run([str(worker),'--thermal-transient'],input=json.dumps(request,allow_nan=False).encode(),
                                      capture_output=True,env=env,timeout=300)
                require(len(result.stdout)<=67108864)
                def pairs(items):
                    output={}
                    for key,value in items:
                        require(key not in output);output[key]=value
                    return output
                output=json.loads(result.stdout.decode('utf-8'),object_pairs_hook=pairs,
                                  parse_constant=lambda value:require(False))
                require(result.returncode==0 and not result.stderr and output['status']=='passed')
                return output
            from fcst_exchange.vendor_paths import checked_path
            path=checked_path(args.manifest.absolute().parent,args.manifest.name)
            with path.open('rb') as stream:raw=stream.read(1048577)
            manifest=loads(raw)
            criteria=json.loads((ROOT/'ci/thermal-qualification-v1.json').read_bytes())
            report.update(status='passed',reason='comparison_only_reviewed_licensed_profile_admission_required',
                          comparison=captured_reference(manifest,path.parent,native,criteria),
                          manifest_sha256=sha256(raw).hexdigest(),worker_sha256=sha256(worker.read_bytes()).hexdigest())
        except (ValueError,TypeError,KeyError,OSError,subprocess.SubprocessError):
            report.update(status='failed',reason='reference_contract_or_execution_failed')
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'status':report['status'],'reason':report['reason'],'vendor_qualified':False,'q1_qualified':False}))
    return {'passed':0,'failed':1,'blocked':2}[report['status']]


if __name__=='__main__':raise SystemExit(main())
