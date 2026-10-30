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


def check_report_schema():
    from jsonschema import Draft202012Validator
    from unittest.mock import patch
    import tempfile
    from fcst_exchange.independent_td import IndependentTdAdapter
    from fcst_exchange.dwg_native import NativeRuntime
    from fcst_exchange.source_package import package_td
    from fcst_exchange.sinda import SindaUnits
    from td_fixture import drawing,PATCH
    from test_td_native_model import records
    schema=json.loads((ROOT/'spec/schemas/exchange-fidelity-v1.schema.json').read_bytes())
    Draft202012Validator.check_schema(schema);validator=Draft202012Validator(schema)
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);source=root/'source';source.mkdir();(source/'main.dwg').write_bytes(b'AC1032-owned')
        runtime=NativeRuntime(root/'backend.exe','b'*64,PATCH)
        for units in (None,SindaUnits('K','J/K','W/K','W','s')):
            with patch.object(NativeRuntime,'run',return_value=(drawing(records()),None,{})):
                staged=IndependentTdAdapter(runtime,units).preview(source,'main.dwg',root/'preview')
            validator.validate(staged.fidelity)
            if units is not None:validator.validate(json.loads(package_td(staged).files['exchange/fidelity.json']))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path,default=ROOT/'.local/td.json')
    args=parser.parse_args();manifest=json.loads((ROOT/'ci/td-acceptance.json').read_bytes())
    coverage=json.loads((ROOT/'ci/coverage.json').read_bytes())
    expected=manifest['required_cases']
    if expected!=coverage['td_cases'] or len(set(expected))!=len(expected):raise ValueError('td_acceptance_drift')
    logs=args.report.parent/'td-logs';logs.mkdir(parents=True,exist_ok=True);records=[]
    for case in expected:
        if case=='td-report-schema':
            try:check_report_schema();status='passed'
            except Exception:status='failed'
            records.append({'id':case,'status':status});continue
        stream=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromName(case)
        result=unittest.TextTestRunner(stream=stream).run(suite)
        (logs/(case+'.log')).write_text(stream.getvalue(),encoding='utf-8')
        records.append({'id':case,'status':'passed' if result.wasSuccessful() and result.testsRun==1 and not result.skipped else 'failed'})
    paths=['ci/td-acceptance.json','ci/td-profiles.json','ci/independent-dwg-probe.json','spec/schemas/exchange-fidelity-v1.schema.json',
           'adapters/opentd63/Program.cs','tests/test_sinda.py','tests/test_opentd.py',
           'tests/test_independent_dwg.py','tests/test_native_dwg.py','tests/test_sinda_writer.py',
           'tests/test_td_payloads.py','tests/test_td_properties.py','tests/td_fixture.py','python/fcst_cli/td.py',
           'tests/test_td_native_model.py','tests/test_td_property_model.py','tests/test_td_property_laws.py','tests/test_sinda_arrays.py','tests/test_td_geometry.py','tests/td_geometry_fixture.py',
           'tools/probe_independent_dwg.py','ci/dwg-backend.json','python/fcst_exchange/dwg-profile.json',
           'tools/build_independent_dwg.py','tools/dwg_build_support.py']
    paths += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'adapters/libredwg').iterdir()) if p.is_file()]
    paths += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'python/fcst_exchange').glob('*.py'))]
    report={'schema_version':1,'work_package':'WP-08','candidate':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'gate':evaluate(expected,records),'cases':records,'input_sha256':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
            'scope':'Independent closed TD canonical-network import, portable persistence, scalar export, orthotropic/property-law exchange and complete rectangle/brick serialization; geometry physical bindings and full-model qualification pending',
            'qualified':False,'qualification_holds':manifest['qualification_holds']}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report['gate']));return 0 if report['gate']['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
