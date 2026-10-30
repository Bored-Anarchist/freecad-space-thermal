# SPDX-License-Identifier: MIT OR Apache-2.0
"""Candidate-bound foundation coverage and content identity shared by local/CI gates."""
from hashlib import sha256
from pathlib import Path
import subprocess
from .gate import evaluate
from .delivery import FOUNDATION_CASES


def input_hashes(root):
    result = {}
    for name in ("python", "engine", "adapters", "tests", "tools", "ci", "spec/schemas", "spec/contracts"):
        for path in sorted((root/name).rglob("*")):
            if path.is_file() and (path.suffix in {".py", ".cpp", ".cs", ".h", ".hpp", ".patch", ".inc", ".json", ".lock"} or path.name=="CMakeLists.txt"):
                result[path.relative_to(root).as_posix()] = sha256(path.read_bytes()).hexdigest()
    for name in ("CMakeLists.txt", "CMakePresets.json", "pyproject.toml", ".github/workflows/ci.yml"):
        result[name] = sha256((root/name).read_bytes()).hexdigest()
    return result


def assess_reports(debug, release, host, expected_inputs, candidate):
    for report in (debug, release):
        if (report.get("candidate") != candidate or report.get("input_sha256") != expected_inputs
                or report.get("gate", {}).get("status") != "passed"):
            raise ValueError("stale_or_failed_foundation_report")
        expected = sorted(FOUNDATION_CASES-{f"WP055-HOST-{i:03d}" for i in range(1,5)}-{"WP055-HAND-001", "WP055-HAND-002"})
        if evaluate(expected,report.get("cases",[]))["status"] != "passed":
            raise ValueError("incomplete_foundation_coverage")
    host_ids = [f"WP055-HOST-{i:03d}" for i in range(1,5)]
    if (host.get("candidate") != candidate or host.get("status") != "passed"
            or host.get("input_sha256") != expected_inputs
            or evaluate(host_ids,host.get("cases",[]))["status"] != "passed"):
        raise ValueError("stale_or_incomplete_host_report")
    return True
