# SPDX-License-Identifier: MIT OR Apache-2.0
"""Read-only GitHub repository settings checker; unavailable evidence fails closed."""
import argparse
import base64
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def assess_validation(repository, runners, policy, workflow, permissions):
    if not repository or repository.get("private") is not True or not runners or runners.get("total_count") != 0:
        return ["unqualified_validation_boundary"]
    findings = []
    if (not policy or policy.get("enabled") is not False or policy.get("public_pr_execution") is not False
            or policy.get("reviewed_candidate_required") is not True or policy.get("fixture_storage") != "runner_local_only"):
        findings.append("validation_policy_not_fail_closed")
    if (not permissions or permissions.get("default_workflow_permissions") != "read"
            or permissions.get("can_approve_pull_request_reviews") is not False):
        findings.append("validation_excessive_permissions")
    jobs = (workflow or {}).get("jobs", {})
    if (not workflow or workflow.get("on") != ["workflow_dispatch"]
            or workflow.get("permissions") != {"contents": "read"} or set(jobs) != {"prerequisites"}):
        findings.append("validation_untrusted_trigger_or_jobs")
    else:
        job = jobs["prerequisites"]
        steps = job.get("steps", [])
        deny = "echo 'blocked: exact licensed profiles and reviewed candidate promotion not configured'\nexit 1"
        if (job.get("runs-on") != "ubuntu-24.04" or len(steps) != 2
                or steps[0].get("uses") != "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
                or steps[0].get("with", {}).get("persist-credentials") != "false"
                or steps[1].get("run", "").strip() != deny or "if" in steps[1]):
            findings.append("validation_deny_guard_changed")
    return findings


def content(endpoint, yaml_document=False):
    response = request(endpoint)
    if not response or response.get("encoding") != "base64":
        return None
    try:
        text = base64.b64decode(response["content"]).decode("utf-8")
        if yaml_document:
            import yaml
            try:
                return yaml.load(text, Loader=yaml.BaseLoader)
            except yaml.YAMLError:
                return None
        return json.loads(text)
    except (KeyError, ValueError, UnicodeError, ImportError):
        return None


def request(endpoint):
    result = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True, timeout=60)
    if result.returncode:
        return None
    return json.loads(result.stdout)


def project_snapshot(project_id):
    query = """query($id:ID!){node(id:$id){... on ProjectV2{
      id title url closed public
      repositories(first:100){nodes{nameWithOwner}}
      fields(first:100){nodes{... on ProjectV2SingleSelectField{name options{name}}}}
      items(first:100){nodes{
        content{... on Issue{url}}
        fieldValues(first:100){nodes{... on ProjectV2ItemFieldSingleSelectValue{
          name field{... on ProjectV2SingleSelectField{name}}
        }}}
      }}
    }}}"""
    result = subprocess.run(["gh", "api", "graphql", "--input", "-"],
                            input=json.dumps({"query": query, "variables": {"id": project_id}}),
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        return None
    data = json.loads(result.stdout)
    return None if data.get("errors") else data.get("data", {}).get("node")


def assess_project(config, project, snapshot):
    if not project or not snapshot:
        return ["project_evidence_unavailable"]
    findings = []
    if (snapshot.get("id") != project.get("project_id") or snapshot.get("url") != project.get("url")
            or snapshot.get("title") != config["projects_title"] or snapshot.get("closed")
            or snapshot.get("public") is not True):
        findings.append("project_identity_or_visibility_mismatch")
    repositories = {row["nameWithOwner"] for row in snapshot.get("repositories", {}).get("nodes", [])}
    if config["repository"] not in repositories:
        findings.append("project_not_linked_to_repository")
    fields = {row.get("name"): row for row in snapshot.get("fields", {}).get("nodes", [])}
    options = {row["name"] for row in fields.get("Status", {}).get("options", [])}
    if options != {"Planned", "Ready", "In progress", "Blocked", "Complete"}:
        findings.append("project_delivery_states_incomplete")
    expected = {row["issue"]: row["state"] for row in project.get("items", [])}
    actual = {}
    for row in snapshot.get("items", {}).get("nodes", []):
        url = (row.get("content") or {}).get("url")
        values = row.get("fieldValues", {}).get("nodes", [])
        actual[url] = next((value.get("name") for value in values
                            if (value.get("field") or {}).get("name") == "Status"), None)
    if len(expected) != 21 or actual != expected:
        findings.append("project_backlog_or_states_mismatch")
    return findings


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
    project_findings = assess_project(config, project, project_snapshot(project["project_id"]) if project else None)
    if project_findings:
        report["findings"].extend(project_findings)
        report["status"] = "blocked"
    elif project:
        report["project"] = {"url": project["url"], "items": len(project["items"]), "status": "passed"}
    validation_prefix = "repos/" + config["validation_repository"]
    validation = request(validation_prefix)
    runners = request(validation_prefix + "/actions/runners")
    boundary_findings = assess_validation(validation, runners,
        content(validation_prefix + "/contents/policy.json"),
        content(validation_prefix + "/contents/.github/workflows/validation.yml", yaml_document=True),
        request(validation_prefix + "/actions/permissions/workflow"))
    if boundary_findings:
        report["findings"].extend(boundary_findings)
        report["status"] = "blocked"
    else:
        report["validation_boundary"] = "private_no_privileged_runners_registered"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
