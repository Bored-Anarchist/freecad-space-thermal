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
    presets = [row["preset"] for row in workflow["jobs"]["build"]["strategy"]["matrix"]["include"]]
    assert sorted(presets) == ["linux-debug", "linux-release", "windows-debug", "windows-release"], "Incomplete build matrix"
    assert workflow["jobs"]["gate"]["if"] == "always()", "Aggregate gate can be skipped"


if __name__ == "__main__":
    try:
        validate()
        print("Workflow structure: passed")
    except (AssertionError, KeyError, TypeError, OSError, yaml.YAMLError):
        print("Workflow structure: failed")
        raise SystemExit(1)
