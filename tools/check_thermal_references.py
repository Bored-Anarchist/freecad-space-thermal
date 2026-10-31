# SPDX-License-Identifier: MIT OR Apache-2.0
"""Required independent WP-11 reference comparisons; raw data remains local."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from profile_support import ROOT, revision
from thermal_reference_build import build, digest
from provision_thermal_references import provision
sys.path.insert(0,str(ROOT/"python"))
from fcst_tools.thermal_references import validate_run, compare, analytic_error, expected_comparisons, assess, input_hashes, require


def execute(executable, arguments, stem, work):
    arguments=list(map(str,arguments))
    if arguments[:1]==["-I"]:arguments[1:1]=["-B","-X","pycache_prefix="+str(work/"unused-bytecode")]
    env={k:v for k,v in os.environ.items() if k not in ("PYTHONPATH","PYTHONHOME")}
    env.update(PATH=str(executable.parent),OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1")
    process=subprocess.run([str(executable),*arguments],cwd=work,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=240)
    (work/(stem+".json")).write_bytes(process.stdout);(work/(stem+".log")).write_bytes(process.stderr)
    if process.returncode or len(process.stdout)>2_000_000:raise ValueError("reference_process_failed_"+stem)
    return process.stdout


def check(subject,configuration,work,candidate,policy):
    ida,source=build(configuration,work);pycanha=provision(work)
    fingerprints={}
    for name,exe,packages in [("scipy",Path(sys.executable),["numpy","scipy"]),("pycanha",pycanha,["pycanha-core","numpy","scipy","mkl","intel-openmp","intel-cmplr-lib-ur","tbb","tcmlib","umf"])]:
        raw=execute(exe,["-I",ROOT/"tools/provision_thermal_references.py","fingerprint",*packages],name+"-fingerprint",work)
        fingerprints[name]=raw.decode("ascii").strip()
    report=dict(schema_version=1,candidate=candidate,profile=policy["profile"],scope=policy["scope"],status="passed",vendor_compatibility_qualified=False,q1_qualified=False,input_sha256=input_hashes(ROOT),runs=[],comparisons=[],pycanha_excluded_cases=policy["pycanha"]["excluded_cases"],provenance=dict(native_subject_sha256=digest(subject),ida_source=source,scipy_runtime_sha256=fingerprints["scipy"],pycanha_runtime_sha256=fingerprints["pycanha"]))
    limits=expected_comparisons(policy)
    def record(case,kind,errors):
        identifier=case+":"+kind
        passed=set(errors)==set(limits[identifier]) and all(0<=v<=limits[identifier][k] for k,v in errors.items())
        report["comparisons"].append(dict(id=identifier,status="passed" if passed else "failed",limits=limits[identifier],maximum_errors=errors))
        if not passed:report["status"]="failed"
    for case in policy["cases"]:
        results={}
        tasks=[("native","native",subject,[case,ROOT/"tests/fixtures/thermal"])]
        for level in ("coarse","fine"):
            tasks.extend([("sundials_ida",level,ida,[case,level]),("scipy_radau",level,Path(sys.executable),["-I",ROOT/"references/thermal/radau_reference.py",case,level])])
            if case in policy["pycanha"]["required_cases"]:tasks.append(("pycanha_core",level,pycanha,["-I",ROOT/"references/thermal/pycanha_reference.py",case,level]))
        for backend,level,exe,args in tasks:
            raw=execute(exe,args,case+"-"+backend+"-"+level,work)
            result=validate_run(json.loads(raw),backend,case,level,policy,candidate);results[backend,level]=result
            report["runs"].append(dict(case=case,backend=backend,level=level,result_sha256=hashlib.sha256(raw).hexdigest(),execution_mode=result["execution_mode"],version="owned" if backend=="native" else result["version"]))
        for short,backend in [("ida","sundials_ida"),("radau","scipy_radau")]:
            record(case,short+"-refinement",compare(results[backend,"coarse"],results[backend,"fine"],case))
            record(case,"native-"+short,compare(results["native","native"],results[backend,"fine"],case))
            if case!="nonlinear":record(case,short+"-analytic",dict(temperature=max(analytic_error(results[backend,l],case) for l in ("coarse","fine"))))
        record(case,"ida-radau",compare(results["sundials_ida","fine"],results["scipy_radau","fine"],case))
        if case in policy["pycanha"]["required_cases"]:
            record(case,"pycanha-refinement",compare(results["pycanha_core","coarse"],results["pycanha_core","fine"],case,True))
            record(case,"pycanha-analytic",dict(temperature=max(analytic_error(results["pycanha_core",l],case) for l in ("coarse","fine"))))
            record(case,"native-pycanha",compare(results["native","native"],results["pycanha_core","fine"],case,True))
        print(case+": compared",flush=True)
    if report["status"]=="passed":assess(report,policy,input_hashes(ROOT),candidate)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--subject",type=Path,required=True);parser.add_argument("--configuration",choices=("Debug","Release"),required=True);parser.add_argument("--report",type=Path,required=True);args=parser.parse_args()
    work=ROOT/".local/thermal-reference-runs"/(args.configuration+"-"+str(time.time_ns()));work.mkdir(parents=True)
    policy=json.loads((ROOT/"ci/thermal-reference-v1.json").read_bytes());candidate=revision()
    try:
        report=check(args.subject.resolve(),args.configuration,work,candidate,policy)
    except Exception:
        # Native/compiler/library errors are retained locally, not copied to CI artifacts.
        import traceback
        (work/"failure.log").write_text(traceback.format_exc(),encoding="utf-8")
        report=dict(schema_version=1,candidate=candidate,status="failed",reason="independent_reference_verification_failed")
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")
    print("WP-11 independent references: "+report["status"])
    return 0 if report["status"]=="passed" else 1


if __name__=="__main__":raise SystemExit(main())
