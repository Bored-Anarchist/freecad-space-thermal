# SPDX-License-Identifier: MIT OR Apache-2.0
"""Restricted local synthetic reference runner; never a public-PR vendor job."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from fcst_exchange.core import ExchangeError
from fcst_exchange.opentd import Runtime,HostAuthorization,discover_runtime,build_sidecar
from fcst_exchange.td_reference import run_reference
from fcst_exchange.td_qualification import assess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-profile',type=Path)
    parser.add_argument('--work',type=Path,default=ROOT/'.local/td-reference-attempt')
    parser.add_argument('--report',type=Path,default=ROOT/'.local/td-reference.json')
    args=parser.parse_args();candidate=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    runtime=discover_runtime();profile={}
    if args.private_profile:
        profile=json.loads(args.private_profile.read_bytes())
        allowed={'host','decision_id','reviewed_sidecar_sha256','source_open_policy_sha256','outputs'}
        if set(profile)!=allowed:raise ValueError('private_profile_fields')
        runtime=Runtime(runtime.assembly,runtime.compiler,Path(profile['host']).absolute(),runtime.sinda)
    report={'work_package':'WP-08','candidate':candidate,'status':'blocked','qualified':False,
            'runtime':runtime.probe(),'qualification':assess([],candidate=candidate),
            'scope':'FCST-owned synthetic vendor reference; never owned-engine or full Q1 qualification'}
    if not runtime.probe()['available']:report['reason']='licensed_runtime_prerequisite'
    elif not profile:report['reason']='reviewed_private_host_profile_required'
    else:
        try:
            build_root=ROOT/'.local/opentd63';build_root.mkdir(exist_ok=True)
            executable=build_root/'fcst-opentd63.exe'
            build_sidecar(runtime,ROOT/'adapters/opentd63/Program.cs',executable)
            if sha256(executable.read_bytes()).hexdigest()!=profile['reviewed_sidecar_sha256']:raise ValueError('reviewed_sidecar_changed')
            authorization=HostAuthorization(profile['decision_id'],profile['reviewed_sidecar_sha256'],sha256(b'fcst-synthetic-reference/1').hexdigest(),
                                             profile['source_open_policy_sha256'],'fcst-synthetic-reference/1')
            criteria=json.loads((ROOT/'ci/td-reference-criteria-v1.json').read_bytes())
            report['reference']=run_reference(runtime,executable,args.work,authorization,profile['outputs'],criteria)
            report['status']='passed'
        except (ExchangeError,OSError,ValueError,subprocess.SubprocessError) as error:
            report['status']='failed';report['reason']=str(error) if isinstance(error,ExchangeError) else 'reference_prerequisite_or_execution_failed'
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'qualified':False,'reason':report.get('reason','external_reference_only')}))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
