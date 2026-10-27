# SPDX-License-Identifier: MIT OR Apache-2.0
"""Provision the approved GitHub destination and sanitized work-package backlog.

All mutations scan their exact JSON payload first. Idempotent for repository,
milestones, issues and project discovery; protection setup follows initial CI.
"""
import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from fcst_tools.privacy import POLICY_PATH, Scanner


def cleared(payload):
    data = json.dumps(payload, sort_keys=True).encode()
    scanner = Scanner(json.loads(POLICY_PATH.read_text()))
    scanner.scan("github-payload.json", data)
    if scanner.findings:
        raise RuntimeError("Publication payload did not clear privacy policy")
    return data


def api(endpoint, payload=None, method=None, optional=False):
    args = ["gh", "api", endpoint]
    if method:
        args += ["--method", method]
    data = None
    if payload is not None:
        data = cleared(payload)
        args += ["--input", "-"]
    result = subprocess.run(args, input=data, capture_output=True, timeout=90)
    if result.returncode:
        if optional:
            return None
        raise RuntimeError("GitHub operation unavailable: " + endpoint.split("?")[0])
    return json.loads(result.stdout) if result.stdout.strip() else {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["backlog", "protect"], required=True)
    args = parser.parse_args()
    config = json.loads((ROOT / "ci/github.json").read_text())
    repository = config["repository"]
    prefix = "repos/" + repository
    if args.phase == "backlog":
        if api(prefix, optional=True) is None:
            api("user/repos", {"name": repository.split("/")[1], "private": False, "has_issues": True,
                               "has_projects": True, "has_wiki": False,
                               "description": "Independent spacecraft thermal modeling and owned C++ engine with Thermal Desktop and ESATAN interoperability"})
        milestones = api(prefix + "/milestones?state=all&per_page=100")
        numbers = {row["title"]: row["number"] for row in milestones}
        for gate in ["Q0", "P0", "Q1", "Q2"]:
            if gate not in numbers:
                numbers[gate] = api(prefix + "/milestones", {"title": gate, "description": "Evidence-backed " + gate + " delivery gate"})["number"]
        existing = api(prefix + "/issues?state=all&per_page=100")
        by_package = {}
        for row in existing:
            match = re.match(r"^(WP-\d{2}):", row["title"])
            if "pull_request" not in row and match:
                if match[1] in by_package:
                    raise RuntimeError("Duplicate work-package issue identity")
                by_package[match[1]] = row
        with (ROOT / "plans/work-packages.csv").open(encoding="utf-8", newline="") as stream:
            packages = list(csv.DictReader(stream))
        with (ROOT / "plans/requirement-traceability.csv").open(encoding="utf-8", newline="") as stream:
            trace = list(csv.DictReader(stream))
        links = []
        for package in packages:
            title = package["id"] + ": " + package["title"]
            ids = [row["requirement_id"] for row in trace if row["primary_work_package"] == package["id"]]
            body = (f'Work package: {package["id"]}\n\n'
                    f'First delivery: {package["first_delivery"]}; completion gate: {package["completion_gate"]}.\n\n'
                    f'Prerequisites: {package["depends_on"] or "None"}.\n\n'
                    f'Deliverables: {package["outputs"]}.\n\n'
                    f'Requirements: {", ".join(ids) or "Integration of supporting requirements"}.\n\n'
                    f'Automated suites: {package["automated_suites"]}.\n\n'
                    'Delivery scope: Windows-only Q0/P0/Q1/Q2. Optional macOS/Linux configurations are uncommitted stretch goals outside all work packages and release gates.\n\n'
                    f'Inventory policy: {"WP-01 is complete on the acquired 55-file six-case baseline; remaining qualification gaps are owned by later packages" if package["id"] == "WP-01" else "Use the completed WP-01 inventory and retain the affected qualification/publication gates"}.\n\n'
                    'Acceptance and detailed tasks: plans/FCST-Implementation-Plan.md. '
                    'Completion requires executable evidence; no manual acceptance execution is assigned to the user. '
                    'Keep restricted fixtures and raw evidence in authorized local storage.\n')
            if package["id"] in by_package:
                issue = by_package[package["id"]]
                api(prefix + "/issues/" + str(issue["number"]), {"title": title, "body": body,
                    "milestone": numbers[package["completion_gate"]]}, method="PATCH")
            else:
                issue = api(prefix + "/issues", {"title": title, "body": body,
                                                 "milestone": numbers[package["completion_gate"]]})
            links.append({"work_package": package["id"], "issue": issue["html_url"], "number": issue["number"]})
            print(package["id"] + " issue ready", flush=True)
        (ROOT / "plans/github-backlog.json").write_text(json.dumps({"repository": repository, "issues": links}, indent=2) + "\n")
        api(prefix + "/actions/permissions/workflow", {"default_workflow_permissions": "read",
                                                       "can_approve_pull_request_reviews": False}, method="PUT")
        api(prefix + "/actions/permissions", {"enabled": True, "allowed_actions": "selected"}, method="PUT")
        api(prefix + "/actions/permissions/selected-actions", {"github_owned_allowed": True,
                                                               "verified_allowed": False,
                                                               "patterns_allowed": []}, method="PUT")
    else:
        api(prefix + "/branches/main/protection", {
            "required_status_checks": {"strict": True, "contexts": config["required_checks"]},
            "enforce_admins": True,
            "required_pull_request_reviews": {"dismiss_stale_reviews": True, "require_code_owner_reviews": True,
                                              "required_approving_review_count": 0},
            "restrictions": None, "required_conversation_resolution": True,
            "allow_force_pushes": False, "allow_deletions": False}, method="PUT")
        existing = api(prefix + "/rulesets")
        if not any(row.get("name") == "Protect release branches" for row in existing):
            api(prefix + "/rulesets", {"name": "Protect release branches", "target": "branch", "enforcement": "active",
                "conditions": {"ref_name": {"include": ["refs/heads/release/**"], "exclude": []}},
                "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
                          {"type": "pull_request", "parameters": {"required_approving_review_count": 0,
                           "dismiss_stale_reviews_on_push": True, "require_code_owner_review": True,
                           "require_last_push_approval": False, "required_review_thread_resolution": True}},
                          {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": True,
                           "required_status_checks": [{"context": check} for check in config["required_checks"]]}}]})
        print("Branch protections configured")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error) if isinstance(error, RuntimeError) else "GitHub setup unavailable", file=sys.stderr)
        raise SystemExit(1)
