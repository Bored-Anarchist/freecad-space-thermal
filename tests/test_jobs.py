# SPDX-License-Identifier: MIT OR Apache-2.0
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from fcst_app.jobs import JobStore, Scheduler, reference, artifact, MAX_EVENTS
from fcst_app.persistence import PersistenceError, encode
from fcst_app.store import ProjectStore
from fcst_contracts import read

ROOT = Path(__file__).resolve().parents[1]
ACTOR = "synthetic-actor"
SCOPES = {"job.submit","job.query","job.cancel","result.query","result.attach"}
PEER = ROOT / "tests/fixtures/job_worker.py"


def model():
    value = json.loads((ROOT / "tests/fixtures/contracts/network.json").read_bytes())
    full = json.loads((ROOT / "tests/fixtures/contracts/all-entities-si.json").read_bytes())
    entities = [e for e in full["entities"] if e["kind"] in {"frame","environment","case"}]
    for entity in entities:
        if entity["kind"] == "case":
            entity.update(load_ids=[],control_ids=[],overlays=[])
    value["entities"].extend(entities)
    return read("model",value)


def execution(scenario="failed"):
    return {"profile":"lifecycle-fixture","features":["synthetic"],"mode":"fcst_native","backend":"fixture",
            "build_hash":sha256(PEER.read_bytes()).hexdigest(), "settings":{"scenario":scenario},"dependencies":{}}


class JobTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".local/test-scratch"
        scratch.mkdir(parents=True,exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = ProjectStore.create(self.root / "project.db",model())
        self.addCleanup(self.project.close)
        self.jobs = JobStore(self.project)
        self.case = next(e["id"] for e in model()["entities"] if e["kind"] == "case")

    def submit(self, scenario="failed", **kwargs):
        return self.jobs.submit(ACTOR,SCOPES,kwargs.pop("key","one"),self.case,
                                expected_revision=0,execution=execution(scenario),**kwargs)

    def scheduler(self, scenario="failed"):
        return Scheduler(self.jobs,self.root / "runs",{"fixture":{"execution":execution(scenario),
                         "command":[sys.executable,str(PEER),scenario],"resume_supported":True,"identity_file":str(PEER)}})

    def test_durable_idempotency_snapshot_conflict_and_scope(self):
        first = self.submit()
        other = ProjectStore(self.project.path)
        self.addCleanup(other.close)
        reopened = JobStore(other)
        self.assertEqual(first,reopened.submit(ACTOR,SCOPES,"one",self.case,expected_revision=0,execution=execution()))
        self.assertEqual(encode(self.project.snapshot()),self.jobs.bytes(first["id"],"input/snapshots/model.json"))
        with self.assertRaisesRegex(PersistenceError,"idempotency_conflict"):
            self.submit(seeds=[9])
        with self.assertRaisesRegex(PersistenceError,"unauthorized"):
            reopened.query("another-actor",SCOPES,first["id"])
        with self.assertRaisesRegex(PersistenceError,"unauthorized"):
            self.jobs.submit(ACTOR,set(),"two",self.case,expected_revision=0,execution=execution())
        with self.assertRaisesRegex(PersistenceError,"stale_revision"):
            self.jobs.submit(ACTOR,SCOPES,"two",self.case,expected_revision=9,execution=execution())
        self.assertEqual(first["state"],"queued")

    def test_queued_cancellation_and_terminal_callbacks_are_idempotent(self):
        job = self.submit()
        cancelled = self.jobs.cancel(ACTOR,SCOPES,job["id"])
        self.assertEqual(cancelled,self.jobs.cancel(ACTOR,SCOPES,job["id"]))
        with self.scheduler() as scheduler:
            self.assertIsNone(scheduler.run_next())
        with self.assertRaisesRegex(PersistenceError,"terminal_job"):
            self.jobs.accept(job["id"],{},self.root)

    def test_crash_timeout_and_disconnect_never_succeed(self):
        for scenario in ("crash","oversize","hang","failed","memory"):
            with self.subTest(scenario=scenario):
                job = self.submit(scenario,key=scenario,budget={"wall_s":.7,"cancel_s":.15,"artifact_bytes":1048576})
                with self.scheduler(scenario) as scheduler:
                    result = scheduler.run_next()
                self.assertIn(result["state"],{"failed","interrupted"})
                self.assertIsNone(result["result"])
                with self.assertRaisesRegex(PersistenceError,"result_unavailable"):
                    self.jobs.result(ACTOR,SCOPES,job["id"])
                self.assertEqual(self.project.snapshot(),model())

    def test_restart_lease_and_linked_fresh_attempt(self):
        job = self.submit()
        with self.project.transaction():
            job["state"] = "running"
            self.jobs._put(job)
        with self.scheduler() as scheduler:
            self.assertEqual(self.jobs._get(job["id"])["state"],"interrupted")
            with self.assertRaisesRegex(PersistenceError,"save_busy"):
                with self.scheduler():
                    pass
            child = self.submit(key="retry",parent=job["id"])
            self.assertEqual(child["parent"],job["id"])
            self.assertEqual(scheduler.run_next()["state"],"failed")

    def test_cancel_acknowledgement_and_forced_deadline(self):
        for scenario in ("cancel","hang"):
            job = self.submit(scenario,key=scenario,budget={"wall_s":4,"cancel_s":.2,"artifact_bytes":1048576})
            errors = []
            def cancel():
                try:
                    with ProjectStore(self.project.path) as project:
                        client = JobStore(project)
                        deadline = time.monotonic()+3
                        while time.monotonic() < deadline:
                            if client.query(ACTOR,SCOPES,job["id"])["job"]["sequence"] >= 2:
                                client.cancel(ACTOR,SCOPES,job["id"])
                                return
                            time.sleep(.01)
                        errors.append("progress_missing")
                except Exception:
                    errors.append("client_failure")
            thread = threading.Thread(target=cancel)
            thread.start()
            with self.scheduler(scenario) as scheduler:
                result = scheduler.run_next()
            thread.join(timeout=5)
            self.assertFalse(errors)
            self.assertEqual(result["state"],"cancelled")
            self.assertEqual(result["cancel_acknowledged"],scenario == "cancel")

    def test_artifact_root_hash_and_size_authorization(self):
        data = b"synthetic"
        (self.root / "good.json").write_bytes(data)
        ref = reference("good.json",data)
        self.assertEqual(data,artifact(self.root,ref))
        with self.assertRaises(ValueError):
            artifact(self.root,{**ref,"path":"../good.json"})
        with self.assertRaises(ValueError):
            artifact(self.root,{**ref,"sha256":"0"*64})
        with self.assertRaises(ValueError):
            artifact(self.root,ref,2)
        from unittest.mock import patch
        from types import SimpleNamespace
        with patch.object(Path,"stat",return_value=SimpleNamespace(st_nlink=2,st_mode=0)):
            with self.assertRaisesRegex(PersistenceError,"artifact_root"):
                artifact(self.root,ref)

    def test_budgets_paging_and_failed_submission_rollback(self):
        for budget in ({"wall_s":float("nan"),"cancel_s":1,"artifact_bytes":1},
                       {"wall_s":1,"cancel_s":1,"artifact_bytes":10**9}):
            with self.assertRaisesRegex(PersistenceError,"resource_budget"):
                self.submit(budget=budget)
        self.jobs.fault = lambda point: (_ for _ in ()).throw(RuntimeError("synthetic"))
        with self.assertRaises(RuntimeError):
            self.submit()
        self.jobs.fault = None
        job = self.submit()
        with self.assertRaisesRegex(PersistenceError,"response_limit"):
            self.jobs.query(ACTOR,SCOPES,job["id"],limit=65)

    def test_frozen_submit_cancel_dispatch_and_exact_retry(self):
        envelope = json.loads((ROOT / "tests/fixtures/contracts/operation-job.submit.json").read_bytes())
        envelope["arguments"] = {"case_id":self.case,"snapshot":reference("snapshots/model.json",encode(model())),
                                 "semantic_hash":self.submit_hash()}
        result = self.project.dispatch(ACTOR,SCOPES,envelope,jobs=self.jobs,execution=execution())
        self.assertEqual(result,self.project.dispatch(ACTOR,SCOPES,envelope,jobs=self.jobs,execution=execution()))
        cancel = json.loads((ROOT / "tests/fixtures/contracts/operation-job.cancel.json").read_bytes())
        cancel["idempotency_key"] = "00000000-0000-4000-8000-000000000091"
        cancel["arguments"]["job_id"] = result["result"]["job_id"]
        response = self.project.dispatch(ACTOR,SCOPES,cancel,jobs=self.jobs,execution=execution())
        self.assertTrue(response["result"]["accepted"])
        self.assertEqual(response,self.project.dispatch(ACTOR,SCOPES,cancel,jobs=self.jobs,execution=execution()))
        other = self.submit(key="other")
        cancel["arguments"]["job_id"] = other["id"]
        with self.assertRaisesRegex(PersistenceError,"idempotency_conflict"):
            self.project.dispatch(ACTOR,SCOPES,cancel,jobs=self.jobs,execution=execution())
        entity = deepcopy(model()["entities"][2])
        with self.assertRaisesRegex(PersistenceError,"idempotency_conflict"):
            self.project.apply(ACTOR,{"changes.apply"},model()["project_id"],0,"other",{"upsert":[entity],"delete":[]})

    def submit_hash(self):
        from fcst_app.persistence import semantic_hash
        return semantic_hash(model())

    def test_protocol_sequences_limits_and_checkpoint_binding(self):
        job = self.submit()
        with self.project.transaction():
            job["state"] = "running"
            self.jobs._put(job)
        handshake = json.loads((ROOT / "tests/fixtures/contracts/worker-handshake.json").read_bytes())
        handshake["job_id"] = job["id"]
        self.jobs.accept(job["id"],handshake,self.root)
        submit = {"contract_version":"1.0.0","job_id":job["id"],"sequence":1,"type":"submit",
                  "payload":{"case_id":self.case,"snapshot":reference("snapshots/model.json",encode(model())),
                             "semantic_hash":self.submit_hash()}}
        self.jobs.accept(job["id"],submit,self.root)
        checkpoint = json.loads((ROOT / "tests/fixtures/contracts/worker-checkpoint.json").read_bytes())
        checkpoint.update(job_id=job["id"],sequence=2)
        with self.assertRaises(ValueError):
            self.jobs.accept(job["id"],checkpoint,self.root)
        for sequence in range(2,MAX_EVENTS):
            progress = {"contract_version":"1.0.0","job_id":job["id"],"sequence":sequence,"type":"progress",
                        "payload":{"stage":"solve","fraction":.5}}
            self.jobs.accept(job["id"],progress,self.root)
        with self.assertRaises(ValueError):
            self.jobs.accept(job["id"],progress,self.root)
        progress["sequence"] = MAX_EVENTS
        with self.assertRaisesRegex(PersistenceError,"protocol_limit"):
            self.jobs.accept(job["id"],progress,self.root)
        page = self.jobs.query(ACTOR,SCOPES,job["id"],offset=4,limit=3)
        self.assertEqual([m["sequence"] for m in page["events"]],[4,5,6])
