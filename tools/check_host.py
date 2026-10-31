# SPDX-License-Identifier: MIT OR Apache-2.0
"""Unattended installed-workbench acceptance on the exact pinned Windows host."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from profile_support import ROOT, run, revision
from install_workbench import install

sys.path.insert(0,str(ROOT/'python'))
from fcst_tools.gate import evaluate


def input_hashes():
    paths=[p for folder in ('python/fcst_host','python/fcst_app','python/fcst_contracts','freecad/FCST') for p in (ROOT/folder).rglob('*') if p.suffix in ('.py','.json')]
    paths += [ROOT/p for p in ('tools/check_host.py','tools/host_acceptance_payload.py','tools/install_workbench.py','tools/profile_support.py','tools/host_smoke.py','tools/host_smoke_payload.py','ci/host-acceptance.json','ci/host-reuse.json','ci/fem-reuse.json','ci/host-profile.json','tests/test_host.py','engine/src/contracts.cpp','tests/fixtures/contracts/network.json','tests/fixtures/spatial/solid-surface-rotated.json')]
    return {p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def assess(report, candidate, inputs, policy):
    if (report.get('candidate')!=candidate or report.get('input_sha256')!=inputs
            or report.get('gate',{}).get('status')!='passed'
            or evaluate(policy['required_cases'],report.get('cases',[]))['status']!='passed'
            or report.get('host_version')!=['1','1','4'] or report.get('python_abi')!='cp311'
            or report.get('spatial_solver_qualified') is not False):
        raise ValueError('host_acceptance_incomplete_or_stale')


def check(worker, report):
    report.unlink(missing_ok=True)
    frozen_inputs=input_hashes()
    import host_smoke
    host_smoke.main()
    policy=json.loads((ROOT/'ci/host-acceptance.json').read_bytes())
    profile=json.loads((ROOT/'ci/host-profile.json').read_bytes())
    folder=ROOT/'.local/wp13'/uuid.uuid4().hex; folder.mkdir(parents=True)
    (folder/'tmp').mkdir()
    addon=install(folder/'Mod')
    hosts=list((ROOT/'.local/host/Windows/bundle').rglob('FreeCAD.exe'))
    hosts=[p for p in hosts if p.parent.name.lower()=='bin']
    if len(hosts)!=1: raise ValueError('ambiguous_host')
    host=hosts[0]
    manifest=json.loads((ROOT/'ci/fem-reuse.json').read_bytes())
    for group in manifest['groups']:
        for entry in group['files']:
            raw=(host.parent.parent/entry['asset_path']).read_bytes()
            if sha256(raw).hexdigest()!=entry['sha256'] or sha256(b''.join(raw.splitlines(keepends=True)[:30])).hexdigest()!=entry['notice_sha256']:
                raise ValueError('host_source_license_mismatch')
    worker=Path(worker).resolve()
    identity=subprocess.run([str(worker),'--build-info'],capture_output=True,timeout=30)
    if identity.returncode or json.loads(identity.stdout)['source_revision']!=revision():
        raise ValueError('host_worker_candidate_mismatch')
    macro=folder/'acceptance.FCMacro'
    macro.write_text('import os\nfrom pathlib import Path\nexec(compile(Path(os.environ["FCST_HOST_PAYLOAD"]).read_text(encoding="utf-8"), "host_acceptance_payload.py", "exec"))\n')
    env=dict(os.environ,FCST_HOST_PAYLOAD=str(ROOT/'tools/host_acceptance_payload.py'),
        FCST_HOST_OUTPUT=str(folder),FCST_HOST_ADDON=str(addon),FCST_HOST_ROOT=str(ROOT),
        FCST_HOST_WORKER=str(worker),QT_QPA_PLATFORM='windows',OMP_NUM_THREADS='1',
        TEMP=str(folder/'tmp'),TMP=str(folder/'tmp'))
    for key in ('PYTHONPATH','PYTHONHOME'): env.pop(key,None)
    run([str(host),str(macro),'--user-cfg',str(folder/'user.cfg'),'--system-cfg',str(folder/'system.cfg')],
        folder,folder/'host.log',env=env,timeout=240)
    data=json.loads((folder/'host.json').read_bytes())
    if input_hashes()!=frozen_inputs:raise ValueError('host_sources_changed_during_acceptance')
    data.update(candidate=revision(),input_sha256=frozen_inputs,
        asset_sha256=profile['platforms']['Windows']['sha256'],worker_sha256=sha256(worker.read_bytes()).hexdigest())
    data['gate']=evaluate(policy['required_cases'],data['cases'])
    assess(data,revision(),input_hashes(),policy)
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(data,indent=2)+'\n')
    print('WP-13 installed host acceptance: passed',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',type=Path,required=True)
    parser.add_argument('--report',type=Path,default=ROOT/'.local/wp13/host.json')
    args=parser.parse_args()
    try: check(args.worker,args.report)
    except Exception:
        print('WP-13 host acceptance: failed; raw diagnostics retained locally')
        import traceback
        failure=ROOT/'.local/wp13/supervisor-error.log'; failure.parent.mkdir(parents=True,exist_ok=True)
        failure.write_text(traceback.format_exc())
        raise SystemExit(1)
