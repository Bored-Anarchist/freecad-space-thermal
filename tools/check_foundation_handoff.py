# SPDX-License-Identifier: MIT OR Apache-2.0
"""Final TST-022 gate shared by local verification and the required CI aggregate."""
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"python"))
from fcst_tools.foundation import input_hashes, assess_reports
from fcst_tools.delivery import FOUNDATION_CASES
from fcst_tools.gate import evaluate
from fcst_tools.privacy import Scanner, POLICY_PATH, inspect_git


def check(directory):
    candidate=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    def load(path): return json.loads(path.read_bytes())
    reports={}
    for preset in ("windows-debug","windows-release"):
        matches=list(directory.rglob("verification.json"))
        matches=[p for p in matches if load(p).get("preset")==preset]
        if len(matches)!=1: raise ValueError("missing_or_duplicate_configuration")
        path=matches[0];v=load(path)
        if v["candidate"]!=candidate or v["gate"]["status"]!="passed": raise ValueError("configuration_not_passed")
        from verify import STEPS
        expected=load(ROOT/"ci/coverage.json")["unit_cases"]+STEPS
        if evaluate(expected,v["cases"])["status"]!="passed": raise ValueError("configuration_coverage")
        reports[preset]=load(path.parent/"spatial.json")
        numerical=load(path.parent/"numerical.json");persistence=load(path.parent/"persistence.json")
        jobs=load(path.parent/"jobs.json")
        if jobs["gate"]["status"]!="passed": raise ValueError("job_lifecycle_regression")
        from check_mcp import assess as assess_mcp
        mcp=load(path.parent/'mcp.json')
        assess_mcp(mcp,candidate,jobs['native_build_sha256'])
        exchange=load(path.parent/"exchange.json")
        if (exchange["candidate"]!=candidate or evaluate(load(ROOT/"ci/exchange-acceptance.json")["required_cases"],exchange["cases"])["status"]!="passed"
                or exchange["gate"]["status"]!="passed"):
            raise ValueError("exchange_regression")
        td=load(path.parent/"td.json")
        if (td["candidate"]!=candidate or td.get("qualified") is not False
                or evaluate(load(ROOT/"ci/td-acceptance.json")["required_cases"],td["cases"])["status"]!="passed"
                or td["gate"]["status"]!="passed"):
            raise ValueError("td_adapter_regression_or_false_qualification")
        if numerical["gate"]["status"]!="passed" or persistence["gate"]["status"]!="passed": raise ValueError("baseline_regression")
        esatan=load(path.parent/'esatan.json')
        if (esatan.get('candidate')!=candidate or esatan.get('qualified') is not False
                or evaluate(load(ROOT/'ci/esatan-acceptance.json')['required_cases'],esatan['cases'])['status']!='passed'
                or esatan['gate']['status']!='passed'
                or esatan.get('qualification_holds')!=load(ROOT/'ci/esatan-acceptance.json')['qualification_holds']
                or not esatan.get('input_sha256')
                or any(sha256((ROOT/name).read_bytes()).hexdigest()!=digest for name,digest in esatan['input_sha256'].items())):
            raise ValueError('esatan_regression_stale_inputs_or_false_qualification')
        contracts=load(path.parent/"contracts.json")
        if contracts["status"]!="passed": raise ValueError("contract_regression")
        from fcst_tools.thermal import assess as assess_thermal, input_hashes as thermal_hashes
        assess_thermal(load(path.parent/'thermal.json'), load(ROOT/'ci/thermal-acceptance.json'), thermal_hashes(ROOT), candidate)
        from fcst_tools.thermal_references import assess as assess_references, input_hashes as reference_hashes
        assess_references(load(path.parent/'thermal-references.json'),load(ROOT/'ci/thermal-reference-v1.json'),reference_hashes(ROOT),candidate)
        from fcst_tools.radiation import assess_report as assess_radiation
        from check_radiation import input_hashes as radiation_hashes
        assess_radiation(load(path.parent/'radiation.json'),load(ROOT/'ci/radiation-acceptance-v1.json'),
                        load(ROOT/'ci/numerical-criteria-v1.json')['statistical_policy'],radiation_hashes(),candidate)
        from check_host import assess as assess_host, input_hashes as host_hashes
        assess_host(load(path.parent/'host.json'),candidate,host_hashes(),load(ROOT/'ci/host-acceptance.json'))
        if load(path.parent/'host.json')['worker_sha256']!=load(path.parent/'thermal.json')['binary_sha256']['worker']:
            raise ValueError('host_worker_substitution')

    hosts=list(directory.rglob("fem-probe.json"))
    if len(hosts)!=1: raise ValueError("missing_or_duplicate_host_report")
    host=load(hosts[0]);inputs=input_hashes(ROOT)
    native_reports=list(directory.rglob('dwg-backend.json'))
    if len(native_reports)!=1:raise ValueError('missing_or_duplicate_native_backend_report')
    native=load(native_reports[0]);native_profile=load(ROOT/'ci/dwg-backend.json')
    if (native.get('candidate')!=candidate or native.get('profile')!=native_profile['runtime']
            or native.get('input_sha256')!=native_profile['source_inputs']
            or any(sha256((ROOT/name).read_bytes()).hexdigest()!=value for name,value in native_profile['source_inputs'].items())
            or native.get('gate',{}).get('status')!='passed'
            or evaluate(native_profile['required_cases'],native.get('cases',[]))['status']!='passed'
            or native.get('qualified') is not False or native.get('vendor_runtime_required') is not False):
        raise ValueError('native_backend_identity_or_regression')
    assess_reports(reports["windows-debug"],reports["windows-release"],host,inputs,candidate)
    profile=load(ROOT/"ci/host-profile.json")
    if (host["asset_sha256"]!=profile["platforms"]["Windows"]["sha256"] or host["python_abi"]!="cp311"
            or host["manifest_sha256"]!=sha256((ROOT/"ci/fem-reuse.json").read_bytes()).hexdigest()): raise ValueError("host_identity")
    packages=list(csv.DictReader((ROOT/"plans/work-packages.csv").open(newline="")))
    project=load(ROOT/"plans/github-project.json");backlog=load(ROOT/"plans/github-backlog.json")
    package=next(p for p in packages if p["id"]=="WP-05.5")
    item=next(p for p in project["items"] if p["work_package"]=="WP-05.5")
    link=next(p for p in backlog["issues"] if p["work_package"]=="WP-05.5")
    states={"planned":"Planned","in_progress":"In progress","complete":"Complete","blocked":"Blocked"}
    if item["issue"]!=link["issue"] or item["state"]!=states[package["status"]] or package["completion_gate"]!="P0": raise ValueError("github_plan_state_mismatch")
    handoff=load(ROOT/"ci/foundation-handoff.json")
    if set(handoff["consumers"])!={"WP-06","WP-07","WP-13","WP-16"}: raise ValueError("consumer_handoff_missing")
    for name in handoff["artifacts"]:
        if not (ROOT/name).is_file(): raise ValueError("handoff_artifact_missing")
    scanner=Scanner(load(POLICY_PATH))
    # Every exact report and every candidate path is inspected before publication.
    for path in sorted(directory.rglob("*.json")):
        if path.name in {"verification.json","spatial.json","fem-probe.json","contracts.json","numerical.json","persistence.json","build-info.json","host-smoke.json","host.json","jobs.json","exchange.json","td.json","dwg-backend.json","thermal.json","thermal-references.json","radiation.json","esatan.json"}:
            scanner.scan(path.name,path.read_bytes())
    # Full outgoing history is additionally required locally before push. CI checks
    # the actual checked-out candidate (checkout may intentionally be shallow).
    inspect_git(scanner,ROOT,"HEAD",False)
    if scanner.findings: raise ValueError("publication_clearance_failed")
    cases=reports["windows-debug"]["cases"]+host["cases"]+[{"id":"WP055-HAND-001","status":"passed"},{"id":"WP055-HAND-002","status":"passed"}]
    gate=evaluate(sorted(FOUNDATION_CASES),cases)
    if gate["status"]!="passed": raise ValueError("foundation_coverage")
    return {"work_package":"WP-05.5","candidate":candidate,"input_sha256":inputs,"gate":gate,"cases":cases,
        "publication_payload_sha256":scanner.report()["payload_sha256"],"scope":"Foundation handoff only; later full FEM-REUSE, jobs, GUI and spatial solver acceptance retained"}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--reports",type=Path,required=True);p.add_argument("--report",type=Path,required=True);a=p.parse_args()
    try: report=check(a.reports)
    except (OSError,ValueError,KeyError,StopIteration) as error:
        print("WP-05.5 handoff gate: failed; "+(str(error) if isinstance(error,ValueError) else "missing_or_invalid_evidence"));return 1
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+"\n")
    print("WP-05.5 handoff gate: passed (25 required cases)");return 0


if __name__=="__main__": raise SystemExit(main())
