# SPDX-License-Identifier: MIT OR Apache-2.0
"""Cross-check acquired originals against pinned upstream Git trees and publish metadata only."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from fcst_tools.inventory import include_references, safe_relative, static_observations
from fcst_tools.privacy import POLICY_PATH, Scanner


def main():
    catalog = json.loads((ROOT / "inventory/acquisition-sources.json").read_text())
    acquisition = json.loads((ROOT / ".local/corpus/acquisition.json").read_text())
    acquired = {(row["source_id"], row["path"]): row for row in acquisition["files"]}
    policy = json.loads(POLICY_PATH.read_text())
    records = []
    for source in catalog["sources"]:
        process = subprocess.run(["gh", "api", f'repos/{source["repository"]}/git/trees/{source["revision"]}?recursive=1'],
                                 capture_output=True, text=True, timeout=60)
        if process.returncode:
            raise ValueError("Pinned source tree unavailable")
        tree = json.loads(process.stdout)
        if tree.get("truncated"):
            raise ValueError("Incomplete source tree")
        blobs = {row["path"]: row for row in tree["tree"] if row["type"] == "blob"}
        declared_paths = {entry["path"] for entry in source["files"]}
        for entry in source["files"]:
            original = ROOT / ".local/corpus/originals" / source["id"] / Path(*PurePosixPath(entry["path"]).parts)
            data = original.read_bytes()
            row = acquired[(source["id"], entry["path"])]
            if (hashlib.sha256(data).hexdigest() != row["sha256"] or row["git_blob_sha1"] != blobs[entry["path"]]["sha"]
                    or len(data) != blobs[entry["path"]]["size"]):
                raise ValueError("Original differs from pinned upstream blob")
            observations = static_observations(entry["role"], data)
            dependencies = []
            privacy = Scanner(policy)
            if observations["format"] not in {"HDF5", "DWG"}:
                text = data.decode("utf-8", errors="replace")
                privacy.text(text, source["id"] + "/" + entry["path"])
                for reference in include_references(text):
                    target = str(PurePosixPath(entry["path"]).parent / reference) if safe_relative(reference) else None
                    resolved = target in declared_paths
                    dependencies.append({"reference_sha256": hashlib.sha256(reference.encode()).hexdigest(),
                                         "target_path": target if resolved else None, "resolved": resolved})
            records.append({**row, "git_tree_verified": True, "publication": "hold_original",
                            "privacy_categories": sorted({finding["category"] for finding in privacy.findings}),
                            "metadata_inspection": "blocked_binary" if observations["format"] in {"HDF5", "DWG"} else "pattern_scan_only",
                            "observations": observations, "static_dependencies": dependencies})
        print(source["id"] + ": original hashes verified against upstream tree", flush=True)
    report = {"schema_version": 1, "scope": "Public provenance metadata only; no raw model bytes or original matched values",
              "files": records}
    scanner = Scanner(policy)
    content = (json.dumps(report, indent=2) + "\n").encode()
    scanner.scan("source-lock.json", content)
    if scanner.findings:
        raise ValueError("Derived metadata not cleared for publication")
    (ROOT / "inventory/source-lock.json").write_bytes(content)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError):
        print("Corpus lock incomplete; source contents and sensitive values omitted")
        raise SystemExit(1)
