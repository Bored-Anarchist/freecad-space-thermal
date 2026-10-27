# SPDX-License-Identifier: MIT OR Apache-2.0
"""One local/CI driver. Raw output stays local; public reports contain bounded IDs."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from fcst_tools.gate import evaluate

STEPS = ["planning", "specification", "inventory", "workflow-lint", "python-package", "python-imports", "configure", "build", "ctest", "install", "engine-only"]


def command(args, log, env=None):
    with log.open("wb") as output:
        result = subprocess.run(args, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                env=env, timeout=600)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=["fast", "full"], default="fast")
    parser.add_argument("--preset", choices=["windows-debug", "windows-release"], default="windows-debug")
    args = parser.parse_args()
    if platform.system() != "Windows":
        parser.error("macOS and Linux verification is deferred to WP-22 after Windows Q2")
    manifest = json.loads((ROOT / "ci/coverage.json").read_text())
    output = ROOT / ".local" / args.preset
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / "tmp"
    temporary.mkdir(exist_ok=True)
    os.environ.update(TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary))
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    os.environ.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    records = []
    def record(case_id, status, **extra):
        records.append({"id": case_id, "status": status, **extra})
        print(case_id + ": " + status, flush=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    def flatten(tests):
        for test in tests:
            if isinstance(test, unittest.TestSuite):
                yield from flatten(test)
            else:
                yield test
    tests = list(flatten(suite))
    for test in tests:
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream).run(unittest.TestSuite([test]))
        (output / (test.id() + ".log")).write_text(stream.getvalue(), encoding="utf-8")
        record(test.id(), "passed" if result.wasSuccessful() and not result.skipped else "failed")
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        revision = ""
    if not revision or any(char not in "0123456789abcdef" for char in revision):
        revision = "uncommitted"
    try:
        import cmake as cmake_package
        cmake_bin = Path(cmake_package.CMAKE_BIN_DIR)
        suffix = ".exe" if os.name == "nt" else ""
        cmake = str(cmake_bin / ("cmake" + suffix))
        ctest = str(cmake_bin / ("ctest" + suffix))
    except ImportError:
        cmake = shutil.which("cmake") or "cmake"
        ctest = shutil.which("ctest") or "ctest"
    config = "Release" if args.preset.endswith("release") else "Debug"
    install = output / "install"
    actions = {
        "planning": [sys.executable, "plans/tools/validate_plan.py"],
        "specification": [sys.executable, "spec/tools/validate_spec.py"],
        "inventory": [sys.executable, "tools/check_inventory.py"],
        "workflow-lint": [sys.executable, "tools/check_workflows.py"],
        "python-package": [sys.executable, "-m", "pip", "install", "--no-deps", "--no-build-isolation", "--no-index", "-e", "."],
        "python-imports": [sys.executable, "-I", "-c", "import fcst_app,fcst_cli,fcst_mcp; assert not fcst_app.capabilities()['solver_available']"],
        "configure": [cmake, "--preset", args.preset, "-DFCST_SOURCE_REVISION=" + revision],
        "build": [cmake, "--build", "--preset", args.preset, "--parallel", "2"],
        "ctest": [ctest, "--preset", args.preset],
        "install": [cmake, "--install", str(ROOT / "out" / args.preset), "--config", config, "--prefix", str(install)],
    }
    for case_id in STEPS:
        start = time.monotonic()
        try:
            if case_id == "engine-only":
                worker = install / "bin" / ("fcst-worker.exe" if os.name == "nt" else "fcst-worker")
                env = dict(os.environ, PATH=str(worker.parent))
                env.pop("PYTHONPATH", None)
                env.pop("PYTHONHOME", None)
                info = subprocess.run([str(worker), "--build-info"], capture_output=True, text=True, env=env, timeout=30)
                data = json.loads(info.stdout)
                rejected = subprocess.run([str(worker), "--solve"], capture_output=True, text=True, env=env, timeout=30)
                okay = (info.returncode == 0 and data["engine"] == "fcst_native"
                        and data["solver_available"] is False and data["source_revision"] == revision
                        and rejected.returncode == 2 and json.loads(rejected.stderr)["code"] == "not_implemented")
                (output / "build-info.json").write_text(json.dumps(data, indent=2) + "\n")
            else:
                okay = command(actions[case_id], output / (case_id + ".log"))
            record(case_id, "passed" if okay else "failed", seconds=round(time.monotonic() - start, 3))
        except (OSError, ValueError, subprocess.SubprocessError, KeyError):
            record(case_id, "failed", reason="execution_unavailable")
    expected = manifest["unit_cases"] + STEPS
    if args.tier == "full":
        for case_id in manifest["full_prerequisites"]:
            if case_id == "freecad-exact-build-smoke":
                try:
                    okay = command([sys.executable, "tools/host_smoke.py"], output / "host-smoke.log")
                    record(case_id, "passed" if okay else "failed")
                except (OSError, ValueError, subprocess.SubprocessError):
                    record(case_id, "failed", reason="host_execution_unavailable")
            else:
                # Product/vendor/numerical qualification is a separate Q0 gate.
                record(case_id, "blocked", reason="required_configuration_or_implementation_unavailable")
        expected += manifest["full_prerequisites"]
    verdict = evaluate(expected, records)
    report = {"schema_version": 1, "scope": "WP-02 foundation; no thermal or compatibility qualification",
              "candidate": revision, "preset": args.preset, "tier": args.tier,
              "python": platform.python_version(), "os": platform.system(), "machine_arch": platform.machine(),
              "coverage_manifest_sha256": hashlib.sha256((ROOT / "ci/coverage.json").read_bytes()).hexdigest(),
              "gate": verdict, "cases": records}
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verdict))
    return 0 if verdict["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
