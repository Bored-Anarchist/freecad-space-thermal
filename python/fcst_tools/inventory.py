# SPDX-License-Identifier: MIT OR Apache-2.0
"""Corpus consistency and inert inspection; never execute imported model logic."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
OPERATIONS = {"inspect", "represent", "edit", "native_execute", "write", "source_reopen_run", "cross_tool_exchange"}


def include_references(text: str) -> list[str]:
    return [match.group(1) or match.group(2) for match in re.finditer(
        r'''(?im)^\s*(?:INSERT|INCLUDE|\$INCLUDE|\#include)\s+(?:["']([^"']+)["']|([^\s;]+))''', text)]


def safe_relative(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts and ":" not in value and "\\" not in value


def static_observations(role: str, data: bytes) -> dict:
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("Inspection byte limit")
    if data.startswith(b"\x89HDF\r\n\x1a\n"):
        return {"format": "HDF5", "metadata_inspected": False, "can_execute": False}
    if re.fullmatch(rb"AC[0-9]{4}", data[:6]):
        return {"format": "DWG", "container_signature": data[:6].decode(),
                "vendor_version_identified": False, "metadata_inspected": False, "can_execute": False}
    text = data.decode("utf-8", errors="replace")
    versions = sorted(set(re.findall(r"ESATAN-TMS\s+([0-9]{4}(?:\s+sp[0-9]+)?)", text, re.I)))
    td_versions = sorted(set(re.findall(r"Thermal Desktop\s+([0-9]+(?:\.[0-9]+){1,3})", text, re.I)))
    result = {"format": "text", "can_execute": False, "external_reference_count": len(include_references(text))}
    if versions:
        result["source_version_headers"] = versions
    if td_versions:
        result["thermal_desktop_version_headers"] = td_versions
    if role in {"steady_deck", "transient_deck"}:
        result.update(format="esatan_ddeck", sections=sorted(set(re.findall(r"(?m)^\s*\$([A-Z][A-Z0-9_]*)", text))),
                      node_declaration_counts={kind: len(re.findall(r"(?m)^\s*" + kind + r"[0-9]+\s*=", text)) for kind in ["D", "B", "A"]},
                      coupling_declaration_counts={kind: len(re.findall(r"\b" + kind + r"\s*\(", text)) for kind in ["GL", "GR"]},
                      logic_retained_inert=True)
    elif role == "step_tas_exchange":
        result.update(format="step_part21", schema_names=re.findall(r"FILE_SCHEMA\s*\(\s*\(\s*'([A-Za-z0-9_]+)'", text, re.I),
                      schema_validated=False)
    elif role in {"network_entrypoint", "network_include"}:
        result.update(format="sinda_text", header_section_count=len(re.findall(r"(?im)^\s*HEADER\b", text)),
                      logic_retained_inert=True)
    elif role == "source_logic":
        result.update(format="source_text", logic_retained_inert=True)
    return result


def rows(path: Path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def load_inventory(root: Path = ROOT) -> dict:
    directory = root / "inventory"
    return {"catalog": json.loads((directory / "acquisition-sources.json").read_text()),
            "lock": json.loads((directory / "source-lock.json").read_text()),
            "models": json.loads((directory / "models.json").read_text()),
            "features": rows(directory / "feature-map.csv"),
            "coverage": rows(directory / "profile-coverage.csv"),
            "gaps": json.loads((directory / "gaps.json").read_text())}


def validate_inventory(data: dict, profile_ids: set[str], requirement_ids: set[str], package_ids: set[str]) -> list[str]:
    errors = []
    def need(condition, category):
        if not condition:
            errors.append(category)
    sources = {row["id"]: row for row in data["catalog"]["sources"]}
    need(len(sources) == len(data["catalog"]["sources"]), "duplicate_source")
    expected_files = {(source["id"], file["path"]) for source in sources.values() for file in source["files"]}
    locked = {(row["source_id"], row["path"]): row for row in data["lock"]["files"]}
    need(len(locked) == len(data["lock"]["files"]) and set(locked) == expected_files, "missing_or_duplicate_file_provenance")
    for source in sources.values():
        need(bool(re.fullmatch(r"[a-f0-9]{40}", source.get("revision", ""))), "unfrozen_source_revision")
        need(bool(source.get("repository_license")), "missing_rights_record")
        need(all(safe_relative(file["path"]) for file in source["files"]), "unsafe_source_path")
    for key, file in locked.items():
        need(file.get("revision") == sources.get(key[0], {}).get("revision"), "source_revision_mismatch")
        need(bool(re.fullmatch(r"[a-f0-9]{64}", file.get("sha256", ""))) and file.get("bytes", 0) > 0, "missing_file_hash")
        need(file.get("publication") == "hold_original", "uncleared_original_publication")
        need(file.get("git_tree_verified") is True, "unverified_upstream_blob")
        need(bool(re.fullmatch(r"[a-f0-9]{40}", file.get("git_blob_sha1", ""))), "missing_upstream_blob_hash")
        dependencies = file.get("static_dependencies", [])
        need(len(dependencies) == file.get("observations", {}).get("external_reference_count", 0), "dependency_reference_omitted")
        for dependency in dependencies:
            target = dependency.get("target_path")
            need(bool(re.fullmatch(r"[a-f0-9]{64}", dependency.get("reference_sha256", ""))), "missing_dependency_reference_hash")
            if dependency.get("resolved"):
                need((key[0], target) in locked, "dependency_target_missing")
            else:
                need(target is None, "unresolved_dependency_leaks_path")
    models = {row["id"]: row for row in data["models"]["models"]}
    need(len(models) == len(data["models"]["models"]), "duplicate_model")
    for model in models.values():
        source = sources.get(model.get("source_id"))
        need(source is not None and bool(model.get("owner_role")), "unassigned_model")
        need(set(model.get("profiles", [])) <= profile_ids and bool(model.get("profiles")), "unknown_model_profile")
        need(set(model.get("required_operations", [])) == OPERATIONS, "operation_coverage_missing")
        dispositions = model.get("operation_dispositions", {})
        need(set(dispositions) == OPERATIONS, "operation_disposition_missing")
        need(all(value.get("status") in {"planned", "blocked", "not_applicable"} and bool(value.get("reason"))
                 for value in dispositions.values()), "unsupported_operation_claim")
        need(model.get("qualification") == "unqualified", "unsupported_qualification_claim")
        version = model.get("source_version", {})
        need(version.get("status") in {"observed", "unknown"} and bool(version.get("evidence")), "unidentified_version_not_dispositioned")
        if version.get("status") == "unknown":
            need(bool(model.get("blockers")), "unknown_version_without_blocker")
        files = [locked.get((model.get("source_id"), path)) for path in model.get("files", [])]
        need(bool(files) and all(file is not None for file in files), "missing_model_file")
        need(bool(model.get("dependency_review")) and bool(model.get("reference_results")), "missing_dependency_or_reference_disposition")
        unresolved = any(not dependency.get("resolved") for file in files if file is not None
                         for dependency in file.get("static_dependencies", []))
        if unresolved:
            need(bool(model.get("blockers")) and model.get("dependency_review", {}).get("status") != "complete",
                 "unresolved_dependency_without_blocker")
        need(model.get("rights", {}).get("redistribution") == "hold", "rights_hold_missing")
        if model.get("purpose") == "syntax_only":
            need(model.get("reference_results", {}).get("physical_oracle") is False, "syntax_fixture_used_as_physics_oracle")
    feature_ids = {row["feature_id"] for row in data["features"]}
    need(len(feature_ids) == len(data["features"]), "duplicate_feature")
    for feature in data["features"]:
        need(feature["work_package"] in package_ids and bool(feature["owner_role"]) and bool(feature["engine_component"]), "unassigned_feature")
        need(bool(feature["requirement_ids"]) and set(feature["requirement_ids"].split(";")) <= requirement_ids, "unknown_feature_requirement")
        fixture_ids = set(filter(None, feature["model_ids"].split(";")))
        need(fixture_ids <= set(models), "unknown_feature_model")
        need(bool(fixture_ids) or bool(feature["gap_id"]), "uncovered_feature_without_gap")
    coverage = {row["profile_id"]: row for row in data["coverage"]}
    need(len(coverage) == len(data["coverage"]) and set(coverage) == profile_ids, "profile_inventory_incomplete")
    gap_ids = {row["id"] for row in data["gaps"]["gaps"]}
    for row in coverage.values():
        need(row["owner_work_package"] in package_ids, "unassigned_profile")
        need(row["qualification"] == "unqualified" and bool(row["blocked_reason"]), "missing_profile_blocker")
        need(set(filter(None, row["model_ids"].split(";"))) <= set(models), "unknown_profile_fixture")
    for feature in data["features"]:
        need(not feature["gap_id"] or feature["gap_id"] in gap_ids, "unknown_feature_gap")
    return sorted(set(errors))


def verify_local(data: dict, originals: Path) -> list[dict]:
    findings = []
    for file in data["lock"]["files"]:
        key = file["source_id"] + "/" + file["path"]
        location = hashlib.sha256(key.encode()).hexdigest()[:20]
        if not safe_relative(file["path"]):
            findings.append({"category": "unsafe_original_path", "location_id": location})
            continue
        path = originals / file["source_id"] / Path(*PurePosixPath(file["path"]).parts)
        if not path.resolve().is_relative_to(originals.resolve()) or path.is_symlink() or not path.is_file():
            findings.append({"category": "missing_or_unsafe_original", "location_id": location})
        elif path.stat().st_size != file["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != file["sha256"]:
            findings.append({"category": "original_hash_mismatch", "location_id": location})
    return findings
