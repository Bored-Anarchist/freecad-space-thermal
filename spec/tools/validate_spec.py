"""Validate this design package and regenerate the derived requirements CSV.

Uses the standard library for register/link checks. JSON Schema validation needs
the jsonschema package; no software or engineering qualification is performed.
Run from any directory with the bundled workspace Python or another environment
containing jsonschema. --write-register regenerates requirements.csv.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from project_files import markdown_files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-register", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    spec_dir = root / "spec"
    spec_path = spec_dir / "FreeCAD-Space-Thermal-Specification.md"
    content = spec_path.read_text(encoding="utf-8")
    rows = []
    for line in content.splitlines():
        if not re.match(r"^\| [A-Z]+-\d{3} \|", line):
            continue
        fields = [item.strip() for item in line.strip().strip("|").split("|")]
        assert len(fields) == 5, f"Malformed requirement row: {line}"
        req_id, requirement, verification, basis, gate = fields
        assert "shall" in requirement.lower(), f"Missing shall: {req_id}"
        assert gate in {"Q0", "Q1", "Q2"}, f"Unknown gate: {req_id}"
        assert verification and basis, f"Incomplete requirement: {req_id}"
        rows.append({
            "id": req_id,
            "requirement": requirement,
            "verification_acceptance": verification,
            "basis": basis,
            "gate": gate,
        })
    assert rows, "No requirements found"
    counts = Counter(row["id"] for row in rows)
    assert all(count == 1 for count in counts.values()), "Duplicate requirement IDs"

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    csv_path = spec_dir / "requirements.csv"
    expected_csv = output.getvalue()
    if args.write_register:
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            stream.write(expected_csv)
    assert csv_path.read_text(encoding="utf-8") == expected_csv, "Requirements CSV is stale"

    sources = (spec_dir / "sources.md").read_text(encoding="utf-8")
    defined_sources = set(re.findall(r"^\| (S\d{2}) \|", sources, flags=re.MULTILINE))
    used_sources = set(re.findall(r"\bS\d{2}\b", content))
    assert used_sources <= defined_sources, f"Missing sources: {used_sources - defined_sources}"
    for path in markdown_files(root):
        text = path.read_text(encoding="utf-8")
        for _, target in re.findall(r"\[([^\]]*)\]\(([^)]+)\)", text):
            if "://" in target or target.startswith("#") or target.startswith("mailto:"):
                continue
            local_target = target.split("#", 1)[0].strip("<>")
            assert (path.parent / local_target).exists(), f"Broken link in {path.name}: {target}"

    with (spec_dir / "compatibility-profiles.csv").open(encoding="utf-8", newline="") as stream:
        profiles = list(csv.DictReader(stream))
    profile_ids = [profile["profile_id"] for profile in profiles]
    assert len(profile_ids) == len(set(profile_ids)), "Duplicate profiles"
    assert all(profile["initial_status"] == "unqualified" for profile in profiles)
    by_id = {profile["profile_id"]: profile for profile in profiles}
    assert by_id["TD-NATIVE"]["required_gate"] == by_id["ESA-NATIVE"]["required_gate"] == "Q1"

    from jsonschema import Draft202012Validator, FormatChecker, RefResolver

    def read_json(path: Path):
        def reject_constant(value):
            raise ValueError(f"Nonfinite JSON number: {value}")
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)

    schemas = {}
    for path in (spec_dir / "schemas").glob("*.json"):
        schema = read_json(path)
        Draft202012Validator.check_schema(schema)
        # The empty-document store also handles older jsonschema releases whose
        # URI resolver cannot join a fragment against a URN base identifier.
        resolver = RefResolver.from_schema(schema, store={"": schema})
        schemas[path.name] = Draft202012Validator(
            schema, resolver=resolver, format_checker=FormatChecker()
        )
    example_manifest = read_json(spec_dir / "examples" / "project-manifest.json")
    conductor = read_json(spec_dir / "examples" / "create-conductor.json")
    schemas["project-manifest.schema.json"].validate(example_manifest)
    schemas["operation-envelope.schema.json"].validate(conductor)
    schemas["create-conductor.arguments.schema.json"].validate(conductor["arguments"])

    print(json.dumps({
        "requirements": len(rows),
        "requirements_by_gate": dict(Counter(row["gate"] for row in rows)),
        "compatibility_profiles": len(profiles),
        "primary_source_groups": len(defined_sources),
        "json_schemas": len(schemas),
        "schema_examples": 2,
        "checks": "PASS: registers, unique IDs, source references, local links, gate parity, JSON Schemas and examples",
        "scope": "Document consistency only; no solver, legacy-format or standards qualification performed",
    }, indent=2))


if __name__ == "__main__":
    main()
