# SPDX-License-Identifier: MIT OR Apache-2.0
"""Scope decisions cannot silently become broader delivery/support claims."""
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
    if (set(by_id) != {f"WP-{i:02d}" for i in range(1, 22)}
            or scope.get("windows_gates") != ["Q0", "P0", "Q1", "Q2"]
            or goal != {"platforms": ["macOS", "Linux"], "status": "uncommitted",
                        "work_package": None, "completion_gate": None, "blocks_delivery": False}):
        errors.append("stretch_goal_in_committed_delivery")
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
