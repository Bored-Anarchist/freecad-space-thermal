# SPDX-License-Identifier: MIT OR Apache-2.0
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from fcst_contracts import read, inspect, ContractError
from fcst_contracts.spatial import downgrade, field_global
from fcst_tools.gate import evaluate
from fcst_tools.privacy import Scanner, BlobReader, _inspect_git, git
from fcst_app.fem_adapter import capability, reconcile_attachment
from fcst_app.persistence import PersistenceError

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/spatial"


class SpatialTests(unittest.TestCase):
    def test_frozen_spatial_vectors_and_v1_pins(self):
        for case in json.loads((FIXTURES/"cases.json").read_bytes())["cases"]:
            raw=(FIXTURES/case["path"]).read_bytes()
            self.assertEqual(sha256(raw).hexdigest(),case["sha256"])
            result=inspect("spatial", raw)
            self.assertEqual(result["status"],case["status"],case["id"])
            self.assertEqual(result.get("code"),case.get("code"),case["id"])
            if "semantic_hash" in case:
                self.assertEqual(result["semantic_hash"],case["semantic_hash"])
        pins=json.loads((ROOT/"ci/foundation-baseline-pins.json").read_bytes())
        for name,digest in pins.items():
            self.assertEqual(sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)

    def test_rotation_mapping_order_version_and_lossy_downgrade(self):
        value=json.loads((FIXTURES/"solid-surface-rotated.json").read_bytes())
        self.assertEqual(field_global(value,"heat_flux"),[[-3,2,8]]*4)
        v=deepcopy(value);v["mappings"].reverse()
        self.assertEqual(read("spatial",v)["mappings"],v["mappings"])
        for version in ("1.0.0","0.9","3.0.0"):
            with self.assertRaisesRegex(ContractError,"lossy_downgrade"): downgrade(value,version)
        with self.assertRaisesRegex(ContractError,"version"): read("model",value)

    def test_missing_changed_host_api_and_ambiguous_attachment(self):
        for obj in (object(),type("Changed",(),{"symbol":1})()):
            with self.assertRaisesRegex(PersistenceError,"host_capability_missing"): capability(obj,"symbol")
        old={"uuid":"synthetic","revision":0,"signature":"same"}
        self.assertEqual(reconcile_attachment(old,[{"uuid":"other"},old]),old)
        for candidates in ([],[old,old],[{**old,"revision":1}]):
            with self.assertRaisesRegex(PersistenceError,"attachment_reassignment_required"): reconcile_attachment(old,candidates)

    def test_required_handoff_coverage_cannot_be_missing_stale_or_substituted(self):
        expected=["WP055-CTR-001","WP055-HOST-001"]
        okay=[{"id":i,"status":"passed"} for i in expected]
        self.assertEqual(evaluate(expected,okay)["status"],"passed")
        for bad in (okay[:1],okay+okay[:1],[{**r,"status":"skipped"} for r in okay],[{"id":"FEM-REUSE-001","status":"passed"}]):
            self.assertEqual(evaluate(expected,bad)["status"],"failed")
        from fcst_tools.foundation import assess_reports
        from fcst_tools.delivery import FOUNDATION_CASES
        inputs={"source.py":"0"*64};candidate="0"*40
        hostids={f"WP055-HOST-{i:03d}" for i in range(1,5)}
        ids=FOUNDATION_CASES-hostids-{"WP055-HAND-001","WP055-HAND-002"}
        report={"candidate":candidate,"input_sha256":inputs,"gate":{"status":"passed"},"cases":[{"id":i,"status":"passed"} for i in sorted(ids)]}
        host={"candidate":candidate,"input_sha256":inputs,"status":"passed","cases":[{"id":i,"status":"passed"} for i in sorted(hostids)]}
        self.assertTrue(assess_reports(report,report,host,inputs,candidate))
        for field,val in (("candidate","1"*40),("input_sha256",{}),("cases",report["cases"][:-1])):
            bad={**report,field:val}
            with self.assertRaises(ValueError): assess_reports(bad,report,host,inputs,candidate)

    def test_batch_scanner_preserves_context_metadata_history_and_budget(self):
        scratch=ROOT/".local/test-scratch";scratch.mkdir(parents=True,exist_ok=True)
        policy=json.loads((ROOT/"ci/publication-policy.json").read_bytes())
        class Legacy:
            def read(self,oid): return git(repo,"cat-file","blob",oid)
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            repo=Path(tmp)
            def command(*args):
                return subprocess.run(["git","-C",str(repo),*args],capture_output=True,check=True).stdout
            command("init","-q")
            identity=policy["approved_identities"][0]
            command("config","user.name",identity["name"]);command("config","user.email",identity["email"])
            (repo/"safe.txt").write_text("synthetic")
            command("add",".");command("-c","core.hooksPath=","commit","-qm","Synthetic base")
            (repo/"restricted").mkdir();(repo/"restricted/same.txt").write_text("synthetic")
            (repo/"old.txt").write_text("gh"+"p_"+"S"*36)
            command("add",".");command("-c","core.hooksPath=","-c","user.name=Unapproved synthetic","commit","-qm","Synthetic restricted context")
            command("rm","old.txt");command("-c","core.hooksPath=","commit","-qm","Synthetic deletion")
            legacy=Scanner(policy);_inspect_git(legacy,repo,"HEAD",True,Legacy())
            batch=Scanner(policy);reader=BlobReader(repo,policy["max_item_bytes"])
            try: _inspect_git(batch,repo,"HEAD",True,reader)
            finally: reader.close()
            self.assertEqual(batch.report(),legacy.report())
            categories={f["category"] for f in batch.findings}
            self.assertTrue({"restricted_or_unsafe_path","credential","unapproved_identity"} <= categories)
            small=deepcopy(policy);small["max_total_bytes"]=1
            with self.assertRaises(ValueError): _inspect_git(Scanner(small),repo,"HEAD",True,Legacy())
