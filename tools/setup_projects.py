# SPDX-License-Identifier: MIT OR Apache-2.0
"""Create/link the approved FCST Project and synchronize its delivery backlog."""
from __future__ import annotations
import csv
import json
import subprocess
from pathlib import Path
from setup_github import api, cleared

ROOT = Path(__file__).resolve().parents[1]
STATES = ["Planned", "Ready", "In progress", "Blocked", "Complete"]


def gh(*args, json_output=True):
    cleared({"arguments": args})
    result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError("GitHub Projects operation unavailable")
    return json.loads(result.stdout) if json_output else result.stdout


def graphql(query, **variables):
    result = api("graphql", {"query": query, "variables": variables})
    if result.get("errors"):
        raise RuntimeError("GitHub Projects API rejected the requested operation")
    return result["data"]


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    config = json.loads((ROOT / "ci/github.json").read_text())
    owner = config["maintainer"]
    projects = gh("project", "list", "--owner", owner, "--limit", "100", "--format", "json")["projects"]
    matching = [project for project in projects if project["title"] == config["projects_title"]]
    if len(matching) > 1:
        raise RuntimeError("Ambiguous project title; refusing to choose a destination")
    project = matching[0] if matching else gh("project", "create", "--owner", owner,
                                             "--title", config["projects_title"], "--format", "json")
    number = str(project["number"])
    project_id = project["id"]
    backlog = json.loads((ROOT / "plans/github-backlog.json").read_text())
    packages = read_rows(ROOT / "plans/work-packages.csv")
    trace = read_rows(ROOT / "plans/requirement-traceability.csv")
    links = {row["work_package"]: row for row in backlog["issues"]}
    existing = gh("project", "item-list", number, "--owner", owner, "--limit", "100", "--format", "json")["items"]
    desired_urls = {row["issue"] for row in links.values()}
    if any(item.get("content", {}).get("url") not in desired_urls for item in existing):
        raise RuntimeError("Project contains unrelated items; refusing to repurpose it")
    gh("project", "link", number, "--owner", owner, "--repo", config["repository"], json_output=False)
    gh("project", "edit", number, "--owner", owner, "--visibility", "PUBLIC", "--description",
       "FCST work packages, requirement links, prerequisites and evidence-backed delivery states", "--format", "json")
    fields = gh("project", "field-list", number, "--owner", owner, "--format", "json")["fields"]
    status_field = next(field for field in fields if field["name"] == "Status")
    if [option["name"] for option in status_field["options"]] != STATES:
        aliases = {"Planned": "Todo", "In progress": "In Progress", "Complete": "Done"}
        old = {option["name"]: option["id"] for option in status_field["options"]}
        colors = ["GRAY", "BLUE", "YELLOW", "ORANGE", "GREEN"]
        options = []
        for state, color in zip(STATES, colors):
            option = {"name": state, "color": color, "description": "FCST delivery state: " + state}
            option_id = old.get(state) or old.get(aliases.get(state))
            if option_id:
                option["id"] = option_id
            options.append(option)
        graphql("mutation($input:UpdateProjectV2FieldInput!){ updateProjectV2Field(input:$input){ projectV2Field { ... on ProjectV2SingleSelectField { id } } } }",
                input={"fieldId": status_field["id"], "singleSelectOptions": options})
    for name, data_type, options in [("Work package", "TEXT", None), ("Completion gate", "SINGLE_SELECT", "Q0,P0,Q1,Q2,POST-Q2"),
                                     ("Prerequisites", "TEXT", None), ("Requirements", "TEXT", None), ("Owner role", "TEXT", None)]:
        if not any(field["name"] == name for field in fields):
            args = ["project", "field-create", number, "--owner", owner, "--name", name,
                    "--data-type", data_type, "--format", "json"]
            if options:
                args += ["--single-select-options", options]
            fields.append(gh(*args))
    fields = {field["name"]: field for field in gh("project", "field-list", number, "--owner", owner, "--format", "json")["fields"]}
    gate_field = fields["Completion gate"]
    if {option["name"] for option in gate_field["options"]} != {"Q0", "P0", "Q1", "Q2", "POST-Q2"}:
        options = [{"id": option["id"], "name": option["name"], "color": "GRAY", "description": "Delivery gate: " + option["name"]}
                   for option in gate_field["options"]]
        options.append({"name": "POST-Q2", "color": "ORANGE", "description": "Deferred ports after Windows Q2"})
        graphql("mutation($input:UpdateProjectV2FieldInput!){updateProjectV2Field(input:$input){projectV2Field{... on ProjectV2SingleSelectField{id}}}}",
                input={"fieldId": gate_field["id"], "singleSelectOptions": options})
        fields = {field["name"]: field for field in gh("project", "field-list", number, "--owner", owner, "--format", "json")["fields"]}
    existing_by_url = {item.get("content", {}).get("url"): item for item in existing}
    records = []
    for package in packages:
        package_id = package["id"]
        issue_url = links[package_id]["issue"]
        item = existing_by_url.get(issue_url) or gh("project", "item-add", number, "--owner", owner,
                                                   "--url", issue_url, "--format", "json")
        state = {"in_progress": "In progress", "blocked": "Blocked", "complete": "Complete"}.get(package["status"], "Planned")
        # Native contract work can proceed while the vendor inventory is blocked.
        if package_id in {"WP-01", "WP-03"} and state == "Planned":
            state = "Ready"
        values = {"Status": {"singleSelectOptionId": next(option["id"] for option in fields["Status"]["options"] if option["name"] == state)},
                  "Work package": {"text": package_id},
                  "Completion gate": {"singleSelectOptionId": next(option["id"] for option in fields["Completion gate"]["options"] if option["name"] == package["completion_gate"])},
                  "Prerequisites": {"text": package["depends_on"] or "None"},
                  "Requirements": {"text": ";".join(row["requirement_id"] for row in trace if row["primary_work_package"] == package_id) or "Integration of supporting requirements"},
                  "Owner role": {"text": package["lead"]}}
        variables = {}
        declarations = []
        mutations = []
        for index, (name, value) in enumerate(values.items()):
            key = "v" + str(index)
            declarations.append("$" + key + ":UpdateProjectV2ItemFieldValueInput!")
            mutations.append(key + ":updateProjectV2ItemFieldValue(input:$" + key + "){projectV2Item{id}}")
            variables[key] = {"projectId": project_id, "itemId": item["id"], "fieldId": fields[name]["id"], "value": value}
        graphql("mutation(" + ",".join(declarations) + "){" + " ".join(mutations) + "}", **variables)
        records.append({"work_package": package_id, "issue": issue_url, "item_id": item["id"], "state": state})
        print(package_id + ": " + state, flush=True)
    record = {"repository": config["repository"], "owner": owner, "project_id": project_id,
              "number": project["number"], "title": project["title"], "url": project["url"],
              "states": STATES, "items": records}
    cleared(record)
    (ROOT / "plans/github-project.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("Project populated: " + project["url"])


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, OSError, subprocess.SubprocessError):
        print("Project setup incomplete; no credentials or raw API output included")
        raise SystemExit(1)
