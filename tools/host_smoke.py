# SPDX-License-Identifier: MIT OR Apache-2.0
"""Acquire an exact official FreeCAD bundle and supervise a synthetic host smoke."""
import json
import os
import platform
import subprocess
from pathlib import Path
from profile_support import ROOT, cmake_tools, run, verified_download, revision
import sys
sys.path.insert(0, str(ROOT / "python"))
from fcst_tools.profiles import assess_host, file_hash


def main():
    profile = json.loads((ROOT / "ci/host-profile.json").read_text(encoding="utf-8"))
    system = platform.system()
    asset = profile["platforms"][system]
    output = ROOT / ".local/host" / system
    output.mkdir(parents=True, exist_ok=True)
    report = output / "host-smoke.json"
    report.unlink(missing_ok=True)
    archive = verified_download("https://github.com/FreeCAD/FreeCAD/releases/download/" +
                                profile["version"] + "/" + asset["asset"],
                                ROOT / ".local/profile-downloads" / asset["asset"],
                                asset["bytes"], asset["sha256"])
    unpack = output / "bundle"
    unpack.mkdir(exist_ok=True)
    cmake, _ = cmake_tools()
    if system == "Windows":
        if not list(unpack.rglob("FreeCADCmd.exe")):
            run([cmake, "-E", "tar", "xf", str(archive)], unpack, output / "extract.log")
        commands = [p for p in unpack.rglob("FreeCADCmd.exe") if p.parent.name.lower() == "bin"]
        if len(commands) != 1:
            raise ValueError("Ambiguous host executable")
        command = [str(commands[0]), str(ROOT / "tools/host_smoke_payload.py")]
    else:
        archive.chmod(0o755)
        if not (unpack / "squashfs-root/AppRun").is_file():
            run([str(archive), "--appimage-extract"], unpack, output / "extract.log")
        command = [str(unpack / "squashfs-root/AppRun"), "--console", str(ROOT / "tools/host_smoke_payload.py")]
    env = dict(os.environ, FCST_HOST_SMOKE_OUTPUT=str(output), FCST_HOST_SMOKE_SOURCE=str(ROOT),
               QT_QPA_PLATFORM="offscreen", OMP_NUM_THREADS="1")
    for name in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(name, None)
    # Separate host preferences and generated document metadata from user state.
    command += ["--user-cfg", str(output / "user.cfg"), "--system-cfg", str(output / "system.cfg")]
    run(command, output, output / "host.log", env=env, timeout=180)
    data = json.loads(report.read_text(encoding="utf-8"))
    if data.get("status") != "passed" or data.get("python_abi") != profile["python_abi"]:
        raise ValueError("Host result did not match profile")
    data["asset_sha256"] = asset["sha256"]
    data["profile_sha256"] = file_hash(ROOT / "ci/host-profile.json")
    data["candidate"] = revision()
    if not assess_host(data, profile, system):
        raise ValueError("Incomplete host case coverage")
    report.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print("Pinned host document/geometry smoke: passed", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError):
        print("Pinned host smoke: failed; raw details retained locally")
        raise SystemExit(1)
