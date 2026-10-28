# SPDX-License-Identifier: MIT OR Apache-2.0
"""Executable WP055 acceptance with frozen expected IDs; no production FE claims."""
import argparse
from copy import deepcopy
from hashlib import sha256
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"python"))
from fcst_contracts import read, inspect, ContractError, loads
from fcst_app.persistence import Package, PersistenceError, Limits, encode, semantic_hash, save_package, recover_package, downgrade_export
from fcst_app.spatial_arrays import write_spatial, read_spatial, digest
from fcst_app.arrays import libraries
from fcst_app.store import ProjectStore
from fcst_tools.gate import evaluate
from fcst_tools.privacy import Scanner, BlobReader, _inspect_git, git
from fcst_tools.spatial_oracles import steady_rod, transient_mode, rotated_flux, boundary_power


def value(): return json.loads((ROOT/"tests/fixtures/spatial/solid-surface-rotated.json").read_bytes())
def model(): return json.loads((ROOT/"tests/fixtures/contracts/network.json").read_bytes())


class Acceptance(unittest.TestCase):
    def setUp(self):
        folder=ROOT/".local/test-scratch";folder.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=folder);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def package(self):
        return Package.create(model(),[(value()["id"],"spatial","spatial/fields.h5",write_spatial(value()),[])])

    def test_inventory(self):
        manifest=json.loads((ROOT/"ci/fem-reuse.json").read_bytes())
        self.assertEqual({g["group"] for g in manifest["groups"]},{"analysis","mesh","material_selection_load","result","examples_tests","external_reference"})
        self.assertEqual(manifest["asset_sha256"],json.loads((ROOT/"ci/host-profile.json").read_bytes())["platforms"]["Windows"]["sha256"])
        for g in manifest["groups"]:
            self.assertTrue(g["symbols"] and g["dependencies"] and g["reason"] and g["maintenance"] and g["deployment"])
            self.assertIn(g["disposition"],{"reuse_api","adapt_source","replace","defer"})
            if g["disposition"]=="replace": self.assertTrue(g["replacement_justification"])
            for f in g["files"]:
                self.assertEqual(len(f["sha256"]),64);self.assertEqual(len(f["notice_sha256"]),64)
                self.assertIn(manifest["source_revision"],f["source_url"])
                self.assertTrue(f["license"] and f["source_adoption"])
        broken=deepcopy(manifest);broken["groups"][0]["files"][0].pop("sha256")
        with self.assertRaises(KeyError): _=broken["groups"][0]["files"][0]["sha256"]

    def test_fixture_provenance(self):
        manifest=json.loads((ROOT/"ci/spatial-fixtures.json").read_bytes())
        self.assertEqual(manifest["rights"],"redistributable");self.assertFalse(manifest["upstream_adaptation"])
        self.assertEqual(manifest["privacy"],"synthetic")
        for name,h in json.loads((ROOT/"ci/foundation-baseline-pins.json").read_bytes()).items():
            self.assertEqual(sha256((ROOT/name).read_bytes()).hexdigest(),h,name)
        policy=json.loads((ROOT/"ci/publication-policy.json").read_bytes())
        scanner=Scanner(policy)
        for file in [ROOT/"ci/spatial-fixtures.json",*sorted((ROOT/"tests/fixtures/spatial").glob("*.json"))]: scanner.scan(file.name,file.read_bytes())
        self.assertFalse(scanner.findings)
        scanner.scan("restricted/example.json",b"{}")
        self.assertTrue(scanner.findings)

    def test_contract_conformance(self):
        fixtures=ROOT/"tests/fixtures/spatial"
        cases=json.loads((fixtures/"cases.json").read_bytes())["cases"]
        coverage=json.loads((ROOT/"ci/coverage.json").read_bytes())
        self.assertEqual(set(coverage["spatial_cases"]),set(CASE_TESTS))
        self.assertEqual(sorted(c["id"] for c in cases),sorted(coverage["spatial_vectors"]))
        from jsonschema import Draft202012Validator
        from fcst_contracts import BUNDLE
        schema=Draft202012Validator(BUNDLE["schemas"]["spatial"])
        for case in cases:
            raw=(fixtures/case["path"]).read_bytes();actual=inspect("spatial",raw)
            self.assertEqual(sha256(raw).hexdigest(),case["sha256"])
            self.assertEqual(actual["status"],case["status"],case["id"])
            self.assertEqual(actual.get("code"),case.get("code"),case["id"])
            if case["status"]=="passed":
                schema.validate(json.loads(raw));self.assertEqual(actual["semantic_hash"],case["semantic_hash"])
            elif case["code"]=="schema": self.assertTrue(list(schema.iter_errors(json.loads(raw))))
            if WORKER:
                native=subprocess.run([str(WORKER),"--contract","spatial"],input=raw,capture_output=True,timeout=30)
                self.assertEqual(actual,json.loads(native.stdout),case["id"])
                self.assertEqual(native.returncode,0 if case["status"]=="passed" else 1)

    def test_version_matrix(self):
        package=self.package()
        self.assertEqual(package.manifest["contract_version"],"2.0.0")
        with self.assertRaisesRegex(ContractError,"version"): read("manifest",package.manifest)
        read("manifest2",package.manifest)
        for major in ("1.0.0","3.0.0"):
            broken=deepcopy(package.manifest);broken["contract_version"]=major
            with self.assertRaises(ContractError): Package(broken,package.files)
        with self.assertRaisesRegex(PersistenceError,"unsupported_downgrade"): downgrade_export(package,"0.9")
        plain=Package.create(model());self.assertEqual(plain.manifest["contract_version"],"1.0.0")

    def test_independent_oracles(self):
        c=json.loads((ROOT/"ci/spatial-criteria-v1.json").read_bytes())
        for x in c["sample_x"]:
            v=steady_rod(x)
            self.assertAlmostEqual(v["temperature_K"],300+20*x,delta=c["absolute"])
            self.assertEqual(v["flux_W_m2"],-40);self.assertEqual(v["power_W"],-20)
            for t in c["sample_times"]:
                actual=transient_mode(x,t)
                # Independent series expansion of exp, with a controlled Taylor tail.
                a=-math.pi**2*.1*t
                expected=300+sum(a**n/math.factorial(n) for n in range(40))*math.sin(math.pi*x)
                self.assertAlmostEqual(actual,expected,delta=c["absolute"])
        k=c["anisotropy"]
        self.assertEqual(rotated_flux(k["local_K"],k["local_gradient"],k["rotation"]),k["expected_global_flux"])
        b=c["boundary"];self.assertEqual(boundary_power(b["q"],b["outward_normal"],b["area_m2"]),4)
        self.assertEqual(boundary_power(b["q"],[-n for n in b["outward_normal"]],b["area_m2"]),-4)
        from fcst_contracts.spatial import integrated_boundary_power
        v=value();self.assertEqual(integrated_boundary_power(v,v["cells"][1]["id"]),-4)

    def test_external_dispositions(self):
        for p in json.loads((ROOT/"ci/fem-reuse.json").read_bytes())["external_profiles"]:
            self.assertEqual(p["disposition"],"deferred");self.assertFalse(p["qualified"])
            self.assertEqual(p["execution_mode"],"reference_external");self.assertTrue(p["reason"])

    def test_roundtrip_reconstruction(self):
        package=self.package();data=package.files["spatial/fields.h5"]
        for expanded in (False,True):
            target=self.root/("expanded" if expanded else "portable.fcst")
            save_package(package,target,expanded=expanded)
            self.assertEqual(read_spatial(Package.open(target).files["spatial/fields.h5"]),read("spatial",value()))
            script="""from fcst_app.persistence import Package
from fcst_app.store import ProjectStore
from fcst_app.spatial_arrays import read_spatial
import sys
with ProjectStore.create(sys.argv[2],package=Package.open(sys.argv[1])) as s:
 p=s.export_package();v=read_spatial(p.files['spatial/fields.h5']);assert v['contract_version']=='2.0.0' and len(v['fields'])==2
"""
            p=subprocess.run([sys.executable,"-I","-c",script,str(target),str(self.root/(str(expanded)+".db"))],capture_output=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stderr.decode(errors="replace")[-500:])
        self.assertEqual(data,package.files["spatial/fields.h5"])

    def test_corruption_identity_historical_invalidation(self):
        h5py,np=libraries();raw=write_spatial(value())
        for name in ("vertices","heat_flux","temperature","vertex_uuid","connectivity"):
            buffer=io.BytesIO(raw)
            with h5py.File(buffer,"r+") as f:
                d=f[name];index=tuple(0 for _ in d.shape);d[index]=d[index]+1
            with self.assertRaises(PersistenceError): read_spatial(buffer.getvalue())
        package=self.package();corrupt=dict(package.files);corrupt["spatial/fields.h5"]=b"bad"
        with self.assertRaises(ContractError): Package(package.manifest,corrupt)
        with ProjectStore.create(self.root/"derived.db",package=package) as store:
            model0=store.snapshot();entity=deepcopy(model0["entities"][-1]);rid=value()["id"]
            store.register_derived(rid,"solve",[entity["id"]],expected_revision=0)
            self.assertEqual(store.spatial_result(rid)["mesh_revision"],value()["mesh_revision"])
            entity["conductance"]["value"]=4
            store.apply("synthetic",{"changes.apply"},model0["project_id"],0,"change",{"upsert":[entity],"delete":[]})
            with self.assertRaisesRegex(PersistenceError,"stale_result"): store.derived(rid)
            with self.assertRaisesRegex(PersistenceError,"stale_result"): store.spatial_result(rid)
            self.assertTrue(store.derived(rid,historical=True)["stale"])
            self.assertEqual(store.spatial_result(rid,historical=True)["model_hash"],value()["model_hash"])
            self.assertEqual(read_spatial(store.export_package().files["spatial/fields.h5"])["model_hash"],value()["model_hash"])
            store.db.execute("UPDATE artifacts SET data=?",(b"corrupt",))
            with self.assertRaises(ContractError): store.export_package()

    def test_extended_crash_recovery(self):
        package=self.package()
        for expanded in (False,True):
            for point in ("write","flush","fsync","verify","backup","journal","replace","sync"):
                target=self.root/(str(expanded)+point)
                save_package(package,target,expanded=expanded)
                script="""import os,sys
from fcst_app.persistence import Package,save_package
p=Package.open(sys.argv[1]);m=dict(p.model);m['revision']=1
a=[(r['id'],r['role'],r['artifact']['path'],p.files[r['artifact']['path']],r['dependencies']) for r in p.manifest['artifacts'] if r['role']=='spatial']
def fault(point):
 if point==sys.argv[2]: os._exit(73)
save_package(Package.create(m,a),sys.argv[1],expanded=sys.argv[3]=='True',fault=fault)
"""
                p=subprocess.run([sys.executable,"-I","-c",script,str(target),point,str(expanded)],capture_output=True,timeout=30)
                self.assertEqual(p.returncode,73)
                recovered=recover_package(target)
                self.assertEqual(recovered.model["revision"],1 if point in {"replace","sync"} else 0)
                self.assertEqual(read_spatial(recovered.files["spatial/fields.h5"]),read("spatial",value()))

    def test_hostile_layout_and_budgets(self):
        h5py,np=libraries();raw=write_spatial(value())
        for mode in ("soft","hard","external","virtual","filter","oversized","unit","shape","extra"):
            buf=io.BytesIO(raw)
            with h5py.File(buf,"r+") as f:
                if mode=="extra": f.create_dataset("extra",data=[0])
                elif mode=="hard": del f["time"];f["time"]=f["vertices"]
                elif mode=="unit": f["heat_flux"].attrs["unit"]="W"
                else:
                    del f["heat_flux"]
                    if mode=="soft": f["heat_flux"]=h5py.SoftLink("/vertices")
                    elif mode=="external": f["heat_flux"]=h5py.ExternalLink("absent.h5","/data")
                    elif mode=="virtual":
                        layout=h5py.VirtualLayout((2,4,3),dtype="<f8");layout[:]=h5py.VirtualSource("absent.h5","/data",shape=(2,4,3));f.create_virtual_dataset("heat_flux",layout)
                    elif mode=="filter": f.create_dataset("heat_flux",data=np.zeros((2,4,3)),compression="gzip")
                    elif mode=="oversized": f.create_dataset("heat_flux",shape=(1000000000,),dtype="<f8")
                    elif mode=="shape": f.create_dataset("heat_flux",data=np.zeros((2,4)))
                    if mode in {"filter","oversized","shape"}: f["heat_flux"].attrs["unit"]="W/m2"
            with self.subTest(mode=mode),self.assertRaises(PersistenceError): read_spatial(buf.getvalue())
        with self.assertRaisesRegex(PersistenceError,"hdf5_limit"): read_spatial(raw,max_bytes=1)
        with self.assertRaises(PersistenceError): Package(self.package().manifest,self.package().files,limits=Limits(item_bytes=100))

    def test_audit_and_issue_ledger(self):
        ledger=json.loads((ROOT/"ci/foundation-issues.json").read_bytes())
        self.assertEqual(len(ledger["retained_audit"]),8)
        coverage=json.loads((ROOT/"ci/coverage.json").read_bytes())
        for row in ledger["retained_audit"]:
            self.assertTrue(row["regressions"])
            for case in row["regressions"]:
                self.assertIn(case,coverage["unit_cases"]+coverage["persistence_cases"])
        for row in ledger["issues"]:
            self.assertTrue(all(row.get(k) for k in ("id","severity","owner","gate","requirement","reproducer","regression","disposition")))
            self.assertIn(row["disposition"],{"corrected","unsupported"})
        for name,digest0 in ledger["baseline_evidence"].items(): self.assertEqual(sha256((ROOT/name).read_bytes()).hexdigest(),digest0)

    def test_plan_identity_and_expected_cases(self):
        from fcst_tools.delivery import FOUNDATION_CASES
        import csv
        rows=list(csv.DictReader((ROOT/"plans/work-packages.csv").open(newline="")))
        self.assertEqual(len(rows),22);self.assertEqual(len({r["id"] for r in rows}),22)
        for wp in ("WP-06","WP-07","WP-13","WP-16"):
            self.assertIn("WP-05.5",next(r for r in rows if r["id"]==wp)["depends_on"].split(";"))
        acceptance=list(csv.DictReader((ROOT/"plans/WP-05.5-acceptance.csv").open(newline="")))
        self.assertEqual({r["case_id"] for r in acceptance},FOUNDATION_CASES)
        self.assertEqual(set(CASE_TESTS)|{f"WP055-HOST-{i:03d}" for i in range(1,5)}|{"WP055-HAND-001","WP055-HAND-002"},FOUNDATION_CASES)

    def test_resource_profile(self):
        from fcst_contracts import MAX_BYTES
        raw=write_spatial(value());package=self.package();limits=Limits()
        profile={"json_limit":MAX_BYTES,"member_limit":limits.item_bytes,"total_limit":limits.total_bytes,"member_count_limit":limits.items,
            "descriptor_bytes":len(encode(value())),"array_container_bytes":len(raw),"package_bytes":len(package.zip_bytes()),
            "supported_vertices":4096,"supported_cells":4096,"supported_times":64,
            "limits_are_joint":True,"product_scale_qualified":False}
        self.assertLess(profile["descriptor_bytes"],MAX_BYTES);self.assertLess(len(raw),limits.item_bytes)
        h5py,np=libraries()
        # A representative larger accepted mesh uses duplicate physical cells with unique IDs,
        # distinct vertices and one time sample; the JSON budget remains the tighter constraint.
        v=value();v["times"]=[0]
        for f in v["fields"]: f["values"]=f["values"][:1]
        original=deepcopy(v)
        for block in range(1,32):
            v["vertices"].extend([[x+2*block,y,z] for x,y,z in original["vertices"]])
            newids=[str(uuid.uuid5(uuid.NAMESPACE_URL,"synthetic-vertex-"+str(block)+"-"+str(i))) for i in range(4)]
            v["vertex_ids"].extend(newids)
            for i,c in enumerate(original["cells"]):
                v["cells"].append({**c,"id":str(uuid.uuid5(uuid.NAMESPACE_URL,"synthetic-cell-"+str(block)+"-"+str(i))),"vertices":[x+4*block for x in c["vertices"]]})
            for f,old in zip(v["fields"],original["fields"]): f["entity_ids"].extend(newids);f["values"][0].extend(old["values"][0])
        from fcst_contracts.spatial import mesh_hash
        v["mesh_revision"]=mesh_hash(v)
        larger=write_spatial(v)
        self.assertEqual(len(read_spatial(larger)["vertices"]),128)
        profile.update(representative_vertices=128,representative_cells=64,representative_json_bytes=len(encode(v)),representative_hdf5_bytes=len(larger))
        (REPORT.parent/"spatial-resources.json").write_bytes(encode(profile)+b"\n")

    def test_publication_bytes_and_planted_findings(self):
        policy=json.loads((ROOT/"ci/publication-policy.json").read_bytes());scanner=Scanner(policy)
        for folder in ("python","engine","tools","ci","spec/schemas","tests/fixtures/spatial"):
            for file in sorted((ROOT/folder).rglob("*")):
                if file.is_file() and file.suffix in {".py",".cpp",".hpp",".inc",".json"}:
                    scanner.scan(file.relative_to(ROOT).as_posix(),file.read_bytes())
        self.assertFalse(scanner.findings,scanner.findings)
        for filename,raw in (("planted.txt",("gh"+"p_"+"S"*36).encode()),("screenshot.png",b"synthetic"),("restricted/input.json",b"{}")):
            bad=Scanner(policy);bad.scan(filename,raw);self.assertTrue(bad.findings)

    def test_publication_scanner_cost_and_equivalence(self):
        # Repeated blob, safe and restricted paths, deleted secret and unapproved
        # metadata are compared byte-for-byte by the standard-library regression.
        sys.path.insert(0,str(ROOT/"tests"))
        from test_spatial import SpatialTests
        result=unittest.TestResult()
        SpatialTests("test_batch_scanner_preserves_context_metadata_history_and_budget").run(result)
        self.assertTrue(result.wasSuccessful(),result.errors+result.failures)
        policy=json.loads((ROOT/"ci/publication-policy.json").read_bytes())
        # Benchmark actual repeated blob retrieval separately from context inspection.
        oid=git(ROOT,"rev-parse","HEAD:README.md").decode().strip()
        start=time.perf_counter();legacy=[git(ROOT,"cat-file","blob",oid) for _ in range(20)];legacy_s=time.perf_counter()-start
        reader=BlobReader(ROOT,policy["max_item_bytes"])
        try:
            start=time.perf_counter();batch=[reader.read(oid) for _ in range(20)];batch_s=time.perf_counter()-start
        finally: reader.close()
        self.assertEqual(legacy,batch)
        report={"reads":20,"unique_blobs":1,"legacy_seconds":round(legacy_s,6),"batch_seconds":round(batch_s,6),
            "disposition":"Batch Git blob retrieval and bounded byte cache; rescan every path and commit with unchanged budgets; never cache clearance"}
        (REPORT.parent/"spatial-scanner-cost.json").write_bytes(encode(report)+b"\n")


WORKER=None
REPORT=ROOT/".local/spatial.json"
CASE_TESTS={
 "WP055-INV-001":"test_inventory", "WP055-INV-002":"test_fixture_provenance",
 **{f"WP055-CTR-{i:03d}":"test_contract_conformance" for i in (1,2,3,5)},
 "WP055-CTR-004":"test_version_matrix", "WP055-NUM-001":"test_independent_oracles", "WP055-NUM-002":"test_external_dispositions",
 "WP055-STORE-001":"test_roundtrip_reconstruction", "WP055-STORE-002":"test_corruption_identity_historical_invalidation",
 "WP055-STORE-003":"test_extended_crash_recovery", "WP055-STORE-004":"test_hostile_layout_and_budgets",
 "WP055-AUDIT-001":"test_audit_and_issue_ledger", "WP055-AUDIT-002":"test_audit_and_issue_ledger",
 "WP055-TOOL-001":"test_plan_identity_and_expected_cases", "WP055-TOOL-002":"test_resource_profile",
 "WP055-PUB-001":"test_publication_bytes_and_planted_findings", "WP055-PUB-002":"test_publication_scanner_cost_and_equivalence"}


def main():
    global WORKER, REPORT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker",type=Path,required=True);parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args();WORKER=args.worker.resolve();REPORT=args.report;args.report.parent.mkdir(parents=True,exist_ok=True)
    results={}
    for method in sorted(set(CASE_TESTS.values())):
        stream=io.StringIO();test=Acceptance(method);result=unittest.TextTestRunner(stream=stream).run(unittest.TestSuite([test]))
        (args.report.parent/(method+".log")).write_text(stream.getvalue(),encoding="utf-8")
        results[method]="passed" if result.wasSuccessful() and not result.skipped else "failed"
    cases=[{"id":case,"status":results[method]} for case,method in CASE_TESTS.items()]
    from fcst_tools.foundation import input_hashes
    report={"work_package":"WP-05.5","candidate":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),"cases":cases,"input_sha256":input_hashes(ROOT),
        "gate":evaluate(sorted(CASE_TESTS),cases),"scope":"Spatial foundation contract, persistence and independent fixtures; host and administrative handoff gates collected separately"}
    args.report.write_bytes(encode(report)+b"\n")
    print(json.dumps({"gate":report["gate"],"failures":[k for k,v in results.items() if v!="passed"]}))
    return 0 if report["gate"]["status"]=="passed" else 1


if __name__=="__main__": raise SystemExit(main())
