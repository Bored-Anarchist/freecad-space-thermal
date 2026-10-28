# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independently run the same frozen JSON vectors in Python and the native worker."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from fcst_contracts import inspect


def check(worker=None):
    fixtures = ROOT / "tests/fixtures/contracts"
    manifest = json.loads((fixtures / "cases.json").read_text())
    coverage = json.loads((ROOT / "ci/coverage.json").read_text())
    ids = [c["id"] for c in manifest["cases"]]
    if (sorted(ids) != sorted(coverage["contract_cases"]) or len(set(ids)) != len(ids)
            or any(c["status"] == "passed" and len(c.get("semantic_hash", "")) != 64 for c in manifest["cases"])):
        return [{"id": "fixture_coverage", "status": "failed"}]
    records, observed = [], {}
    for case in manifest["cases"]:
        raw = (fixtures / case["path"]).read_bytes()
        result = inspect(case["kind"], raw)
        okay = result["status"] == case["status"] and result.get("code") == case.get("code")
        if "semantic_hash" in case:
            okay &= result.get("semantic_hash") == case["semantic_hash"]
        if "same_hash_as" in case:
            okay &= result.get("semantic_hash") == observed[case["same_hash_as"]].get("semantic_hash")
        if worker:
            native = subprocess.run([str(worker), "--contract", case["kind"]], input=raw,
                                    capture_output=True, timeout=30)
            try:
                cpp = json.loads(native.stdout)
                okay &= result == cpp and native.returncode == (0 if result["status"] == "passed" else 1)
            except (ValueError, UnicodeError):
                okay = False
        observed[case["id"]] = result
        records.append({"id": case["id"], "status": "passed" if okay else "failed", "fixture_sha256": sha256(raw).hexdigest()})
    if worker:
        raw = (fixtures / "worker-progress.json").read_bytes()
        encoded = struct.pack("<I", len(raw)) + raw
        frames = [("valid", encoded), ("short", encoded[:3]), ("truncated", encoded[:-1]),
                  ("trailing", encoded + b"x"), ("oversize", struct.pack("<I", 65537)), ("empty", struct.pack("<I", 0))]
        for name, data in frames:
            result = inspect("worker-frame", data)
            native = subprocess.run([str(worker), "--contract", "worker-frame"], input=data, capture_output=True, timeout=30)
            okay = result == json.loads(native.stdout) and native.returncode == (0 if name == "valid" else 1)
            records.append({"id": "frame-" + name, "status": "passed" if okay else "failed", "fixture_sha256": sha256(data).hexdigest()})
        if sorted("frame-" + name for name, _ in frames) != sorted(coverage["contract_frames"]):
            records.append({"id": "frame_coverage", "status": "failed"})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    records = check(args.worker.resolve())
    status = "passed" if all(c["status"] == "passed" for c in records) else "failed"
    report = {"contract_version": "1.0.0", "scope": "WP-03 independent C++/Python conformance; no solver qualification", "status": status, "cases": records}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"contract_conformance": status, "cases": len(records), "failures": [r["id"] for r in records if r["status"] != "passed"]}))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
