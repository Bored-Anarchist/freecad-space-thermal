# SPDX-License-Identifier: MIT OR Apache-2.0
"""Reject missing, substituted or stale foundation profile evidence."""
import hashlib
import json
import math
import re

HOST_CASES = {"create_geometry", "save_reopen", "edit_undo", "application_imports"}
BUILD_STAGES = {"source_hash", "license_hash", "configure", "build", "install", "installed_consumer"}
RESOURCE_STAGES = {"configure", "build", "install", "consumer-configure", "consumer-build", "consumer-run"}


def valid_resource_usage(usage):
    fields = {"cpu_seconds", "peak_process_commit_bytes", "peak_job_commit_bytes", "total_processes"}
    return not (not isinstance(usage, dict) or set(usage) != fields
                or type(usage["cpu_seconds"]) not in (int, float)
                or not math.isfinite(usage["cpu_seconds"]) or usage["cpu_seconds"] < 0
                or any(type(usage[key]) is not int or usage[key] <= 0 for key in fields - {"cpu_seconds"})
                or usage["peak_job_commit_bytes"] < usage["peak_process_commit_bytes"])


def valid_resources(stages):
    return isinstance(stages, dict) and set(stages) == RESOURCE_STAGES and all(valid_resource_usage(usage) for usage in stages.values())


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assess_host(report, profile, system):
    asset = profile["platforms"][system]
    cases = report.get("cases", [])
    return (report.get("status") == "passed" and report.get("scope") == "foundation_host_smoke"
            and report.get("freecad_version") == profile["version"].split(".")
            and report.get("python_abi") == profile["python_abi"]
            and report.get("asset_sha256") == asset["sha256"]
            and len(cases) == len(HOST_CASES) and set(cases) == HOST_CASES
            and report.get("solver_available") is False and report.get("gui_qualified") is False)


def assess_dependencies(report, sources, system, selected=None):
    expected = {row["id"]: row for row in sources if selected is None or row["id"] == selected}
    records = report.get("candidates", [])
    if not expected or len(records) != len(expected) or report.get("platform") != system:
        return False
    actual = {row.get("id"): row for row in records}
    if set(actual) != set(expected):
        return False
    for name, source in expected.items():
        row = actual[name]
        if (row.get("source_sha256") != source["sha256"] or row.get("version") != source["version"]
                or row.get("license_sha256") != source["license_sha256"] or row.get("adopted") is not False):
            return False
        if name == "petsc" and system == "Windows":
            if row.get("status") != "unsupported" or row.get("reason_code") != "petsc_native_msvc_unsupported":
                return False
        elif (row.get("status") != "passed" or set(row.get("stages", [])) != BUILD_STAGES
              or len(row.get("stages", [])) != len(BUILD_STAGES) or row.get("installed_bytes", 0) <= 0):
            return False
        elif "stage_resources" in row and not valid_resources(row["stage_resources"]):
            return False
    return True


def validate_locks(host, sources):
    errors = []
    if host.get("version") != "1.1.4" or host.get("python_abi") != "cp311" or set(host.get("platforms", {})) != {"Windows"}:
        errors.append("invalid_host_profile")
    if {row["id"] for row in sources} != {"sundials", "hdf5", "embree", "occt", "petsc"} or len(sources) != 5:
        errors.append("missing_candidate_profile")
    for row in sources:
        if (not re.fullmatch(r"[a-f0-9]{40}", row.get("revision", ""))
                or row.get("url") != "https://codeload.github.com/" + row["repository"] + "/tar.gz/" + row["revision"]):
            errors.append("unfrozen_source")
    for row in list(sources) + list(host.get("platforms", {}).values()):
        if not re.fullmatch(r"[a-f0-9]{64}", row.get("sha256", "")) or not 0 < row.get("bytes", 0) < 1024 ** 3:
            errors.append("invalid_artifact_lock")
    for row in sources:
        if not re.fullmatch(r"[a-f0-9]{64}", row.get("license_sha256", "")):
            errors.append("unfrozen_license")
    return sorted(set(errors))
