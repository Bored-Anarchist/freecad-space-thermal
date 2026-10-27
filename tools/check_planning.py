# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded CI console output; raw validation diagnostics stay in local storage."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    output = ROOT / ".local/planning"
    output.mkdir(parents=True, exist_ok=True)
    passed = True
    for name, script in [("plan", "plans/tools/validate_plan.py"), ("specification", "spec/tools/validate_spec.py"),
                         ("workflows", "tools/check_workflows.py")]:
        try:
            with (output / (name + ".log")).open("wb") as log:
                result = subprocess.run([sys.executable, script], cwd=ROOT, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=60)
            okay = result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            okay = False
        print(name + (": passed" if okay else ": failed"))
        passed = passed and okay
    raise SystemExit(0 if passed else 1)
