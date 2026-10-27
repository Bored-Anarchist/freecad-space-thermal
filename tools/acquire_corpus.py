# SPDX-License-Identifier: MIT OR Apache-2.0
"""Acquire pinned public examples inertly; preserve bytes and keep originals local."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 16 * 1024 * 1024


def safe_target(root: Path, source_id: str, path: str) -> Path:
    parts = PurePosixPath(path)
    if not re.fullmatch(r"[A-Z0-9-]+", source_id) or parts.is_absolute() or ".." in parts.parts or "\\" in path or ":" in path:
        raise ValueError("Unsafe acquisition path")
    target = root / source_id / Path(*parts.parts)
    if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink():
        raise ValueError("Acquisition target escapes storage")
    return target


def acquire(catalog: dict, destination: Path) -> dict:
    records = []
    for source in catalog["sources"]:
        if not re.fullmatch(r"[a-f0-9]{40}", source["revision"]):
            raise ValueError("Acquisition must pin an immutable revision")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", source["repository"]):
            raise ValueError("Invalid public repository")
        for entry in source["files"]:
            target = safe_target(destination, source["id"], entry["path"])
            url = f'https://raw.githubusercontent.com/{source["repository"]}/{source["revision"]}/{quote(entry["path"])}'
            with urlopen(url, timeout=60) as response:
                if response.geturl() != url:
                    raise ValueError("Unexpected acquisition redirect")
                data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError("Acquisition exceeds byte limit")
            if target.exists() and target.read_bytes() != data:
                raise ValueError("Existing original differs; refusing to overwrite")
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(data)
            records.append({"source_id": source["id"], "path": entry["path"], "role": entry["role"],
                            "revision": source["revision"], "url": url, "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "git_blob_sha1": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()})
            print(source["id"] + ": " + entry["role"] + " acquired", flush=True)
    return {"schema_version": 1, "original_bytes_preserved": True, "files": records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "inventory/acquisition-sources.json")
    args = parser.parse_args()
    report = acquire(json.loads(args.catalog.read_text()), ROOT / ".local/corpus/originals")
    output = ROOT / ".local/corpus/acquisition.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Originals retained locally; no model execution or publication performed")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError):
        print("Acquisition incomplete; raw remote content and paths omitted")
        raise SystemExit(1)
