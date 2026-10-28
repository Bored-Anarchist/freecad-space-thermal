# SPDX-License-Identifier: MIT OR Apache-2.0
"""Verify official host first, then supervise the separate FEM payload."""
import json
import os
from pathlib import Path
import shutil
import sys
from hashlib import sha256
import host_smoke
from profile_support import ROOT, run, revision


def main():
    host_smoke.main()
    folder = ROOT / ".local/fem-probe"
    folder.mkdir(exist_ok=True)
    (folder/"fem-probe.json").unlink(missing_ok=True)
    # Unique attempt directories preserve failures and avoid stale documents/databases.
    import uuid
    attempt = folder / uuid.uuid4().hex
    attempt.mkdir()
    commands=[p for p in (ROOT / ".local/host/Windows/bundle").rglob("FreeCADCmd.exe") if p.parent.name.lower()=="bin"]
    if len(commands)!=1: raise ValueError("Ambiguous host executable")
    host=commands[0]
    manifest=json.loads((ROOT/"ci/fem-reuse.json").read_bytes())
    for group in manifest["groups"]:
        for entry in group["files"]:
            raw=(host.parent.parent/entry["asset_path"]).read_bytes()
            if sha256(raw).hexdigest()!=entry["sha256"] or sha256(b"".join(raw.splitlines(keepends=True)[:30])).hexdigest()!=entry["notice_sha256"]:
                raise ValueError("Host source or license identity mismatch")
    env = dict(os.environ, FCST_HOST_SMOKE_SOURCE=str(ROOT), FCST_FEM_OUTPUT=str(attempt), QT_QPA_PLATFORM="offscreen", OMP_NUM_THREADS="1")
    for name in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(name, None)
    run([str(host), str(ROOT / "tools/fem_probe_payload.py"), "--user-cfg", str(attempt/"user.cfg"), "--system-cfg", str(attempt/"system.cfg")], attempt, attempt/"host.log", env=env, timeout=180)
    report = json.loads((attempt / "fem-probe.json").read_bytes())
    assert report["status"] == "passed"
    profile = json.loads((ROOT / "ci/host-profile.json").read_bytes())
    report.update(candidate=revision(), asset_sha256=profile["platforms"]["Windows"]["sha256"],
        host_profile_sha256=sha256((ROOT / "ci/host-profile.json").read_bytes()).hexdigest(),
        payload_sha256=sha256((ROOT / "tools/fem_probe_payload.py").read_bytes()).hexdigest(),
        manifest_sha256=sha256((ROOT / "ci/fem-reuse.json").read_bytes()).hexdigest())
    sys.path.insert(0,str(ROOT/"python"))
    from fcst_tools.foundation import input_hashes
    report["input_sha256"]=input_hashes(ROOT)
    (folder / "fem-probe.json").write_text(json.dumps(report, indent=2)+"\n")
    print("Pinned FEM foundation probes: passed")


if __name__ == "__main__":
    try: main()
    except Exception:
        print("Pinned FEM foundation probes: failed; diagnostics retained locally")
        raise SystemExit(1)
