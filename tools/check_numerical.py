# SPDX-License-Identifier: MIT OR Apache-2.0
"""Build, install and assess the Q0 C++ checkpoint; retain every attempt locally."""
from __future__ import annotations
import argparse
import ctypes
import datetime
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
import uuid
import traceback
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from fcst_tools.gate import evaluate
from fcst_tools.numerical import (canonical, compare, compare_restart, compare_steady, digest, oracle,
                                  within, assess_attempt, steady_oracle, validate_policy, native_cache_root)
from fcst_contracts import read as read_contract
from profile_support import cmake_tools, run, revision, ProbeFailure
from build_dependencies import source_tree, OPTIONS


def hardware():
    class Memory(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(name, ctypes.c_ulonglong) for name in
            ("total", "available", "page", "pageavailable", "virtual", "virtualavailable", "extended")]
    mem = Memory()
    mem.length = ctypes.sizeof(mem)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
        raise ValueError("hardware_unavailable")
    return {"cpu": platform.processor(), "ram_bytes": mem.total, "os_build": platform.version(),
            "architecture": platform.machine(), "threads": 1}


def source_manifest():
    # Actual working bytes, including this implementation before its first commit.
    names = ["tools/check_numerical.py", "python/fcst_tools/numerical.py", "python/fcst_tools/gate.py",
             "prototypes/numerical/main.cpp", "prototypes/numerical/CMakeLists.txt", "ci/probe-sources.json",
             "tools/build_dependencies.py", "tools/profile_support.py", "ci/numerical-reference.json"]
    names += ["tests/fixtures/contracts/analytic-seed-native.json", "tests/fixtures/public/two-node-analytic.json",
              "python/fcst_contracts/__init__.py", "python/fcst_contracts/bundle.json", "ci/coverage.json",
              "spec/requirements.csv", "plans/automated-test-requirements.csv", "plans/requirement-traceability.csv",
              "spec/compatibility-profiles.csv", "plans/compatibility-test-plan.csv"]
    return {name: digest((ROOT / name).read_bytes()) for name in names if (ROOT / name).exists()}


def build(configuration, work):
    cmake, _ = cmake_tools()
    item = next(x for x in json.loads((ROOT / "ci/probe-sources.json").read_bytes())["sources"] if x["id"] == "sundials")
    dep = native_cache_root(ROOT, os.environ.get("LOCALAPPDATA", ROOT / ".local"))
    dep.mkdir(parents=True, exist_ok=True)
    source = source_tree(item, dep)
    # Reused extraction directories are mutable: verify actual build inputs,
    # not only the cached archive and its license file.
    with tarfile.open(ROOT / ".local/profile-downloads/sundials.tar.gz") as archive:
        for member in archive.getmembers():
            if member.isfile():
                name = Path(member.name).relative_to(Path(member.name).parts[0])
                target = source / name
                if target.is_symlink() or not target.is_file() or digest(target.read_bytes()) != digest(archive.extractfile(member).read()):
                    raise ValueError("backend_source_changed")
    install = dep / "install"
    generator = ["-G", "Visual Studio 17 2022", "-A", "x64"]
    run([cmake, "-S", str(source), "-B", str(dep / "build"), *generator,
         "-DCMAKE_INSTALL_PREFIX=" + str(install), "-DCMAKE_C_FLAGS=/fp:strict",
         *["-D"+v for v in OPTIONS["sundials"]]], ROOT, work / "dependency-configure.log")
    run([cmake, "--build", str(dep / "build"), "--config", "Release", "--parallel", "2"], ROOT, work / "dependency-build.log")
    run([cmake, "--install", str(dep / "build"), "--config", "Release"], ROOT, work / "dependency-install.log")
    # Build inputs are incremental; installed copies and evidence remain per attempt.
    prototype_build = dep / "prototype" / configuration
    run([cmake, "-S", str(ROOT / "prototypes/numerical"), "-B", str(prototype_build), *generator,
         "-DCMAKE_PREFIX_PATH=" + str(install)], ROOT, work / "configure.log")
    run([cmake, "--build", str(prototype_build), "--config", configuration, "--parallel", "2"], ROOT, work / "build.log")
    run([cmake, "--install", str(prototype_build), "--config", configuration, "--prefix", str(work / "install")], ROOT, work / "install.log")
    # This copy is outside both build trees, with only installed runtime files.
    destination = work / "engine-only"
    shutil.copytree(work / "install/bin", destination)
    return destination / "fcst-numerical.exe", item


def payload(case, criteria, start=0, end=None, initial=None, heater=True):
    return " ".join(str(x) for x in [*case["parameters"], start, end or case["end_s"], case["sample_s"],
        criteria["integration"]["rtol"], criteria["integration"]["atol"], *(initial or case["initial"]), int(heater)])


def execute(executable, args, text=""):
    # No Python, FreeCAD, vendor runtime, compiler or dependency directory on PATH.
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    env.update(PATH=str(executable.parent), OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    process = subprocess.run([str(executable), *args], input=text, text=True, capture_output=True,
                             cwd=executable.parent, env=env, timeout=90)
    result = json.loads(process.stdout)
    if not isinstance(result, dict) or (process.returncode == 0 and result.get("status") == "failed"):
        raise ValueError("invalid_native_result")
    return process.returncode, result


def coverage():
    import csv
    def rows(name):
        with (ROOT / name).open(newline="", encoding="utf-8") as stream:
            return list(csv.DictReader(stream))
    requirements = rows("spec/requirements.csv") + rows("plans/automated-test-requirements.csv")
    trace = rows("plans/requirement-traceability.csv")
    profiles = rows("spec/compatibility-profiles.csv")
    planned = rows("plans/compatibility-test-plan.csv")
    ids = [x["id"] for x in requirements]
    return (len(ids) == len(set(ids)) and len(trace) == len(ids) and
            {x["requirement_id"] for x in trace} == set(ids) and
            len(planned) == len(profiles) and {x["profile_id"] for x in planned} == {x["profile_id"] for x in profiles} and
            all(x["primary_work_package"] and x["evidence_contract"] and x["automated_suites"] for x in trace))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", choices=["Debug", "Release"], default="Release")
    parser.add_argument("--report", type=Path, default=ROOT / ".local/numerical-summary.json")
    parser.add_argument("--require-reference", action="store_true")
    parser.add_argument("--replay", type=Path)
    args = parser.parse_args()
    if args.replay:
        replay = assess_attempt(args.replay)
        print(json.dumps(replay))
        return 0 if replay["status"] == "passed" else 1
    if platform.system() != "Windows":
        parser.error("The Q0 target is Windows x64")
    attempt = ROOT / ".local/numerical" / (datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex)
    attempt.mkdir(parents=True)
    # Freeze exact bytes before configuring a compiler or executing an oracle.
    criteria_bytes = (ROOT / "ci/numerical-criteria-v1.json").read_bytes()
    fixture_bytes = (ROOT / "tests/fixtures/numerical/checkpoint-v1.json").read_bytes()
    (attempt / "criteria.json").write_bytes(criteria_bytes)
    (attempt / "fixture.json").write_bytes(fixture_bytes)
    criteria, fixture = json.loads(criteria_bytes), json.loads(fixture_bytes)
    validate_policy(criteria, fixture)
    provenance = {"candidate": revision(), "source_artifacts": source_manifest(), "hardware": hardware(),
                  "configuration": args.configuration, "criteria_sha256": digest(criteria_bytes), "fixture_sha256": digest(fixture_bytes),
                  "execution_mode": "fcst_native", "scope": "q0_prototype", "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  "driver": "tools/check_numerical.py", "ci": {k: os.environ.get(k, "local") for k in
                  ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB", "GITHUB_WORKFLOW", "GITHUB_SHA")}}
    provenance["require_reference"] = args.require_reference
    provenance["python"] = platform.python_version()
    (attempt / "started.json").write_bytes(canonical(provenance))
    records, observations = [], {}
    def record(name, okay, **metrics):
        records.append({"id": name, "status": "passed" if okay else "failed", **metrics})
        print(name + ": " + records[-1]["status"], flush=True)
    state = "interrupted"
    try:
        record("coverage", coverage())
        executable, dependency = build(args.configuration, attempt)
        code, info = execute(executable, ["info"])
        provenance.update(build=info, backend_source=dependency,
            installed_artifacts={p.name: digest(p.read_bytes()) for p in sorted(executable.parent.iterdir()) if p.is_file()})
        provenance["reference_match"] = (ROOT / "ci/numerical-reference.json").exists() and json.loads(
            (ROOT / "ci/numerical-reference.json").read_bytes()) == {"hardware": provenance["hardware"], "build": info, "configuration": args.configuration}
        record("engine-only-install", code == 0 and info["scope"] == "q0_prototype" and info["sundials"] == "7.3.0")
        results, references = {}, {}
        for case_id, case in fixture["cases"].items():
            if case_id == "analytic-seed":
                seed = json.loads((ROOT / case["source"]).read_bytes())
                # Project the WP-03 validated native snapshot into this bounded
                # experiment's typed inputs; Python does preparation, C++ solves.
                model = read_contract("model", json.loads((ROOT / "tests/fixtures/contracts/analytic-seed-native.json").read_bytes()))
                entities = model["entities"]
                capacitive = next(x for x in entities if x["kind"] == "node" and x["classification"] == "capacitive")
                boundary = next(x for x in entities if x["kind"] == "node" and x["classification"] == "prescribed")
                conductor = next(x for x in entities if x["kind"] == "conductor")
                load = next(x for x in entities if x["kind"] == "load")
                expected = [capacitive["capacity"]["value"], conductor["conductance"]["value"], boundary["temperature"]["value"], load["power"]["value"], capacitive["temperature"]["value"]]
                if expected != [seed[k] for k in ("capacity_J_per_K", "conductance_W_per_K", "boundary_K", "power_W", "initial_K")] or expected != [case["parameters"][i] for i in (0,4,9,10)] + [case["initial"][0]]:
                    raise ValueError("independent_seed_changed")
                steady = seed["boundary_K"]+seed["power_W"]/seed["conductance_W_per_K"]
                def analytic(t):
                    value = steady+(seed["initial_K"]-steady)*math.exp(-t*seed["conductance_W_per_K"]/seed["capacity_J_per_K"])
                    return {"time_s": t, "state": [value,seed["boundary_K"],seed["capacity_J_per_K"]*(value-seed["initial_K"])],
                            "algebraic_K":seed["boundary_K"],"heater":True}
                references[case_id] = {"samples": [analytic(i*case["sample_s"]) for i in range(round(case["end_s"]/case["sample_s"])+1)], "events_s":[]}
            else:
                references[case_id] = oracle(case, criteria["oracle"]["refined_step_s"])
            for backend in ("dense", "band", "adams"):
                key = case_id + "-" + backend
                code, result = execute(executable, ["integrate", backend], payload(case, criteria))
                observations[key] = result; results[key] = result
                errors, metrics = compare(case, result, references[case_id], criteria)
                record(key, code == 0 and not errors, problems=errors, **metrics,
                    seconds=result["seconds"], peak_memory_bytes=result["peak_memory_bytes"],
                    steps=result["steps"], rhs_evaluations=result["rhs_evaluations"])
        nonlinear = fixture["cases"]["stiff-nonlinear-heater"]
        equilibrium = steady_oracle(nonlinear["parameters"])
        for backend in ("dense", "band"):
            code, result = execute(executable, ["steady", backend], payload(nonlinear, criteria))
            record("steady-"+backend, code == 0 and compare_steady(nonlinear["parameters"], result, equilibrium, criteria))
            observations["steady-"+backend] = result
        coarse = oracle(nonlinear, criteria["oracle"]["step_s"])
        fine = references["stiff-nonlinear-heater"]
        refinement = max(abs(a-b) for x, y in zip(coarse["samples"], fine["samples"]) for a, b in zip(x["state"][:2], y["state"][:2]))
        record("oracle-refinement", refinement <= criteria["oracle"]["refinement_atol_K"] and len(coarse["events_s"]) == len(fine["events_s"]) and len(fine["events_s"]) > 2,
               max_error_K=refinement)
        backend_error = max(abs(a-b) for name in fixture["cases"] for backend in ("band", "adams") for x, y in zip(results[name+"-dense"]["samples"], results[name+"-"+backend]["samples"]) for a, b in zip(x["state"], y["state"]))
        record("backend-equivalence", backend_error <= criteria["temperature_K"]["atol"], max_error=backend_error)
        for backend in ("dense", "band", "adams"):
            # Stop the process at a sample boundary; resume in a fresh engine-only process.
            code, partial = execute(executable, ["cancel", backend], payload(nonlinear, criteria, end=10))
            last = partial["samples"][-1]
            code2, resumed = execute(executable, ["integrate", backend], payload(nonlinear, criteria,
                start=10, initial=last["state"], heater=last["heater"]))
            expected = results["stiff-nonlinear-heater-"+backend]
            errors, metrics = compare_restart(partial, resumed, expected, 10, criteria)
            okay = code == code2 == 0 and not errors
            observations["restart-"+backend] = {"partial": partial, "resumed": resumed}
            record("restart-"+backend, okay, problems=errors, **metrics)
        for key, text, expected_code in [("invalid-input", "nan", "invalid_input"),
                ("inconsistent-initialization", payload(nonlinear, criteria, initial=[302,300,0]), "inconsistent_initial_state"),
                ("property-domain", payload(nonlinear, criteria, initial=[-1,300,0]), "property_domain")]:
            code, bad = execute(executable, ["integrate", "band"], text)
            observations[key] = bad
            record(key, code == 2 and bad == {"status":"failed", "code":expected_code})
        for backend, nodes in [("dense", 128), ("band", 128), *[("band", n) for n in criteria["performance"]["scale_nodes"]]]:
            key = f"scale-{backend}-{nodes}"
            reps = []
            for _ in range(criteria["performance"]["replicates"]):
                code, result = execute(executable, ["scale", backend, str(nodes)])
                result["exit_code"] = code; reps.append(result)
            observations[key] = reps
            okay = all(r["exit_code"] == 0 and r["nodes"] == nodes and r["directed_links"] == 10*nodes-30 and
                within(r["max_error"], 0, criteria["scale_error"]) and within(r["max_residual"], 0, criteria["scale_residual"]) and
                0 <= r["seconds"] <= criteria["performance"]["max_seconds"] and 0 < r["peak_memory_bytes"] <= criteria["performance"]["max_memory_bytes"] for r in reps)
            record(key, okay, median_seconds=statistics.median(r["seconds"] for r in reps),
                range_seconds=[min(r["seconds"] for r in reps), max(r["seconds"] for r in reps)], peak_memory_bytes=max(r["peak_memory_bytes"] for r in reps))
        observations["independent_oracles"] = references
        if provenance["source_artifacts"] != source_manifest():
            raise ValueError("source_changed_during_assessment")
        state = "completed"
    except (Exception, KeyboardInterrupt) as failure:
        # Bounded public diagnostics; full compiler/process logs stay local.
        (attempt / "exception.log").write_text(traceback.format_exc(), encoding="utf-8")
        allowed = {"backend_source_changed", "independent_seed_changed", "source_changed_during_assessment"}
        reason = str(failure) if isinstance(failure, ValueError) and str(failure) in allowed else "required_prerequisite_or_execution_unavailable"
        record("execution", False, reason=reason,
               stage=failure.stage if isinstance(failure, ProbeFailure) else "numerical_execution")
    finally:
        gate = evaluate(criteria["required_cases"], records)
        if args.require_reference and not provenance.get("reference_match"):
            gate["status"] = "failed"; gate["problems"].append("reference_profile_mismatch")
        assessment = {"cases": records, "gate": gate}
        (attempt / "observations.json").write_bytes(canonical(observations))
        (attempt / "assessment.json").write_bytes(canonical(assessment))
        provenance.update(state=state, artifacts={name:digest((attempt/name).read_bytes()) for name in
            ("criteria.json", "fixture.json", "observations.json", "assessment.json")}, ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        provenance["local_artifacts"] = {p.name:digest(p.read_bytes()) for p in sorted(attempt.glob("*.log"))}
        provenance["local_artifacts"]["started.json"] = digest((attempt/"started.json").read_bytes())
        manifest_bytes = canonical(provenance)
        (attempt / "manifest.json").write_bytes(manifest_bytes)
        (attempt / "seal.json").write_bytes(canonical({"manifest_sha256":digest(manifest_bytes)}))
        report = {"scope":"Q0 numerical prototype; no production or compatibility qualification", "provenance":provenance,
                  "manifest_sha256":digest(manifest_bytes), **assessment}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes(canonical(report)+b"\n")
        print(json.dumps(gate))
    return 0 if gate["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError):
        print('{"status":"failed","reason":"numerical_prerequisite_or_evidence_unavailable"}')
        raise SystemExit(1)
