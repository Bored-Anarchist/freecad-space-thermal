# SPDX-License-Identifier: MIT OR Apache-2.0
"""Run required security/coverage cases without exposing raw failure tracebacks."""
import io
import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from fcst_tools.gate import evaluate
from fcst_tools.verification import unit_inputs
from profile_support import revision

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("all", "security"), default="all")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    frozen_inputs = unit_inputs(ROOT)
    manifest_hash = hashlib.sha256((ROOT / "ci/coverage.json").read_bytes()).hexdigest()
    candidate = revision()
    if args.report:
        args.report.unlink(missing_ok=True)
    output = ROOT / ".local/security"
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / "tmp"
    temporary.mkdir(exist_ok=True)
    os.environ.update(TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary))
    tempfile.tempdir = str(temporary)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    def flatten(items):
        for test in items:
            if isinstance(test, unittest.TestSuite):
                yield from flatten(test)
            else:
                yield test
    records = []
    security_modules = ("test_privacy.", "test_gate.", "test_validation_boundary.", "test_ci_performance.")
    for test in flatten(suite):
        if args.scope == "security" and not test.id().startswith(security_modules):
            continue
        case_started = time.monotonic()
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream).run(unittest.TestSuite([test]))
        (output / (test.id() + ".log")).write_text(stream.getvalue(), encoding="utf-8")
        records.append({"id": test.id(), "status": "passed" if result.wasSuccessful() and not result.skipped else "failed",
                        "seconds": round(time.monotonic() - case_started, 3)})
    expected = json.loads((ROOT / "ci/coverage.json").read_text())["unit_cases"]
    if args.scope == "security":
        expected = [case for case in expected if case.startswith(security_modules)]
    verdict = evaluate(expected, records)
    if frozen_inputs != unit_inputs(ROOT):
        print("Unit inputs changed during verification")
        raise SystemExit(1)
    if args.report:
        report = dict(scope="unit-tests" if args.scope == "all" else "security-tests", candidate=candidate,
                      coverage_manifest_sha256=manifest_hash, input_sha256=frozen_inputs,
                      gate=verdict, cases=records, seconds=round(time.monotonic() - started, 3))
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"gate": verdict, "cases": records}))
    raise SystemExit(0 if verdict["status"] == "passed" else 1)
