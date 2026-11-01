# SPDX-License-Identifier: MIT OR Apache-2.0
"""Build/install pinned candidates and compile independent installed consumers.

These are packaging probes. They do not select a production numerical backend.
Raw configure/compiler logs and third-party files always remain local.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import tarfile
import time
from pathlib import Path
from profile_support import ROOT, cmake_tools, run, verified_download, revision, ProbeFailure
import sys
sys.path.insert(0, str(ROOT / "python"))
from fcst_tools.profiles import assess_dependencies

OPTIONS = {
    "sundials": ["BUILD_ARKODE=OFF", "BUILD_CVODES=OFF", "BUILD_IDAS=OFF", "BUILD_IDA=OFF",
                 "BUILD_KINSOL=OFF", "EXAMPLES_ENABLE_C=OFF", "EXAMPLES_ENABLE_CXX=OFF",
                 "EXAMPLES_INSTALL=OFF", "BUILD_STATIC_LIBS=OFF", "BUILD_SHARED_LIBS=ON"],
    "hdf5": ["BUILD_TESTING=OFF", "HDF5_BUILD_TOOLS=OFF", "HDF5_BUILD_EXAMPLES=OFF",
             "HDF5_BUILD_HL_LIB=OFF", "HDF5_ENABLE_Z_LIB_SUPPORT=OFF", "HDF5_ENABLE_SZIP_SUPPORT=OFF",
             "HDF5_BUILD_CPP_LIB=OFF", "HDF5_BUILD_FORTRAN=OFF", "BUILD_SHARED_LIBS=ON"],
    "embree": ["EMBREE_TUTORIALS=OFF", "EMBREE_ISPC_SUPPORT=OFF", "EMBREE_TASKING_SYSTEM=INTERNAL",
               "EMBREE_MAX_ISA=SSE2", "EMBREE_STATIC_LIB=OFF", "EMBREE_TESTING_INTENSITY=0"],
    "occt": ["BUILD_MODULE_ModelingData=ON", "BUILD_MODULE_ModelingAlgorithms=OFF",
             "BUILD_MODULE_Visualization=OFF", "BUILD_MODULE_ApplicationFramework=OFF",
             "BUILD_MODULE_DataExchange=OFF", "BUILD_MODULE_DETools=OFF", "BUILD_MODULE_Draw=OFF",
             "USE_TK=OFF", "USE_TCL=OFF", "USE_FREETYPE=OFF", "USE_TBB=OFF",
             "USE_VTK=OFF", "INSTALL_DIR_LAYOUT=Unix", "BUILD_LIBRARY_TYPE=Shared"],
}

CLIENTS = {
    "sundials": ("find_package(SUNDIALS REQUIRED COMPONENTS cvode nvecserial)",
                 "SUNDIALS::cvode SUNDIALS::nvecserial", """#include <cvode/cvode.h>
#include <nvector/nvector_serial.h>
int main(){ SUNContext c=nullptr; if(SUNContext_Create(SUN_COMM_NULL,&c)) return 1;
auto v=N_VNew_Serial(2,c); if(!v) return 2; N_VConst(3,v);
auto s=CVodeCreate(CV_BDF,c); if(!s || NV_Ith_S(v,1)!=3) return 3;
CVodeFree(&s); N_VDestroy(v); SUNContext_Free(&c); return 0; }
"""),
    "hdf5": ("find_package(HDF5 CONFIG REQUIRED)", "hdf5-shared", """#include <hdf5.h>
int main(){ auto f=H5Fcreate("synthetic.h5",H5F_ACC_TRUNC,H5P_DEFAULT,H5P_DEFAULT);
if(f<0) return 1; hsize_t n=2; double x[2]={1.25,2.5},y[2]={0,0};
auto s=H5Screate_simple(1,&n,nullptr);
auto d=H5Dcreate2(f,"values",H5T_NATIVE_DOUBLE,s,H5P_DEFAULT,H5P_DEFAULT,H5P_DEFAULT);
if(d<0 || H5Dwrite(d,H5T_NATIVE_DOUBLE,H5S_ALL,H5S_ALL,H5P_DEFAULT,x)<0) return 2;
H5Dclose(d); H5Sclose(s); H5Fclose(f);
f=H5Fopen("synthetic.h5",H5F_ACC_RDONLY,H5P_DEFAULT); d=H5Dopen2(f,"values",H5P_DEFAULT);
if(d<0 || H5Dread(d,H5T_NATIVE_DOUBLE,H5S_ALL,H5S_ALL,H5P_DEFAULT,y)<0) return 3;
H5Dclose(d); H5Fclose(f); return y[0]==1.25 && y[1]==2.5 ? 0 : 4; }
"""),
    "embree": ("find_package(embree 4 REQUIRED)", "embree", """#include <embree4/rtcore.h>
#include <cmath>
#include <limits>
int main(){ auto d=rtcNewDevice("threads=1"); if(!d) return 1;
auto s=rtcNewScene(d); auto g=rtcNewGeometry(d,RTC_GEOMETRY_TYPE_TRIANGLE);
auto v=(float*)rtcSetNewGeometryBuffer(g,RTC_BUFFER_TYPE_VERTEX,0,RTC_FORMAT_FLOAT3,12,3);
float p[9]={0,0,0,1,0,0,0,1,0}; for(int i=0;i<9;++i) v[i]=p[i];
auto ix=(unsigned*)rtcSetNewGeometryBuffer(g,RTC_BUFFER_TYPE_INDEX,0,RTC_FORMAT_UINT3,12,1);
ix[0]=0;ix[1]=1;ix[2]=2; rtcCommitGeometry(g); rtcAttachGeometry(s,g); rtcReleaseGeometry(g);rtcCommitScene(s);
RTCRayHit r={}; r.ray.org_x=.25f;r.ray.org_y=.25f;r.ray.org_z=1;
r.ray.dir_z=-1;r.ray.tfar=10;r.ray.mask=~0u;r.hit.geomID=RTC_INVALID_GEOMETRY_ID;
RTCIntersectArguments a;rtcInitIntersectArguments(&a);rtcIntersect1(s,&r,&a);
int ok=r.hit.geomID!=RTC_INVALID_GEOMETRY_ID && std::abs(r.ray.tfar-1)<=8*std::numeric_limits<float>::epsilon()
 && rtcGetDeviceError(d)==RTC_ERROR_NONE;
rtcReleaseScene(s);rtcReleaseDevice(d);return ok?0:2; }
"""),
    "occt": ("find_package(OpenCASCADE REQUIRED)\ninclude_directories(${OpenCASCADE_INCLUDE_DIR})\nlink_directories(${OpenCASCADE_LIBRARY_DIR})",
             "TKernel TKMath TKG3d", """#include <Geom_CartesianPoint.hxx>
#include <gp_Pnt.hxx>
int main(){ Handle(Geom_CartesianPoint) p=new Geom_CartesianPoint(1,2,3);
return p->Pnt().Distance(gp_Pnt(1,2,6))==3 ? 0:1; }
"""),
}


def source_tree(item, work):
    archive = verified_download(item["url"], ROOT / ".local/profile-downloads" / (item["id"] + ".tar.gz"),
                                item["bytes"], item["sha256"])
    dest = work / "source"
    dest.mkdir(exist_ok=True)
    source = dest / (item["repository"].split("/")[-1] + "-" + item["revision"])
    if not source.is_dir():
        with tarfile.open(archive) as stream:
            # Build trees need regular source files, not documentation symlinks.
            members = []
            for member in stream.getmembers():
                target = dest / member.name
                if not target.resolve().is_relative_to(dest.resolve()):
                    raise ValueError("Archive path escapes extraction root")
                if member.isfile() or member.isdir():
                    members.append(member)
                elif not member.issym() and not member.islnk():
                    raise ValueError("Special source archive member")
            stream.extractall(dest, members=members)
    if hashlib.sha256((source / item["license_file"]).read_bytes()).hexdigest() != item["license_sha256"]:
        raise ValueError("License differs from locked source")
    return source


def cmake_probe(item, source, work, cmake, ctest, jobs, *, compiler_jobs=2, timings=None, resources=None):
    name = item["id"]
    build, install = work / "build", work / "install"
    def measured(command, directory, log, env=None):
        start = time.monotonic()
        usage = {} if resources is not None else None
        run(command, directory, log, env=env, resources=usage)
        if timings is not None:
            timings[Path(log).stem] = round(time.monotonic()-start, 3)
        if resources is not None:
            resources[Path(log).stem] = usage
    generator = ["-G", "Visual Studio 17 2022", "-A", "x64"] if os.name == "nt" else ["-G", "Ninja"]
    common = ["-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_INSTALL_PREFIX=" + str(install),
              "-DCMAKE_C_FLAGS=-ffp-contract=off", "-DCMAKE_CXX_FLAGS=-ffp-contract=off"] if os.name != "nt" else [
              "-DCMAKE_INSTALL_PREFIX=" + str(install),
              f"-DCMAKE_C_FLAGS=/MP{compiler_jobs}", f"-DCMAKE_CXX_FLAGS=/MP{compiler_jobs}"]
    measured([cmake, "-S", str(source), "-B", str(build), *generator, *common,
         *["-D" + option for option in OPTIONS[name]]], ROOT, work / "configure.log")
    measured([cmake, "--build", str(build), "--config", "Release", "--parallel", str(jobs)], ROOT, work / "build.log")
    measured([cmake, "--install", str(build), "--config", "Release"], ROOT, work / "install.log")
    client = work / "consumer"
    client.mkdir(exist_ok=True)
    find, libraries, code = CLIENTS[name]
    (client / "main.cpp").write_text(code, encoding="utf-8")
    (client / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.22)\nproject(InstalledProbe LANGUAGES C CXX)\n" + find +
        "\nadd_executable(probe main.cpp)\ntarget_link_libraries(probe PRIVATE " + libraries +
        ")\nenable_testing()\nadd_test(NAME installed_consumer COMMAND probe)\n", encoding="utf-8")
    measured([cmake, "-S", str(client), "-B", str(client / "build"), *generator,
         "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_PREFIX_PATH=" + str(install)], ROOT, work / "consumer-configure.log")
    measured([cmake, "--build", str(client / "build"), "--config", "Release"], ROOT, work / "consumer-build.log")
    env = dict(os.environ, OMP_NUM_THREADS="1")
    if os.name == "nt":
        dll_dirs = sorted({str(p.parent) for p in install.rglob("*.dll")})
        env["PATH"] = os.pathsep.join(dll_dirs) + os.pathsep + env.get("PATH", "")
    else:
        env["LD_LIBRARY_PATH"] = os.pathsep.join(sorted({str(p.parent) for p in install.rglob("*.so*")}))
    measured([ctest, "--test-dir", str(client / "build"), "-C", "Release", "--output-on-failure",
         "--no-tests=error"], ROOT, work / "consumer-run.log", env=env)
    return install


def petsc_probe(source, work, jobs):
    install = work / "install"
    # Linux system BLAS/LAPACK are probe inputs, never an adopted production lock.
    run([__import__("sys").executable, str(source / "configure"), "--prefix=" + str(install),
         "PETSC_ARCH=arch-fcst-probe", "--with-debugging=0", "--with-mpi=0", "--with-fc=0",
         "--with-cxx=0", "--with-x=0", "--with-shared-libraries=1", "--with-ssl=0",
         "--with-blaslapack-lib=[/usr/lib/x86_64-linux-gnu/liblapack.so.3,/usr/lib/x86_64-linux-gnu/libblas.so.3]"], source, work / "configure.log")
    run(["make", "PETSC_DIR=" + str(source), "PETSC_ARCH=arch-fcst-probe", "-j" + str(jobs), "all"], source, work / "build.log")
    run(["make", "PETSC_DIR=" + str(source), "PETSC_ARCH=arch-fcst-probe", "install"], source, work / "install.log")
    env = dict(os.environ, PETSC_DIR=str(install), PETSC_ARCH="", OMP_NUM_THREADS="1")
    run(["make", "PETSC_DIR=" + str(install), "PETSC_ARCH=", "check"], source, work / "consumer-run.log", env=env)
    return install


def prepare_blas(work):
    """Install distribution-signed probe inputs only on an ephemeral Linux runner."""
    run(["sudo", "apt-get", "update", "-qq"], ROOT, work / "system-update.log", timeout=600)
    run(["sudo", "apt-get", "install", "-y", "--no-install-recommends", "libblas-dev", "liblapack-dev"],
        ROOT, work / "system-install.log", timeout=600)


def toolchain(work):
    values = {"system": platform.system(), "architecture": platform.machine(), "threads": 1}
    if os.cpu_count() is not None:
        values["logical_cpus"] = os.cpu_count()
    for name in ("ImageOS", "ImageVersion"):
        value = os.environ.get(name, "")
        if value and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value):
            values[name] = value
    for path in sorted((work / "build/CMakeFiles").glob("*/CMake*Compiler.cmake")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for language, key, value in re.findall(r'set\(CMAKE_(C|CXX)_COMPILER_(ID|VERSION) "([A-Za-z0-9_.+-]+)"\)', text):
            values[language.lower() + "_" + key.lower()] = value
    if (work / "install/lib/libpetsc.so").exists():
        process = subprocess.run(["cc", "-dumpfullversion"], capture_output=True, text=True, timeout=10)
        if re.fullmatch(r"[0-9.]+", process.stdout.strip()):
            values["c_version"] = process.stdout.strip()
        values["system_blas_lapack"] = []
        for name in ("liblapack.so.3", "libblas.so.3"):
            path = Path("/usr/lib/x86_64-linux-gnu") / name
            if path.is_file():
                values["system_blas_lapack"].append({"soname": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=list(OPTIONS) + ["petsc"])
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--compiler-jobs", type=int, default=2,
                        help="Maximum MSVC compiler processes per MSBuild project")
    parser.add_argument("--prepare-system", action="store_true", help="Install signed Linux BLAS/LAPACK probe prerequisites using sudo apt-get")
    args = parser.parse_args()
    if platform.system() != "Windows":
        parser.error("macOS and Linux package probes are uncommitted stretch goals outside the work packages")
    if not 1 <= args.jobs <= 16:
        parser.error("jobs must be between 1 and 16")
    if not 1 <= args.compiler_jobs <= 4:
        parser.error("compiler-jobs must be between 1 and 4")
    lock = ROOT / "ci/probe-sources.json"
    items = json.loads(lock.read_text(encoding="utf-8"))["sources"]
    cmake, ctest = cmake_tools()
    output = ROOT / ".local/dependency-builds" / platform.system()
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for item in items:
        if args.candidate and item["id"] != args.candidate:
            continue
        work = output / item["id"]
        work.mkdir(exist_ok=True)
        record = {"id": item["id"], "version": item["version"], "source_sha256": item["sha256"],
                  "license_sha256": item["license_sha256"], "adopted": False,
                  "generator": "visual-studio-2022", "build_jobs": args.jobs,
                  "compiler_jobs": args.compiler_jobs, "stage_seconds": {}, "stage_resources": {}}
        start = time.monotonic()
        if item["id"] == "petsc" and os.name == "nt":
            record.update(status="unsupported", reason_code="petsc_native_msvc_unsupported",
                          reason="Native MSVC is not a supported PETSc build profile; Linux probe is required")
        else:
            try:
                if item["id"] == "petsc" and args.prepare_system:
                    prepare_blas(work)
                source = source_tree(item, work)
                install = petsc_probe(source, work, args.jobs) if item["id"] == "petsc" else cmake_probe(item, source, work, cmake, ctest, args.jobs, compiler_jobs=args.compiler_jobs, timings=record["stage_seconds"], resources=record["stage_resources"])
                record.update(status="passed", stages=["source_hash", "license_hash", "configure", "build", "install", "installed_consumer"],
                              installed_bytes=sum(p.stat().st_size for p in install.rglob("*") if p.is_file()),
                              toolchain=toolchain(work), build_options=OPTIONS.get(item["id"], ["serial", "shared", "system_blas_lapack"]))
            except ProbeFailure as failure:
                record.update(status="failed", failing_stage=failure.stage, reason=failure.reason,
                              sanitized_diagnostics=failure.diagnostics)
            except (ValueError, OSError, tarfile.TarError, subprocess.SubprocessError):
                record.update(status="failed", reason="probe_failed_raw_logs_local")
        record["seconds"] = round(time.monotonic() - start, 3)
        records.append(record)
        (work / "result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(item["id"] + ": " + record["status"], flush=True)
        if record["status"] == "failed":
            print(json.dumps({"id": item["id"], "stage": record.get("failing_stage", "source_preparation"),
                              "reason": record["reason"]}), flush=True)
    report = {"scope": "Candidate packaging only; no numerical qualification or production adoption", "platform": platform.system(),
              "candidate": revision(), "source_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(), "candidates": records}
    name = "dependency-builds" + ("-" + args.candidate if args.candidate else "") + ".json"
    (output / name).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if assess_dependencies(report, items, platform.system(), args.candidate) else 1


if __name__ == "__main__":
    raise SystemExit(main())
