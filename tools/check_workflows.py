# SPDX-License-Identifier: MIT OR Apache-2.0
"""Parse workflow YAML and verify foundation security/coverage invariants."""
import re
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def validate():
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        document = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        assert document.get("permissions") == {"contents": "read"}, "Non-minimal default permissions"
        assert set(document["on"]) <= {"push", "pull_request", "workflow_dispatch"}, "Unexpected privileged trigger"
        assert document.get("jobs"), "No workflow jobs"
        for job in document["jobs"].values():
            assert "self-hosted" not in str(job.get("runs-on")), "Privileged runner in public workflow"
            for step in job.get("steps", []):
                if "run" in step:
                    assert isinstance(step["run"], str), "Run must be a scalar string"
                if "uses" in step:
                    assert re.fullmatch(r"actions/[a-z-]+@[a-f0-9]{40}", step["uses"]), "Unpinned workflow dependency"
    workflow = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step.get("with", {}).get("ref") == "${{ github.event.pull_request.head.sha || github.sha }}", "Every handoff job must test the same published candidate"
    presets = [row["preset"] for row in workflow["jobs"]["build"]["strategy"]["matrix"]["include"]]
    assert sorted(presets) == ["windows-debug", "windows-release"], "Windows-only build matrix required"
    assert workflow["jobs"]["gate"]["if"] == "always()", "Aggregate gate can be skipped"
    assert set(workflow["jobs"]["gate"]["needs"]) == {"build", "host", "dependencies"}, "Profile jobs absent from required gate"
    assert workflow["jobs"]["host"]["strategy"]["matrix"]["os"] == ["windows-2022"], "Windows-only host matrix required"
    assert "spatial.json" in str(workflow["jobs"]["build"]), "Spatial reports absent"
    assert "jobs.json" in str(workflow["jobs"]["build"]), "WP-06 lifecycle reports absent"
    build_steps = workflow["jobs"]["build"]["steps"]
    assert any("publication_preflight.py" in step.get("run", "") and "exchange.json" in step["run"] for step in build_steps), "WP-07 report lacks pre-upload clearance"
    assert any("exchange.json" in step.get("with", {}).get("path", "") for step in build_steps if step.get("uses", "").startswith("actions/upload-artifact@")), "WP-07 report absent"
    assert "fem_probe.py" in str(workflow["jobs"]["host"]), "FEM probes absent"
    assert "check_foundation_handoff.py" in str(workflow["jobs"]["gate"]), "TST-022 aggregate absent"
    packages = workflow["jobs"]["dependencies"]["strategy"]["matrix"]
    assert packages["os"] == ["windows-2022"], "Windows-only package matrix required"
    assert set(packages["candidate"]) == {"sundials", "hdf5", "embree", "occt"}, "Incorrect active Windows package candidates"
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        document = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        for job in document["jobs"].values():
            runner = job["runs-on"]
            if "matrix.os" in runner:
                matrix = job["strategy"]["matrix"]
                runners = matrix.get("os") or [r["os"] for r in matrix.get("include", [])]
                assert runners and set(runners) == {"windows-2022"}, "Deferred platform scheduled"
            else:
                assert runner == "windows-2022", "Deferred platform scheduled"


if __name__ == "__main__":
    try:
        validate()
        print("Workflow structure: passed")
    except (AssertionError, KeyError, TypeError, OSError, yaml.YAMLError):
        print("Workflow structure: failed")
        raise SystemExit(1)
