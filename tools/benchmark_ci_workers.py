# SPDX-License-Identifier: MIT OR Apache-2.0
"""Unattended, paired worker comparison on one calibrated Windows runner."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from fcst_tools.ci_performance import compare, seconds, workload_hash
from fcst_tools.profiles import RESOURCE_PROFILE
from fcst_tools.verification import unit_inputs
from profile_support import revision
from verify import STEPS


def analyze(reports, jobs, baseline, candidate, expected):
    if type(jobs) is not int or jobs not in (3, 4) or len(reports) != 5:
        raise ValueError("worker_benchmark_plan")
    other = 7-jobs
    plan = [jobs, jobs, other, other, jobs]  # Calibration, then ABBA.
    acceptance = STEPS[STEPS.index("contract-conformance"):]
    samples = []
    cpus = None
    for report, workers in zip(reports, plan):
        if (not isinstance(report, dict) or not isinstance(report.get("execution"), dict)
                or report.get("preset") != "windows-debug" or report["execution"].get("jobs") != workers
                or report["execution"].get("run_mode") != "worker-benchmark"
                or report["execution"].get("resource_profile") != RESOURCE_PROFILE):
            raise ValueError("worker_benchmark_execution")
        compare(report, baseline, candidate, expected, STEPS)
        actual_cpus = report["execution"].get("logical_cpus")
        if type(actual_cpus) is not int or actual_cpus < 1 or (cpus is not None and actual_cpus != cpus):
            raise ValueError("worker_benchmark_runner_changed")
        cpus = actual_cpus
        cases = {c["id"]: c for c in report["cases"] if c["id"] in acceptance}
        begin = min(seconds(c["started_seconds"]) for c in cases.values())
        end = max(seconds(c["started_seconds"])+seconds(c["seconds"]) for c in cases.values())
        if end <= begin or end > report["execution"]["seconds"] + .01:
            raise ValueError("worker_benchmark_interval")
        samples.append(dict(jobs=workers, driver_seconds=report["execution"]["seconds"],
                            acceptance_seconds=round(end-begin, 3),
                            cpu_seconds=round(sum(c["resources"]["cpu_seconds"] for c in cases.values()), 6),
                            stage_seconds={name: cases[name]["seconds"] for name in acceptance},
                            stage_peak_commit_bytes={name: cases[name]["resources"]["peak_job_commit_bytes"] for name in acceptance}))
    values = {workers: [s["acceptance_seconds"] for s in samples[1:] if s["jobs"] == workers] for workers in (3, 4)}
    medians = {str(workers): median(values[workers]) for workers in (3, 4)}
    return dict(schema_version=1, candidate=candidate, resource_profile=RESOURCE_PROFILE,
                preset="windows-debug", logical_cpus=cpus, required_cases=len(expected),
                calibration=samples[0], sampling_plan=plan[1:], samples=samples[1:],
                median_acceptance_seconds=medians, four_vs_three_ratio=round(medians["4"]/medians["3"], 4),
                scope="One full calibration, then paired complete acceptance; preparation repeats but is excluded from acceptance comparison")


def run(jobs, unit_report):
    try:
        candidate = revision()
        frozen = unit_inputs(ROOT)
        run_id = os.environ.get("GITHUB_RUN_ID", str(time.time_ns()))
        attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "0")
        if any(not re.fullmatch(r"[0-9]{1,40}", value) for value in (run_id, attempt)):
            raise ValueError("worker_benchmark_run_identity")
        work = ROOT / ".local/worker-benchmark" / (run_id+"-"+attempt)
        work.mkdir(parents=True, exist_ok=False)
        baseline = json.loads((ROOT / "ci/ci-performance-baseline.json").read_bytes())
        if baseline["workload_sha256"] != workload_hash(ROOT):
            raise ValueError("worker_benchmark_workload")
        expected = json.loads((ROOT / "ci/coverage.json").read_bytes())["unit_cases"] + STEPS
        reports = []
        for index, workers in enumerate([jobs, jobs, 7-jobs, 7-jobs, jobs]):
            with (work / f"attempt-{index}.log").open("wb") as log:
                result = subprocess.run([sys.executable, str(ROOT / "tools/verify.py"), "--preset", "windows-debug",
                    "--jobs", str(workers), "--unit-report", str(unit_report)], cwd=ROOT,
                    stdout=log, stderr=subprocess.STDOUT, timeout=1200,
                    env=dict(os.environ, FCST_VERIFICATION_MODE="worker-benchmark"))
            if result.returncode or revision() != candidate or unit_inputs(ROOT) != frozen:
                raise ValueError("worker_benchmark_attempt")
            destination = work / f"attempt-{index}.json"
            shutil.copyfile(ROOT / ".local/windows-debug/verification.json", destination)
            reports.append(json.loads(destination.read_bytes()))
            print(f"Worker benchmark attempt {index}: passed with {workers} workers", flush=True)
        summary = analyze(reports, jobs, baseline, candidate, expected)
        summary["workload_sha256"] = workload_hash(ROOT)
        (work / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        print("Worker benchmark: passed; all attempts retained", flush=True)
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print("Worker benchmark: failed; raw diagnostics remain local", flush=True)
        return 1
