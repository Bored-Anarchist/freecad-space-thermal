"""Check planning coverage and consistency using only the Python standard library.

This checks a plan, not a thermal engine, a legacy adapter, or actual test results.
Implementation progress needs evidence records; unqualified requirement, suite
and compatibility records remain planned.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "python"))
from project_files import markdown_files
from fcst_tools.delivery import validate_scope
PLANS = ROOT / "plans"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_rows(path: Path, key: str) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(bool(rows), f"Empty register: {path.name}")
    require(all(None not in row and all(value is not None for value in row.values()) for row in rows),
            f"Malformed CSV fields: {path.name}")
    require(all(row.get(key) for row in rows), f"Missing {key}: {path.name}")
    keys = [row[key] for row in rows]
    require(len(keys) == len(set(keys)), f"Duplicate {key}: {path.name}")
    return {row[key]: row for row in rows}


def split_ids(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def main() -> None:
    baseline = read_rows(ROOT / "spec" / "requirements.csv", "id")
    testing = read_rows(PLANS / "automated-test-requirements.csv", "id")
    packages = read_rows(PLANS / "work-packages.csv", "id")
    suites = read_rows(PLANS / "test-suites.csv", "id")
    trace = read_rows(PLANS / "requirement-traceability.csv", "requirement_id")
    profiles = read_rows(ROOT / "spec" / "compatibility-profiles.csv", "profile_id")
    profile_plan = read_rows(PLANS / "compatibility-test-plan.csv", "profile_id")
    require(not (set(baseline) & set(testing)), "Test requirement IDs collide with baseline IDs")

    # Check the authoritative tables without needing the spec validator's jsonschema dependency.
    normative = {}
    for line in (ROOT / "spec" / "FreeCAD-Space-Thermal-Specification.md").read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\| [A-Z]+-\d{3} \|", line):
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        require(len(parts) == 5, f"Malformed normative row: {line}")
        req_id, requirement, verification, basis, gate = parts
        require(req_id not in normative, f"Duplicate normative requirement: {req_id}")
        normative[req_id] = dict(id=req_id, requirement=requirement,
                                 verification_acceptance=verification, basis=basis, gate=gate)
    require(normative == baseline, "Baseline requirements CSV differs from specification tables")

    plan_path = PLANS / "FCST-Implementation-Plan.md"
    plan_text = plan_path.read_text(encoding="utf-8")
    described_packages = re.findall(r"^### Step \d+ — (WP-\d{2}):", plan_text, flags=re.MULTILINE)
    require(Counter(described_packages) == Counter({key: 1 for key in packages}),
            "Plan steps and work-package register differ")
    described_tests = re.findall(r"^\| (TST-\d{3}) \|", plan_text, flags=re.MULTILINE)
    require(Counter(described_tests) == Counter({key: 1 for key in testing}),
            "Plan test requirements and register differ")
    described_suites = re.findall(r"^\| (SUITE-[A-Z]+) \|", plan_text, flags=re.MULTILINE)
    require(Counter(described_suites) == Counter({key: 1 for key in suites}),
            "Plan suite descriptions and register differ")

    def check_suites(row: dict[str, str], context: str) -> None:
        identifiers = split_ids(row["automated_suites"])
        require(bool(identifiers), f"No automated suites: {context}")
        require(len(identifiers) == len(set(identifiers)), f"Duplicate suite: {context}")
        require(set(identifiers) <= set(suites), f"Unknown suite: {context}")

    valid_gates = {"Q0", "P0", "Q1", "Q2"}
    gate_rank = {gate: rank for rank, gate in enumerate(["Q0", "P0", "Q1", "Q2"])}
    for package_id, package in packages.items():
        require(re.fullmatch(r"WP-\d{2}", package_id) is not None, f"Invalid package ID: {package_id}")
        require(package["lead"] and package["outputs"], f"Missing owner/output: {package_id}")
        require(package["first_delivery"] in valid_gates and package["completion_gate"] in valid_gates,
                f"Unknown package gate: {package_id}")
        require(gate_rank[package["first_delivery"]] <= gate_rank[package["completion_gate"]],
                f"First delivery after completion: {package_id}")
        dependencies = split_ids(package["depends_on"])
        require(len(dependencies) == len(set(dependencies)), f"Duplicate dependency: {package_id}")
        require(set(dependencies) <= set(packages), f"Unknown dependency: {package_id}")
        require(package_id not in dependencies, f"Self dependency: {package_id}")
        require(package["status"] in {"planned", "in_progress", "blocked", "complete"},
                f"Unknown implementation status: {package_id}")
        if package["status"] != "planned":
            evidence_path = PLANS / "evidence" / (package_id + ".json")
            require(evidence_path.is_file(), f"Missing implementation evidence: {package_id}")
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            require(evidence.get("work_package") == package_id and evidence.get("status") == package["status"],
                    f"Implementation evidence status mismatch: {package_id}")
            require(bool(evidence.get("checks")), f"Empty implementation evidence: {package_id}")
            if package["status"] == "complete":
                require(not evidence.get("blockers") and all(row["status"] == "passed" for row in evidence["checks"]),
                        f"Incomplete work marked complete: {package_id}")
        check_suites(package, package_id)

    # A package dependency refers to an available interface/slice, not necessarily
    # the other package's full qualification. Still require an acyclic graph.
    visiting, visited, order = set(), set(), []

    def visit(package_id: str) -> None:
        require(package_id not in visiting, f"Dependency cycle at {package_id}")
        if package_id in visited:
            return
        visiting.add(package_id)
        for dependency in split_ids(packages[package_id]["depends_on"]):
            visit(dependency)
        visiting.remove(package_id)
        visited.add(package_id)
        order.append(package_id)

    for package_id in packages:
        visit(package_id)

    all_requirements = {**baseline, **testing}
    require(set(trace) == set(all_requirements),
            f"Traceability mismatch: missing={set(all_requirements) - set(trace)}, extra={set(trace) - set(all_requirements)}")
    for req_id, requirement in all_requirements.items():
        row = trace[req_id]
        is_test = req_id in testing
        expected_source = "plans/automated-test-requirements.csv" if is_test else "spec/requirements.csv"
        require(row["source"] == expected_source, f"Wrong requirement source: {req_id}")
        require(row["required_gate"] == requirement["gate"], f"Requirement gate changed: {req_id}")
        require(row["primary_work_package"] in packages, f"Missing package owner: {req_id}")
        primary = packages[row["primary_work_package"]]
        require(gate_rank[primary["completion_gate"]] <= gate_rank[row["required_gate"]],
                f"Primary work completes after requirement gate: {req_id}")
        supporting = split_ids(row["supporting_work_packages"])
        require(set(supporting) <= set(packages), f"Unknown supporting package: {req_id}")
        require(len(supporting) == len(set(supporting)), f"Duplicate supporting package: {req_id}")
        require(row["primary_work_package"] not in supporting, f"Primary repeated as support: {req_id}")
        require(bool(row["evidence_contract"]), f"Missing evidence contract: {req_id}")
        require(row["status"] == "planned", f"Unsubstantiated test result: {req_id}")
        check_suites(row, req_id)
        if is_test:
            require("shall" in requirement["requirement"].lower(), f"Nonmandatory test requirement: {req_id}")
            require(row["primary_work_package"] == requirement["primary_work_package"],
                    f"Test owner mismatch: {req_id}")
            require(row["automated_suites"] == requirement["automated_suites"], f"Test suite mismatch: {req_id}")
            require(row["evidence_contract"] == requirement["verification_acceptance"],
                    f"Test acceptance evidence mismatch: {req_id}")

    require((ROOT / "AGENTS.md").is_file(), "Missing standing repository/privacy instructions")
    require("TST-021" in testing, "Missing publication-privacy delivery requirement")

    require(set(profile_plan) == set(profiles), "Missing or unknown planned compatibility profile")
    for profile_id, profile in profiles.items():
        row = profile_plan[profile_id]
        require(row["required_gate"] == profile["required_gate"], f"Profile gate changed: {profile_id}")
        require(row["required_directions"] == profile["required_directions"], f"Profile directions changed: {profile_id}")
        require(row["primary_work_package"] in packages, f"Profile has no owner: {profile_id}")
        require(row["planned_scenarios"] and row["prerequisites"], f"Missing profile test plan: {profile_id}")
        require(row["status"] == "planned", f"Unsubstantiated profile qualification: {profile_id}")
        require(profile["initial_status"] == "unqualified", f"Baseline profile status changed: {profile_id}")
        check_suites(row, profile_id)
    require(profiles["TD-NATIVE"]["required_gate"] == profiles["ESA-NATIVE"]["required_gate"] == "Q1",
            "TD/ESA equal Q1 gate changed")

    for suite_id, suite in suites.items():
        require(suite["status"] == "planned", f"Unsubstantiated suite implementation: {suite_id}")
        require(suite["runner"] and suite["triggers"] and suite["evidence_contract"], f"Incomplete suite: {suite_id}")
        require(suite["first_gate"] in valid_gates, f"Unknown suite gate: {suite_id}")

    def document(name):
        return json.loads((ROOT / name).read_text(encoding="utf-8"))
    require(not validate_scope(document("plans/delivery-scope.json"), list(packages.values()),
            document("plans/evidence/WP-01.json"), document("inventory/gaps.json"),
            document("CMakePresets.json"), document("ci/host-profile.json")), "Delivery scope drift")

    for path in markdown_files(ROOT):
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            local_path = target.split("#", 1)[0].strip("<>")
            require((path.parent / local_path).exists(), f"Broken local link: {path.name}: {target}")

    print(json.dumps({
        "baseline_requirements": len(baseline),
        "baseline_requirements_by_gate": dict(Counter(row["gate"] for row in baseline.values())),
        "automated_test_requirements": len(testing),
        "planned_coverage_records": len(trace),
        "work_packages": len(packages),
        "automated_suites": len(suites),
        "compatibility_profiles_planned": len(profile_plan),
        "dependency_order": order,
        "checks": "PASS: baseline fidelity, complete planned traceability, gates, ownership, acyclic dependencies, suites, profiles and local links",
        "scope": "Planning consistency only; no product tests, numerical qualification or file compatibility performed",
    }, indent=2))


if __name__ == "__main__":
    main()
