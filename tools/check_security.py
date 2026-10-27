# SPDX-License-Identifier: MIT OR Apache-2.0
"""Run required security/coverage cases without exposing raw failure tracebacks."""
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from fcst_tools.gate import evaluate

if __name__ == "__main__":
    output = ROOT / ".local/security"
    output.mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    def flatten(items):
        for test in items:
            if isinstance(test, unittest.TestSuite):
                yield from flatten(test)
            else:
                yield test
    records = []
    for test in flatten(suite):
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream).run(unittest.TestSuite([test]))
        (output / (test.id() + ".log")).write_text(stream.getvalue(), encoding="utf-8")
        records.append({"id": test.id(), "status": "passed" if result.wasSuccessful() and not result.skipped else "failed"})
    expected = json.loads((ROOT / "ci/coverage.json").read_text())["unit_cases"]
    verdict = evaluate(expected, records)
    print(json.dumps({"gate": verdict, "cases": records}))
    raise SystemExit(0 if verdict["status"] == "passed" else 1)
