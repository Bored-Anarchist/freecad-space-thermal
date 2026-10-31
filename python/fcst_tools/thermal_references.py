# SPDX-License-Identifier: MIT OR Apache-2.0
"""Fail-closed comparison and evidence contract for independent WP-11 solvers.

Standard library only: native gates and security checks do not import references.
"""
import hashlib
import json
import math
from pathlib import Path

FIELDS = ("temperature", "links", "boundary_power", "storage_change", "external_energy", "boundary_energy", "energy_defect", "duty")
TIMES = {"cooling": [0, .5, 1, 2, 4], "closed": [0, .1, .5, 1, 2], "dae": [0, .5, 1, 2, 4], "enthalpy": [0, .5, 1, 2, 5, 10], "stiff": [0, 1e-6, 1e-4, .01, .1, .5, 1], "heater": [0, .5, 1, 2, 3, 4, 5], "schedule": [0, .5, 1, 1.5, 2, 3, 4], "nonlinear": [0, .5, 1, 2, 3, 4, 5]}
STEADY = {"cooling": [300, 300], "dae": [300, 300, 300], "stiff": [290, 290, 290], "nonlinear": [320, 310, 300]}


def require(value):
    if not value: raise ValueError("thermal_reference_evidence_invalid")


def number(value):
    require(type(value) in (int, float) and math.isfinite(value))
    return value


def hash_value(value):
    return isinstance(value, str) and len(value) == 64 and not set(value)-set("0123456789abcdef")


def input_hashes(root):
    names = ["CMakeLists.txt", "CMakePresets.json", "ci/thermal-reference-v1.json", "ci/probe-sources.json", "ci/requirements.lock", "ci/pycanha-reference.lock", "ci/pycanha-reference-runtime.json", "tools/check_thermal_references.py", "tools/thermal_reference_build.py", "tools/provision_thermal_references.py", "tools/profile_support.py", "tools/build_dependencies.py", "python/fcst_tools/thermal_references.py"]
    for directory in ("engine/include/fcst", "engine/src", "engine/tests", "tests/fixtures/thermal", "references/thermal"):
        names += [p.relative_to(root).as_posix() for p in (root/directory).iterdir() if p.is_file() and p.suffix in (".cpp", ".hpp", ".in", ".json", ".py", ".txt")]
    return {n: hashlib.sha256((root/n).read_bytes()).hexdigest() for n in sorted(set(names))}


def validate_run(result, backend, case, level, policy, candidate):
    require(isinstance(result, dict) and result.get("status") == "passed" and result.get("case") == case)
    if backend == "native":
        require(level == "native" and result.get("execution_mode") == "fcst_native" and result.get("source_revision") == candidate and hash_value(result.get("preparation_hash")))
        require(result.get("requested_times") == TIMES[case] and result.get("temperature_atol_K") == policy["native_temperature_atol_K"].get(case,policy["native_temperature_atol_K"]["default"]))
    else:
        require(result.get("execution_mode") == "reference_external" and result.get("backend") == backend and result.get("level") == level)
        require(result.get("version") == (policy["pycanha"]["version"] if backend == "pycanha_core" else policy["required_backends"][backend]))
        require(result.get("step_s") == policy["pycanha"][level+"_step_s"] if backend == "pycanha_core" else result.get("tolerance") == policy["levels"][level])
    samples = result.get("samples")
    require(isinstance(samples, list) and len(TIMES[case]) <= len(samples) < 10000)
    previous = -1
    for s in samples:
        require(isinstance(s, dict) and number(s["time"]) > previous); previous = s["time"]
        require(isinstance(s["temperature"], list) and len(s["temperature"]) == len({"cooling": [0,0], "closed": [0,0], "dae": [0,0,0], "enthalpy": [0], "stiff": [0,0,0], "heater": [0,0], "schedule": [0], "nonlinear": [0,0,0]}[case]))
        require(all(0 < number(t) < 1000 for t in s["temperature"]))
        if backend != "pycanha_core":
            require(isinstance(s["links"], list) and len(s["links"]) == (0 if case in ("enthalpy", "schedule") else 2 if case in ("dae", "stiff", "nonlinear") else 1))
            for field in FIELDS[1:]:
                for v in s[field] if isinstance(s[field], list) else [s[field]]: number(v)
            require(abs(s["energy_defect"]-(s["storage_change"]-s["external_energy"]))<=1e-9 and 0<=s["duty"]<=1)
    for t in TIMES[case]: require(len([s for s in samples if abs(s["time"]-t) <= 1e-9]) == 1)
    if backend != "pycanha_core":
        events = result.get("events"); require(isinstance(events, list) and len(events) < 100)
        previous = -1
        for e in events:
            require(number(e["time"]) > previous and e["kind"] in ("heater", "schedule") and e["before"] in (0,1) and e["after"] == 1-e["before"]); previous=e["time"]
        if case in STEADY:
            steady = result["steady"]; require(isinstance(steady, dict) and len(steady["temperature"]) == len(STEADY[case]))
            require(max(abs(number(a)-b) for a,b in zip(steady["temperature"], STEADY[case])) <= policy["steady_temperature_K"])
            require(abs(number(steady["boundary_power"])-(-15 if case == "nonlinear" else 0)) <= policy["steady_power_W"])
        else: require(result.get("steady") is None)
    return result


def compare(left, right, case, temperatures_only=False):
    fields = ("temperature",) if temperatures_only else FIELDS
    errors = {k: 0. for k in fields}
    for t in TIMES[case]:
        rows = []
        for result in (left, right):
            matches = [s for s in result["samples"] if abs(number(s["time"])-t) <= 1e-9]; require(len(matches) == 1); rows.append(matches[0])
        for field in fields:
            a,b = rows[0][field], rows[1][field]
            if not isinstance(a, list): a,b = [a],[b]
            require(isinstance(b,list) and len(a) == len(b))
            errors[field] = max([errors[field]]+[abs(number(x)-number(y)) for x,y in zip(a,b)])
    if not temperatures_only:
        a,b=left["events"],right["events"];require(len(a)==len(b))
        errors["event_time"] = 0.
        for x,y in zip(a,b):
            require(all(x[k]==y[k] for k in ("kind","before","after")))
            errors["event_time"] = max(errors["event_time"],abs(number(x["time"])-number(y["time"])))
    return errors


def analytic(case, time):
    t=time
    if case in ("cooling","dae"):
        x=300+10*math.exp(-t/2); return [x,300] if case=="cooling" else [x,(x+300)/2,300]
    if case=="closed": return [298+12*math.exp(-10*t/3),298-8*math.exp(-10*t/3)]
    if case in ("enthalpy","schedule"): return [math.sqrt(90000+500*(t if case=="enthalpy" else min(max(t-1,0),1)))]
    if case=="stiff":
        trace=-100010001.;fast=(trace-math.sqrt(trace*trace-4e8))/2;slow=1e8/fast
        bs=(99990-fast*10)/(slow-fast);a_s=(slow+10001)/10000*bs
        return [290+a_s*math.exp(slow*t)+(20-a_s)*math.exp(fast*t),290+bs*math.exp(slow*t)+(10-bs)*math.exp(fast*t),290]
    if case=="heater":
        first=math.log(16/5)
        if t<first:return [310-16*math.exp(-t),290]
        index=int((t-first)/math.log(3));elapsed=t-first-index*math.log(3)
        return [290+15*math.exp(-elapsed) if index%2==0 else 310-15*math.exp(-elapsed),290]
    raise ValueError("no_analytic_transient")


def analytic_error(result, case):
    require(case != "nonlinear")
    error=0.
    for t in TIMES[case]:
        rows=[s for s in result["samples"] if abs(s["time"]-t)<=1e-9];require(len(rows)==1)
        error=max(error,max(abs(number(a)-b) for a,b in zip(rows[0]["temperature"],analytic(case,t))))
    if case=="heater":
        require(len(result["events"])==5)
        expected=[0]+[math.log(16/5)+k*math.log(3) for k in range(4)]
        error=max(error,max(abs(number(e["time"])-t) for e,t in zip(result["events"],expected)))
    elif case=="schedule": require(result["events"]==[dict(time=0,kind="schedule",before=1,after=0),dict(time=1,kind="schedule",before=0,after=1),dict(time=2,kind="schedule",before=1,after=0)])
    elif result.get("backend")!="pycanha_core": require(result["events"]==[])
    return error


def expected_comparisons(policy):
    result={}
    for case in policy["cases"]:
        for kind in ("ida-refinement","radau-refinement","ida-radau","native-ida","native-radau"):
            limits=dict(policy["native_agreement"] if kind.startswith("native") else policy["reference_agreement"])
            if case=="stiff" and kind.startswith("native"):limits.update(policy["stiff_native_overrides"])
            result[case+":"+kind]=limits
        if case!="nonlinear":
            for kind in ("ida-analytic","radau-analytic"): result[case+":"+kind]={"temperature":policy["reference_agreement"]["temperature"]}
    for case in policy["pycanha"]["required_cases"]:
        for kind in ("pycanha-refinement","pycanha-analytic","native-pycanha"):
            result[case+":"+kind]={"temperature":policy["pycanha"]["native_temperature_agreement_K" if kind.startswith("native") else "temperature_agreement_K"]}
    return result


def assess(report, policy, hashes, candidate):
    try:
        require(report["schema_version"]==1 and report["candidate"]==candidate and report["input_sha256"]==hashes and report["profile"]==policy["profile"])
        require(report["scope"]=="engine_numerical_qualification" and report["vendor_compatibility_qualified"] is False and report["q1_qualified"] is False and report["status"]=="passed")
        expected=expected_comparisons(policy);rows=report["comparisons"]
        require(len(rows)==len(expected) and {r["id"] for r in rows}==set(expected))
        for row in rows:
            require(row["limits"]==expected[row["id"]] and set(row["maximum_errors"])==set(row["limits"]) and row["status"]=="passed")
            for k,limit in row["limits"].items():require(0<=number(row["maximum_errors"][k])<=limit)
        runs=report["runs"]
        keys={(c,b,l) for c in policy["cases"] for b in policy["required_backends"] for l in ("coarse","fine")}|{(c,"native","native") for c in policy["cases"]}|{(c,"pycanha_core",l) for c in policy["pycanha"]["required_cases"] for l in ("coarse","fine")}
        require(len(runs)==len(keys) and {(r["case"],r["backend"],r["level"]) for r in runs}==keys)
        for r in runs:
            require(hash_value(r["result_sha256"]) and r["execution_mode"]==("fcst_native" if r["backend"]=="native" else "reference_external"))
            require(r["version"]==("owned" if r["backend"]=="native" else policy["pycanha"]["version"] if r["backend"]=="pycanha_core" else policy["required_backends"][r["backend"]]))
        require(len({r["result_sha256"] for r in runs})==len(runs))
        provenance=report["provenance"]
        require(set(provenance)=={"native_subject_sha256","ida_source","scipy_runtime_sha256","pycanha_runtime_sha256"})
        for k in ("native_subject_sha256","scipy_runtime_sha256","pycanha_runtime_sha256"):require(hash_value(provenance[k]))
        source=provenance["ida_source"]
        require(source["archive_sha256"]=="a1aa9261c4034da363db379ffe2db0a3b77980f526ee0471f5f56dc53a9c2ed2" and source["revision"]=="cb681a4e3a46bcad903fb966284d6f53e85bdb94")
        require(hash_value(source["license_sha256"]) and "fcst-ida-reference.exe" in source["runtime_sha256"] and all(hash_value(v) for v in source["runtime_sha256"].values()))
        require(report["pycanha_excluded_cases"]==policy["pycanha"]["excluded_cases"])
    except (KeyError,TypeError,IndexError) as error:raise ValueError("thermal_reference_evidence_invalid") from error
    return True
