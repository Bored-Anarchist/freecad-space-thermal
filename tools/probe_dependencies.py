# SPDX-License-Identifier: MIT OR Apache-2.0
"""Discover candidate CMake packages without downloading or adopting them."""
import argparse
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/dependency-probes.json")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "ci/dependencies.json").read_text())
    work = ROOT / ".local/probes"
    records = []
    for candidate in manifest["candidates"]:
        package = candidate["cmake_package"]
        source = work / package
        source.mkdir(parents=True, exist_ok=True)
        (source / "CMakeLists.txt").write_text(
            f'cmake_minimum_required(VERSION 3.22)\nproject(Probe LANGUAGES C CXX)\nfind_package({package} REQUIRED)\n')
        start = time.monotonic()
        try:
            process = subprocess.run([args.cmake, "-S", str(source), "-B", str(source / "build")],
                                     capture_output=True, timeout=180)
            (source / "raw.log").write_bytes(process.stdout + process.stderr)
            status = "discovered_not_qualified" if process.returncode == 0 else "unavailable"
        except (OSError, subprocess.SubprocessError):
            status = "blocked"
        records.append({"name": candidate["name"], "status": status,
                        "probe_seconds": round(time.monotonic() - start, 3), "adopted": False})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"scope": "Discovery only; package build/install and numerical probes require selected versions at Q0", "candidates": records}, indent=2) + "\n")
    print(json.dumps(records))


if __name__ == "__main__":
    main()
