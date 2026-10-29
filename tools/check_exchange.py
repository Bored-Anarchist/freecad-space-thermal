# SPDX-License-Identifier: MIT OR Apache-2.0
"""Unattended WP-07 acceptance; only bounded synthetic verdicts leave local storage."""
import argparse
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/"python"),str(ROOT/"tests")]
from fcst_tools.gate import evaluate


def schema_case(schema):
    from jsonschema import Draft202012Validator
    from fcst_exchange import preview
    from fcst_exchange.core import STATUSES
    from test_exchange import network, line
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)/"main.txt"
        for raw in (network(),network()+b"FUTURE opaque\n",network()+b"ENTITY {bad}\n",
                    network()+line("INCLUDE",{"path":"missing.txt"})):
            path.write_bytes(raw)
            report = preview(tmp,"main.txt",dialect="fcst-network/1").report
            validator.validate(report)
            # Every defined status has an independent schema representation.
            for status in STATUSES:
                report["records"][0]["status"] = status
                validator.validate(report)
            report["records"][0]["status"] = "executable-compatible"
            if validator.is_valid(report):
                raise ValueError("status_conflation")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report",type=Path,default=ROOT/".local/exchange.json")
    args = parser.parse_args()
    register = json.loads((ROOT/"ci/exchange-acceptance.json").read_bytes())
    coverage = json.loads((ROOT/"ci/coverage.json").read_bytes())
    output = args.report.parent/"exchange-logs"
    output.mkdir(parents=True,exist_ok=True)
    records = []
    expected = register["required_cases"]
    if (expected != coverage["exchange_cases"] or len(set(expected)) != len(expected)
            or not all(register["requirements"].values())
            or any(not set(cases) <= set(expected) for cases in register["requirements"].values())):
        raise ValueError("exchange_acceptance_drift")
    for case in expected:
        stream = io.StringIO()
        if case == "exchange-report-schema":
            try:
                schema_case(json.loads((ROOT/register["schema"]).read_bytes()))
                passed = True
            except Exception:
                # No raw source paths or reader exceptions in public evidence.
                import traceback
                traceback.print_exc(file=stream)
                passed = False
        else:
            suite = unittest.defaultTestLoader.loadTestsFromName(case)
            result = unittest.TextTestRunner(stream=stream).run(suite)
            passed = result.wasSuccessful() and result.testsRun == 1 and not result.skipped
        (output/(case+".log")).write_text(stream.getvalue(),encoding="utf-8")
        records.append({"id":case,"status":"passed" if passed else "failed"})
    verdict = evaluate(expected,records)
    paths = ["ci/exchange-acceptance.json",register["schema"]]
    paths += [p.relative_to(ROOT).as_posix() for directory in (ROOT/"python/fcst_exchange",) for p in sorted(directory.glob("*.py"))]
    paths += ["python/fcst_cli/exchange.py","tests/test_exchange.py","tests/test_exchange_tools.py","tests/fixtures/exchange_converter.py"]
    candidate = subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    report = {"schema_version":1,"work_package":"WP-07","candidate":candidate,"profile":register["profile"],
              "scope":register["qualification"],"input_sha256":{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
              "gate":verdict,"cases":records}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(verdict))
    return 0 if verdict["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
