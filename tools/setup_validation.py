# SPDX-License-Identifier: MIT OR Apache-2.0
"""Create a private, disabled-by-default validation boundary without licensed data."""
import base64
import json
from pathlib import Path
from setup_github import api, cleared

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    config = json.loads((ROOT / "ci/github.json").read_text())
    policy = json.loads((ROOT / "ci/publication-policy.json").read_text())
    identity = policy["approved_identities"][0]
    repository = config["validation_repository"]
    prefix = "repos/" + repository
    if api(prefix, optional=True) is None:
        api("user/repos", {"name": repository.split("/")[1], "private": True,
                           "description": "Controlled FCST validation boundary; no restricted models or licensed runtimes uploaded",
                           "has_issues": False, "has_projects": False, "has_wiki": False})
    files = {
        "README.md": "# FCST private validation boundary\n\nNo licensed data, secrets or privileged runners are provisioned. Public pull requests cannot trigger workflows here. Validation remains blocked until exact licensed profiles, reviewed immutable candidates, disposable workspaces, sanitized outputs and runner-local fixture stores are configured and tested. Never upload restricted originals or raw evidence without destination-specific permission.\n",
        "policy.json": json.dumps({"enabled": False, "reviewed_candidate_required": True,
                                    "public_pr_execution": False, "fixture_storage": "runner_local_only",
                                    "reason": "Exact runtime and reviewed artifact promotion profiles not configured"}, indent=2) + "\n",
        ".github/workflows/validation.yml": """name: Controlled validation boundary
on: [workflow_dispatch]
permissions:
  contents: read
jobs:
  prerequisites:
    name: Validation prerequisites
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262
        with:
          persist-credentials: false
      - name: Deny unconfigured privileged execution
        run: |
          echo 'blocked: exact licensed profiles and reviewed candidate promotion not configured'
          exit 1
"""
    }
    for path, text in files.items():
        cleared({"path": path, "text": text, "author": identity})
        if api(prefix + "/contents/" + path, optional=True) is None:
            api(prefix + "/contents/" + path, {"message": "Establish disabled validation boundary",
                "content": base64.b64encode(text.encode()).decode(), "author": identity, "committer": identity}, method="PUT")
    api(prefix + "/actions/permissions/workflow", {"default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": False}, method="PUT")
    api(prefix + "/actions/permissions", {"enabled": True, "allowed_actions": "selected"}, method="PUT")
    api(prefix + "/actions/permissions/selected-actions", {"github_owned_allowed": True,
        "verified_allowed": False, "patterns_allowed": []}, method="PUT")
    print("Private validation boundary ready; privileged execution remains blocked")
