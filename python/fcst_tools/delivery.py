# SPDX-License-Identifier: MIT OR Apache-2.0
"""Scope decisions cannot silently become broader delivery/support claims."""
import re


COMMITTED_WORK_PACKAGES = frozenset({f"WP-{i:02d}" for i in range(1, 22)} | {"WP-05.5"})
FOUNDATION_CASES = frozenset(
    [f"WP055-INV-{i:03d}" for i in range(1, 3)]
    + [f"WP055-HOST-{i:03d}" for i in range(1, 5)]
    + [f"WP055-CTR-{i:03d}" for i in range(1, 6)]
    + [f"WP055-NUM-{i:03d}" for i in range(1, 3)]
    + [f"WP055-STORE-{i:03d}" for i in range(1, 5)]
    + [f"WP055-{group}-{i:03d}" for group in ("AUDIT", "TOOL", "PUB", "HAND") for i in range(1, 3)]
)


def package_from_title(title):
    match = re.match(r"^(WP-\d{2}(?:\.\d+)?):", title)
    return match[1] if match and match[1] in COMMITTED_WORK_PACKAGES else None


def validate_foundation_acceptance(rows, requirements, suites, evidence=None):
    errors = []
    identifiers = [row.get("case_id") for row in rows]
    if set(identifiers) != FOUNDATION_CASES or len(identifiers) != len(set(identifiers)):
        errors.append("foundation_acceptance_coverage_mismatch")
    for row in rows:
        reqs = row.get("requirement_ids", "").split(";")
        selected = row.get("automated_suites", "").split(";")
        if (not set(reqs) <= set(requirements) or "TST-022" not in reqs
                or len(reqs) != len(set(reqs)) or not set(selected) <= set(suites)
                or len(selected) != len(set(selected))):
            errors.append("foundation_acceptance_unknown_or_duplicate_reference")
        substantiated = row.get("status") == "planned"
        if row.get("status") == "passed" and evidence and evidence.get("status") == "complete":
            collected = evidence.get("acceptance", [])
            substantiated = (len(collected) == len(FOUNDATION_CASES)
                and {c.get("id") for c in collected} == FOUNDATION_CASES
                and all(c.get("status") == "passed" for c in collected)
                and evidence.get("input_sha256") and evidence.get("tested_candidate"))
        if (not substantiated or not row.get("owner_role")
                or not row.get("automated_acceptance") or not row.get("evidence_contract")):
            errors.append("foundation_acceptance_unsubstantiated_or_incomplete")
    return sorted(set(errors))
def validate_scope(scope, packages, evidence, gaps, presets, host):
    errors = []
    if (scope.get("active_platforms") != ["Windows"] or
            scope.get("active_presets") != ["windows-debug", "windows-release"] or
            set(host.get("platforms", {})) != {"Windows"}):
        errors.append("non_windows_active_platform")
    active = {p["name"] for p in presets.get("configurePresets", []) if not p.get("hidden")}
    if active != set(scope.get("active_presets", [])):
        errors.append("active_presets_mismatch")
    by_id = {p["id"]: p for p in packages}
    goal = scope.get("stretch_goals", {}).get("SG-PLATFORMS", {})
    if (set(by_id) != COMMITTED_WORK_PACKAGES
            or scope.get("windows_gates") != ["Q0", "P0", "Q1", "Q2"]
            or goal != {"platforms": ["macOS", "Linux"], "status": "uncommitted",
                        "work_package": None, "completion_gate": None, "blocks_delivery": False}):
        errors.append("stretch_goal_in_committed_delivery")
    foundation = by_id.get("WP-05.5", {})
    if (foundation.get("first_delivery") != "P0" or foundation.get("completion_gate") != "P0"
            or set(foundation.get("depends_on", "").split(";")) != {f"WP-{i:02d}" for i in range(1, 6)}
            or any("WP-05.5" not in by_id.get(consumer, {}).get("depends_on", "").split(";")
                   for consumer in ("WP-06", "WP-07", "WP-13", "WP-16"))):
        errors.append("foundation_handoff_missing_or_misordered")
    expected = {p: {"stretch_goal": "SG-PLATFORMS", "status": "uncommitted"} for p in ["Linux", "macOS"]}
    if scope.get("deferred_platforms") != expected:
        errors.append("missing_deferred_platform_disposition")
    if (by_id.get("WP-01", {}).get("status") != "complete" or evidence.get("status") != "complete"
            or evidence.get("blockers") or scope.get("wp01", {}).get("qualification_claim") is not False):
        errors.append("inventory_completion_or_qualification_claim_invalid")
    for gap in gaps.get("gaps", []):
        if (gap.get("owner_work_package") not in by_id or gap.get("owner_work_package") == "WP-01"
                or not gap.get("required_gate") or gap.get("status") != "blocked"):
            errors.append("qualification_gap_not_assigned")
    return sorted(set(errors))
