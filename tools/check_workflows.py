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
        assert document["concurrency"] == {
            "group": "${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}",
            "cancel-in-progress": "${{ github.event_name == 'pull_request' }}"}, "Obsolete PR runs not cancelled safely"
        assert document["on"]["push"]["branches"] == ["main", "release/**"], "Duplicate branch/PR workflows"
        assert set(document["on"]) <= {"push", "pull_request", "workflow_dispatch"}, "Unexpected privileged trigger"
        assert document.get("jobs"), "No workflow jobs"
        for job in document["jobs"].values():
            assert "self-hosted" not in str(job.get("runs-on")), "Privileged runner in public workflow"
            for step in job.get("steps", []):
                if "run" in step:
                    assert isinstance(step["run"], str), "Run must be a scalar string"
                if "uses" in step:
                    assert re.fullmatch(r"actions/[a-z-]+(?:/(?:restore|save))?@[a-f0-9]{40}", step["uses"]), "Unpinned workflow dependency"
            steps = job.get("steps", [])
            for index, step in enumerate(steps):
                if step.get("uses", "").startswith("actions/cache/"):
                    assert step["with"]["path"] == ".local/public-download-cache", "Unsafe online cache path"
                    assert "restore-keys" not in step["with"], "Unbounded cache fallback"
                    assert "hashFiles(" in step["with"]["key"] and "ci/publication-policy.json" in step["with"]["key"], "Cache lock/policy identity absent"
                    if step["uses"].startswith("actions/cache/save@"):
                        assert "success()" in step.get("if", "") and "steps.cache-clear.outcome == 'success'" in step["if"], "Cache save lacks exact-byte clearance"
                        assert index > 0 and steps[index-1].get("id") == "cache-clear" and "cache_downloads.py seal" in steps[index-1].get("run", ""), "Cache clearance must immediately precede upload"
    workflow = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step.get("with", {}).get("ref") == "${{ github.event.pull_request.head.sha || github.sha }}", "Every handoff job must test the same published candidate"
    presets = [row["preset"] for row in workflow["jobs"]["build"]["strategy"]["matrix"]["include"]]
    assert sorted(presets) == ["windows-debug", "windows-release"], "Windows-only build matrix required"
    assert workflow["jobs"]["gate"]["if"] == "always()", "Aggregate gate can be skipped"
    assert set(workflow["jobs"]["gate"]["needs"]) == {"build", "host", "dependencies", "dwg"}, "Profile jobs absent from required gate"
    native=workflow['jobs']['dwg']['steps']
    assert any('build_independent_dwg.py' in step.get('run','') for step in native), 'Independent backend build absent'
    assert any('publication_preflight.py' in step.get('run','') and 'dwg-backend.json' in step['run'] for step in native), 'Native report lacks clearance'
    assert any(step.get('with',{}).get('name')=='foundation-dwg' for step in native), 'Native report absent from handoff'
    assert workflow["jobs"]["host"]["strategy"]["matrix"]["os"] == ["windows-2022"], "Windows-only host matrix required"
    assert "spatial.json" in str(workflow["jobs"]["build"]), "Spatial reports absent"
    assert "jobs.json" in str(workflow["jobs"]["build"]), "WP-06 lifecycle reports absent"
    build_steps = workflow["jobs"]["build"]["steps"]
    assert workflow["jobs"]["build"]["needs"] == "unit", "Unit receipt lacks a current-run owner"
    assert any('--unit-report .local/unit-owner/unit-tests.json' in step.get('run','') and '--jobs 2' in step['run'] for step in build_steps), "Bounded current-run verification absent"
    units = workflow["jobs"]["unit"]["steps"]
    assert any('check_security.py --report .local/unit/unit-tests.json' in step.get('run','') for step in units), "Complete unit owner absent"
    assert any('publication_preflight.py --file .local/unit/unit-tests.json' in step.get('run','') for step in units), "Unit receipt lacks clearance"
    assert any('mcp-requirements.lock' in step.get('run','') for step in build_steps), 'MCP SDK lock absent'
    assert any('publication_preflight.py' in step.get('run','') and 'mcp.json' in step['run'] for step in build_steps), 'MCP report lacks clearance'
    assert any('mcp.json' in step.get('with',{}).get('path','') for step in build_steps if step.get('uses','').startswith('actions/upload-artifact@')), 'MCP report absent'
    assert any('publication_preflight.py' in step.get('run','') and 'radiation.json' in step['run'] for step in build_steps), 'WP-12 report lacks clearance'
    assert any('radiation.json' in step.get('with',{}).get('path','') for step in build_steps if step.get('uses','').startswith('actions/upload-artifact@')), 'WP-12 report absent'

    assert any('publication_preflight.py' in step.get('run','') and 'thermal.json' in step['run'] for step in build_steps), 'WP-11 preparation report lacks clearance'
    assert any('thermal.json' in step.get('with',{}).get('path','') for step in build_steps if step.get('uses','').startswith('actions/upload-artifact@')), 'WP-11 preparation report absent'
    assert any('publication_preflight.py' in step.get('run','') and 'thermal-references.json' in step['run'] for step in build_steps), 'Independent reference report lacks clearance'
    assert any('thermal-references.json' in step.get('with',{}).get('path','') for step in build_steps if step.get('uses','').startswith('actions/upload-artifact@')), 'Independent reference report absent'
    assert any("publication_preflight.py" in step.get("run", "") and "exchange.json" in step["run"] for step in build_steps), "WP-07 report lacks pre-upload clearance"
    assert any("exchange.json" in step.get("with", {}).get("path", "") for step in build_steps if step.get("uses", "").startswith("actions/upload-artifact@")), "WP-07 report absent"
    assert any("publication_preflight.py" in step.get("run", "") and "td.json" in step["run"] for step in build_steps), "WP-08 report lacks pre-upload clearance"
    assert any("td.json" in step.get("with", {}).get("path", "") for step in build_steps if step.get("uses", "").startswith("actions/upload-artifact@")), "WP-08 report absent"
    assert any('publication_preflight.py' in step.get('run','') and 'esatan.json' in step['run'] for step in build_steps), 'WP-09 report lacks pre-upload clearance'
    assert any('esatan.json' in step.get('with',{}).get('path','') for step in build_steps if step.get('uses','').startswith('actions/upload-artifact@')), 'WP-09 report absent'
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
