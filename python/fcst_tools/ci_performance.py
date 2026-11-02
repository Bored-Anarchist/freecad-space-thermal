# SPDX-License-Identifier: MIT OR Apache-2.0
"""Compare verified CI timings without publishing raw logs or weakening coverage."""
import hashlib
import json
import math
from .gate import evaluate
from .profiles import valid_resource_usage, RESOURCE_PROFILE


def workload_hash(root):
    policy = json.loads((root / "ci/radiation-acceptance-v1.json").read_bytes())
    policy.pop("native_cases")  # Adding correctness regressions is allowed.
    value = dict(radiation=policy,
        statistics=json.loads((root / "ci/numerical-criteria-v1.json").read_bytes())["statistical_policy"],
        fixtures={name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in (
            "engine/tests/radiation_fixtures.hpp", "tests/fixtures/radiation/plates.json", "tests/fixtures/radiation/steady.json")})
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def seconds(value):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not 0 <= value <= 2**63-1 or not math.isfinite(value)):
        raise ValueError("invalid_ci_timing")
    return value


def change(before, after):
    before, after = seconds(before), seconds(after)
    return dict(before_seconds=before, after_seconds=after, delta_seconds=round(after-before, 3),
                ratio=round(after/before, 4) if before else None,
                investigate=after-before >= 60 and after > before*1.2)


def compare(report, baseline, candidate, expected, stages):
    preset = report["preset"]
    if (preset not in baseline["presets"] or report.get("candidate") != candidate
            or report.get("gate") != evaluate(expected, report.get("cases", []))
            or report["gate"]["status"] != "passed"
            or not set(baseline["required_case_ids"]) <= {c["id"] for c in report["cases"]}):
        raise ValueError("ci_performance_coverage_or_candidate")
    timing = {c["id"]: seconds(c["seconds"]) for c in report["cases"] if c["id"] in stages}
    if set(timing) != set(stages):
        raise ValueError("ci_performance_missing_stage")
    old = baseline["presets"][preset]
    elapsed = seconds(report["execution"]["seconds"])
    if not elapsed or type(report["execution"]["jobs"]) is not int or report["execution"]["jobs"] not in (1, 2, 3, 4):
        raise ValueError("ci_performance_execution")
    cache_state = report["execution"].get("cache_state", "unknown")
    if cache_state not in ("cold", "warm", "unknown"):
        raise ValueError("ci_performance_cache_state")
    resources = {c["id"]: c["resources"] for c in report["cases"] if c["id"] in stages and "resources" in c}
    if any(not valid_resource_usage(usage) for usage in resources.values()):
        raise ValueError("ci_performance_stage_resources")
    resource_profile = report["execution"].get("resource_profile")
    if resource_profile is not None and (resource_profile != RESOURCE_PROFILE or set(resources) != set(stages) - {"engine-only"}):
        raise ValueError("ci_performance_resource_coverage")
    logical_cpus = report["execution"].get("logical_cpus")
    if logical_cpus is not None and (type(logical_cpus) is not int or not 1 <= logical_cpus <= 1024):
        raise ValueError("ci_performance_logical_cpus")
    run_mode = report["execution"].get("run_mode", "standard")
    if run_mode not in ("standard", "worker-benchmark"):
        raise ValueError("ci_performance_run_mode")
    return dict(driver=change(old["driver_seconds"], elapsed),
                stages={name: change(old["stage_seconds"].get(name, 0), timing[name]) for name in stages},
                required_cases=len(expected), jobs=report["execution"]["jobs"],
                logical_cpus=logical_cpus, stage_resources=resources, run_mode=run_mode,
                cache_state=cache_state, baseline_cache_state=baseline.get("cache_state", "unknown"),
                longest_stage=max(stages, key=timing.get))
