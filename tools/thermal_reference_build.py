# SPDX-License-Identifier: MIT OR Apache-2.0
"""Build a separate pinned IDA reference; never link the FCST engine."""
import hashlib
import json
import tarfile
from pathlib import Path
from build_dependencies import source_tree
from profile_support import ROOT, cmake_tools, run


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(configuration, work):
    cmake, _ = cmake_tools()
    item = next(x for x in json.loads((ROOT / "ci/probe-sources.json").read_bytes())["sources"] if x["id"] == "sundials")
    dep = ROOT / ".local/thermal-reference-dependency"
    dep.mkdir(parents=True, exist_ok=True)
    source = source_tree(item, dep)
    with tarfile.open(ROOT / ".local/profile-downloads/sundials.tar.gz") as archive:
        for member in archive.getmembers():
            if member.isfile():
                target = source / Path(member.name).relative_to(Path(member.name).parts[0])
                if target.is_symlink() or not target.is_file() or hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(archive.extractfile(member).read()).digest():
                    raise ValueError("reference_source_changed")
    install = dep / "install"
    generator = ["-G", "Visual Studio 17 2022", "-A", "x64"]
    options = ["BUILD_IDA=ON", "BUILD_CVODE=OFF", "BUILD_ARKODE=OFF", "BUILD_CVODES=OFF", "BUILD_IDAS=OFF", "BUILD_KINSOL=OFF", "EXAMPLES_ENABLE_C=OFF", "EXAMPLES_ENABLE_CXX=OFF", "EXAMPLES_INSTALL=OFF", "BUILD_STATIC_LIBS=OFF", "BUILD_SHARED_LIBS=ON"]
    run([cmake, "-S", str(source), "-B", str(dep / "build"), *generator, "-DCMAKE_INSTALL_PREFIX="+str(install), "-DCMAKE_C_FLAGS=/fp:strict", *["-D"+v for v in options]], ROOT, work / "dependency-configure.log")
    run([cmake, "--build", str(dep / "build"), "--config", "Release", "--parallel", "2"], ROOT, work / "dependency-build.log")
    run([cmake, "--install", str(dep / "build"), "--config", "Release"], ROOT, work / "dependency-install.log")
    client = dep / configuration
    run([cmake, "-S", str(ROOT / "references/thermal"), "-B", str(client), *generator, "-DCMAKE_PREFIX_PATH="+str(install)], ROOT, work / "ida-configure.log")
    run([cmake, "--build", str(client), "--config", configuration, "--parallel", "2"], ROOT, work / "ida-build.log")
    run([cmake, "--install", str(client), "--config", configuration, "--prefix", str(work / "ida-install")], ROOT, work / "ida-install.log")
    executable = work / "ida-install/bin/fcst-ida-reference.exe"
    return executable, {"archive_sha256": item["sha256"], "revision": item["revision"], "license_sha256": item["license_sha256"], "runtime_sha256": {p.name: digest(p) for p in sorted(executable.parent.iterdir()) if p.is_file()}}
