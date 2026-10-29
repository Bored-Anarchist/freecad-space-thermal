# SPDX-License-Identifier: MIT OR Apache-2.0
"""WP-08 vendor-independent acceptance; full thermal qualification remains open."""
import argparse
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'python'),str(ROOT/'tests')]
from fcst_tools.gate import evaluate


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path,default=ROOT/'.local/td.json')
    args=parser.parse_args();manifest=json.loads((ROOT/'ci/td-acceptance.json').read_bytes())
    coverage=json.loads((ROOT/'ci/coverage.json').read_bytes())
    expected=manifest['required_cases']
    if expected!=coverage['td_cases'] or len(set(expected))!=len(expected):raise ValueError('td_acceptance_drift')
    logs=args.report.parent/'td-logs';logs.mkdir(parents=True,exist_ok=True);records=[]
    for case in expected:
        stream=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromName(case)
        result=unittest.TextTestRunner(stream=stream).run(suite)
        (logs/(case+'.log')).write_text(stream.getvalue(),encoding='utf-8')
        records.append({'id':case,'status':'passed' if result.wasSuccessful() and result.testsRun==1 and not result.skipped else 'failed'})
    paths=['ci/td-acceptance.json','ci/td-profiles.json','ci/independent-dwg-probe.json',
           'adapters/opentd63/Program.cs','tests/test_sinda.py','tests/test_opentd.py',
           'tests/test_independent_dwg.py','tests/test_native_dwg.py','tests/test_sinda_writer.py',
           'tools/probe_independent_dwg.py','ci/dwg-backend.json','python/fcst_exchange/dwg-profile.json',
           'tools/build_independent_dwg.py','tools/dwg_build_support.py']
    paths += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'adapters/libredwg').iterdir()) if p.is_file()]
    paths += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'python/fcst_exchange').glob('*.py'))]
    report={'schema_version':1,'work_package':'WP-08','candidate':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'gate':evaluate(expected,records),'cases':records,'input_sha256':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
            'scope':'Independent SINDA import, preservation edits and new-model writer; direct native DWG container/source retention; optional reference contracts; TD thermal classes remain unmapped',
            'qualified':False,'qualification_holds':manifest['qualification_holds']}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report['gate']));return 0 if report['gate']['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
