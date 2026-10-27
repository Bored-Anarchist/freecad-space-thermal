# SPDX-License-Identifier: MIT OR Apache-2.0
"""Verify publication-safe corpus metadata; qualification never substitutes static inspection for vendor execution."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from fcst_tools.inventory import load_inventory, rows, validate_inventory, verify_local


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", dest="verify_originals", action="store_true", help="Also verify preserved originals without executing them")
    parser.add_argument("--qualify", action="store_true", help="Require full WP-01 closure; unavailable prerequisites fail")
    args = parser.parse_args()
    data = load_inventory()
    errors = validate_inventory(data,
        {row["profile_id"] for row in rows(ROOT / "spec/compatibility-profiles.csv")},
        {row["id"] for row in rows(ROOT / "spec/requirements.csv")},
        {row["id"] for row in rows(ROOT / "plans/work-packages.csv")})
    findings = verify_local(data, ROOT / ".local/corpus/originals") if args.verify_originals else []
    blockers = data["gaps"]["gaps"] if args.qualify else []
    report = {"scope": "Inventory consistency and inert acquisition only; no product compatibility or native solving qualification",
              "status": "failed" if errors or findings else "blocked" if blockers else "passed",
              "sources": len(data["catalog"]["sources"]), "files": len(data["lock"]["files"]),
              "models": len(data["models"]["models"]), "profiles": len(data["coverage"]), "features": len(data["features"]),
              "errors": errors, "findings": findings, "blockers": [{"id": row["id"], "category": row["category"]} for row in blockers]}
    output = ROOT / ".local/corpus" / ("qualification.json" if args.qualify else "inventory-verification.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError):
        print('{"status":"failed","errors":["inventory_inspection_unavailable"]}')
        raise SystemExit(1)
