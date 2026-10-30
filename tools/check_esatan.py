# SPDX-License-Identifier: MIT OR Apache-2.0
"""Unattended WP-09 implementation acceptance; full Q1 claims remain held."""
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


def schema_case():
    import tempfile
    from jsonschema import Draft202012Validator
    from fcst_exchange.esatan import EsatanAdapter
    from esatan_fixture import NETWORK,UNITS
    schema=json.loads((ROOT/'spec/schemas/exchange-fidelity-v1.schema.json').read_bytes())
    validator=Draft202012Validator(schema)
    with tempfile.TemporaryDirectory() as directory:
        p=Path(directory); (p/'main.d').write_bytes(NETWORK)
        for raw in (NETWORK,NETWORK.replace(b'GL(1,2)',b'GR(1,2)')):
            (p/'main.d').write_bytes(raw)
            validator.validate(EsatanAdapter(UNITS,source_version='2018-sp1').preview(p,'main.d').report)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,default=ROOT/'.local/esatan.json')
    args=parser.parse_args()
    manifest=json.loads((ROOT/'ci/esatan-acceptance.json').read_bytes())
    coverage=json.loads((ROOT/'ci/coverage.json').read_bytes())
    expected=manifest['required_cases']
    if expected!=coverage['esatan_cases'] or len(set(expected))!=len(expected): raise ValueError('esatan_acceptance_drift')
    logs=args.report.parent/'esatan-logs'; logs.mkdir(parents=True,exist_ok=True); records=[]
    for case in expected:
        if case=='esatan-report-schema':
            try: schema_case(); status='passed'
            except Exception: status='failed'
        else:
            stream=io.StringIO(); suite=unittest.defaultTestLoader.loadTestsFromName(case)
            result=unittest.TextTestRunner(stream=stream).run(suite)
            (logs/(case+'.log')).write_text(stream.getvalue(),encoding='utf-8')
            status='passed' if result.wasSuccessful() and result.testsRun==1 and not result.skipped else 'failed'
        records.append({'id':case,'status':status})
    paths=['ci/esatan-acceptance.json','ci/esatan-profiles.json','ci/esatan-acquisition.json','tests/esatan_fixture.py','tests/esatan_offline_peer.py',
           'tests/esatan_result_acceptance.py','tests/test_esatan.py','python/fcst_cli/esatan.py','python/fcst_cli/__main__.py',
           'tests/test_esatan_xml.py','tools/check_esatan.py','tools/acquire_esatan_xml.py','tools/probe_esatan.py',
           'spec/schemas/exchange-fidelity-v1.schema.json']
    paths += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'python/fcst_exchange').glob('*.py'))]
    report={'schema_version':1,'work_package':'WP-09',
            'candidate':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'gate':evaluate(expected,records),'cases':records,
            'input_sha256':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
            'scope':manifest['scope'],'qualified':False,'qualification_holds':manifest['qualification_holds']}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report['gate']))
    return 0 if report['gate']['status']=='passed' else 1


if __name__=='__main__': raise SystemExit(main())
