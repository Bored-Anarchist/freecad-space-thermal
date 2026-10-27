# SPDX-License-Identifier: MIT OR Apache-2.0
"""Read-only GitHub repository settings checker; unavailable evidence fails closed."""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def request(endpoint):
    result = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True, timeout=60)
    if result.returncode:
        return None
    return json.loads(result.stdout)


def assess(config, repo, protection, actions, workflows, rules, issues, project):
    findings = []
    def need(condition, code):
        if not condition:
            findings.append(code)
    need(repo is not None, "repository_unavailable")
    if repo:
        need(repo.get("full_name") == config["repository"], "wrong_repository")
        need(repo.get("visibility") == config["visibility"], "wrong_visibility")
        need(repo.get("has_issues"), "issues_disabled")
        need(repo.get("default_branch") == config["default_branch"], "wrong_default_branch")
    need(protection is not None, "default_protection_unavailable")
    if protection:
        checks = protection.get("required_status_checks") or {}
        need(set(config["required_checks"]) <= set(checks.get("contexts", [])), "missing_required_checks")
        need(checks.get("strict"), "branch_must_be_current")
        need((protection.get("enforce_admins") or {}).get("enabled"), "admin_bypass_enabled")
        need(not (protection.get("allow_force_pushes") or {}).get("enabled"), "force_pushes_allowed")
        need(not (protection.get("allow_deletions") or {}).get("enabled"), "branch_deletions_allowed")
        need(protection.get("required_pull_request_reviews") is not None, "review_policy_missing")
    need(actions is not None and actions.get("default_workflow_permissions") == "read"
         and actions.get("can_approve_pull_request_reviews") is False, "excessive_workflow_permissions")
    need(workflows is not None and workflows.get("enabled") is True
         and workflows.get("allowed_actions") == "selected", "action_allowlist_missing")
    need(rules is not None and any(row.get("name") == "Protect release branches" and row.get("enforcement") == "active"
                                  for row in rules), "release_protection_missing")
    need(issues is not None and len(issues) >= 21, "work_package_backlog_incomplete")
    need(project is not None and bool(project.get("url")), "project_link_missing")
    return {"status": "blocked" if findings else "passed", "findings": findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/github-settings.json")
    args = parser.parse_args()
    config = json.loads((ROOT / "ci/github.json").read_text())
    prefix = "repos/" + config["repository"]
    repo = request(prefix)
    protection = request(prefix + "/branches/main/protection")
    actions = request(prefix + "/actions/permissions/workflow")
    workflows = request(prefix + "/actions/permissions")
    rules = request(prefix + "/rulesets")
    issues = request(prefix + "/issues?state=all&per_page=100")
    project_path = ROOT / "plans/github-project.json"
    project = json.loads(project_path.read_text()) if project_path.exists() else None
    report = {"repository": config["repository"], **assess(config, repo, protection, actions, workflows, rules, issues, project)}
    validation_prefix = "repos/" + config["validation_repository"]
    validation = request(validation_prefix)
    runners = request(validation_prefix + "/actions/runners")
    if not validation or validation.get("private") is not True or runners is None or runners.get("total_count") != 0:
        report["findings"].append("unqualified_validation_boundary")
        report["status"] = "blocked"
    else:
        report["validation_boundary"] = "private_no_privileged_runners_registered"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
