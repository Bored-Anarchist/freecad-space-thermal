# SPDX-License-Identifier: MIT OR Apache-2.0
"""Emit bounded timings from current-run, passing candidate reports only."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from fcst_tools.ci_performance import compare, change, seconds, workload_hash
from fcst_tools.profiles import assess_dependencies, RESOURCE_STAGES, RESOURCE_PROFILE, valid_resources
from profile_support import revision
from verify import STEPS


def summarize(directory, baseline, candidate):
    if baseline["workload_sha256"] != workload_hash(ROOT):
        raise ValueError("ci_performance_workload_changed")
    for name, contract in baseline.get("acceptance_case_ids", {}).items():
        policy = json.loads((ROOT / name).read_bytes())
        if not set(contract["cases"]) <= set(policy[contract["field"]]):
            raise ValueError("ci_performance_acceptance_coverage_lost")
    expected = json.loads((ROOT / "ci/coverage.json").read_bytes())["unit_cases"] + STEPS
    reports = list(directory.rglob("verification.json"))
    if len(reports) != 2:
        raise ValueError("ci_performance_configuration_count")
    presets = {}
    for path in reports:
        report = json.loads(path.read_bytes())
        if report.get("execution", {}).get("resource_profile") != RESOURCE_PROFILE:
            raise ValueError("ci_performance_resource_profile")
        if report["preset"] in presets:
            raise ValueError("ci_performance_duplicate_configuration")
        presets[report["preset"]] = compare(report, baseline, candidate, expected, STEPS)
    if set(presets) != set(baseline["presets"]):
        raise ValueError("ci_performance_configuration_coverage")
    packages = {}
    sources = json.loads((ROOT / "ci/probe-sources.json").read_bytes())["sources"]
    for path in directory.rglob("dependency-builds-*.json"):
        report = json.loads(path.read_bytes())
        if report.get("candidate") != candidate or len(report["candidates"]) != 1:
            raise ValueError("ci_performance_package_candidate")
        record = report["candidates"][0]; name = record["id"]
        if (name not in baseline["packages"] or name in packages
                or record["source_sha256"] != baseline["packages"][name]["source_sha256"]
                or not assess_dependencies(report, sources, "Windows", name)):
            raise ValueError("ci_performance_package_coverage")
        if (record.get("generator") != "visual-studio-2022"
                or record.get("resource_profile") != RESOURCE_PROFILE
                or type(record.get("build_jobs")) is not int or not 1 <= record["build_jobs"] <= 16
                or type(record.get("compiler_jobs")) is not int or not 1 <= record["compiler_jobs"] <= 4
                or not valid_resources(record.get("stage_resources"))
                or not isinstance(record.get("stage_seconds"), dict) or set(record["stage_seconds"]) != RESOURCE_STAGES):
            raise ValueError("ci_performance_package_execution")
        logical_cpus = record.get("toolchain", {}).get("logical_cpus")
        if logical_cpus is not None and (type(logical_cpus) is not int or not 1 <= logical_cpus <= 1024):
            raise ValueError("ci_performance_package_cpus")
        packages[name] = dict(change(baseline["packages"][name]["seconds"], record["seconds"]),
                              logical_cpus=logical_cpus,
                              generator=record["generator"], build_jobs=record["build_jobs"], compiler_jobs=record["compiler_jobs"],
                              stage_seconds={stage: seconds(record["stage_seconds"][stage]) for stage in sorted(RESOURCE_STAGES)},
                              stage_resources=record["stage_resources"])
    if set(packages) != set(baseline["packages"]):
        raise ValueError("ci_performance_missing_package")
    return dict(schema_version=1, candidate=candidate, resource_profile=RESOURCE_PROFILE, baseline_candidate=baseline["candidate"],
                baseline_run_id=baseline["run_id"], workload_sha256=baseline["workload_sha256"],
                presets=presets, packages=packages,
                timing_policy="Investigate increases over 20 percent and at least 60 seconds; timing alone is not a correctness failure")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.report.unlink(missing_ok=True)
    try:
        baseline = json.loads((ROOT / "ci/ci-performance-baseline.json").read_bytes())
        report = summarize(args.reports, baseline, revision())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        for preset, result in report["presets"].items():
            driver = result["driver"]
            print(f"CI timing {preset}: {driver['before_seconds']:.1f} -> {driver['after_seconds']:.1f} seconds; investigate={driver['investigate']}")
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print("CI timing summary: failed; incomplete or incompatible evidence")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
