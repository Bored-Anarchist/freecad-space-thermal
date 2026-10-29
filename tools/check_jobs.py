# SPDX-License-Identifier: MIT OR Apache-2.0
"""WP-06 unattended lifecycle acceptance; publish only bounded case verdicts."""
from __future__ import annotations
import argparse
from copy import deepcopy
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "tests")]
from test_jobs import JobTests, ACTOR, SCOPES, PEER, execution, model
from fcst_app.arrays import write_arrays
from fcst_app.jobs import JobStore, Scheduler, native_backend, reference
from fcst_app.persistence import Package, PersistenceError, encode, semantic_hash
from fcst_app.store import ProjectStore
from fcst_tools.gate import evaluate

WORKER = None


def populate(jobs, job_id):
    arrays = {"index/node_uuid":[list(uuid.UUID(e["id"]).bytes) for e in model()["entities"] if e["kind"] == "node"],
              "time":[0.,1.],"temperature":[[293.15,300.],[294.,300.]],
              "power":[[1.,-1.],[.5,-.5]],"residual":[[0.,0.],[0.,0.]]}
    data = write_arrays("result",semantic_hash(model()),arrays)
    manifest = json.loads((ROOT / "tests/fixtures/contracts/result.json").read_bytes())
    for path, content in (("input/fixture/result.h5",data),("input/fixture/result.json",encode(manifest))):
        jobs.db.execute("INSERT INTO job_bytes VALUES(?,?,?)",(job_id,path,content))


class JobAcceptance(JobTests):
    # Do not silently inherit/recount standard-library cases as extra acceptance.
    def test_success_publication_attachment_and_historical_snapshot(self):
        job = self.submit("success")
        populate(self.jobs,job["id"])
        with self.scheduler("success") as scheduler:
            result = scheduler.run_next()
        self.assertEqual(result["state"],"succeeded")
        self.assertEqual(self.jobs.attach(ACTOR,SCOPES,job["id"]),job["id"])
        self.assertEqual(self.jobs.attach(ACTOR,SCOPES,job["id"]),job["id"])
        package = self.project.export_package()
        self.assertIn("results/"+job["id"]+"/arrays.h5",package.files)
        with ProjectStore.create(self.root / "portable.db",package=package) as portable:
            self.assertEqual(portable.derived(job["id"])["semantic_hash"],job["semantic_hash"])
        request = json.loads((ROOT / "tests/fixtures/contracts/operation-result.query.json").read_bytes())
        request["arguments"].update(result_id=job["id"],offset=0,limit=1)
        response = self.jobs.dispatch(ACTOR,SCOPES,request,execution=execution("success"))
        ref = response["result"]["artifact"]
        from fcst_contracts import verify_artifact
        verify_artifact(ref,self.jobs.bytes(job["id"],ref["path"]))
        self.assertEqual(response["result"]["count"],1)
        entity = deepcopy(self.project.snapshot()["entities"][2])
        entity["temperature"]["value"] += 1
        self.project.apply(ACTOR,{"changes.apply"},job["project_id"],0,"edit",{"upsert":[entity],"delete":[]})
        with self.assertRaisesRegex(PersistenceError,"stale_result"):
            self.jobs.attach(ACTOR,SCOPES,job["id"])
        with self.assertRaisesRegex(PersistenceError,"stale_result"):
            self.project.derived(job["id"])
        self.assertEqual(self.jobs.result(ACTOR,SCOPES,job["id"],historical=True)["snapshot"]["revision"],0)
        self.project.apply(ACTOR,{"changes.undo"},job["project_id"],1,"undo",{"revision":1},operation="changes.undo")
        self.assertEqual(semantic_hash(self.project.snapshot()),job["semantic_hash"])
        with self.assertRaisesRegex(PersistenceError,"stale_result"):
            self.jobs.attach(ACTOR,SCOPES,job["id"])

    def test_success_can_win_a_requested_cancellation_race(self):
        job = self.submit("race")
        populate(self.jobs,job["id"])
        errors = []
        def cancel():
            with ProjectStore(self.project.path) as project:
                jobs = JobStore(project)
                deadline = time.monotonic()+4
                while time.monotonic() < deadline:
                    if jobs._get(job["id"])["sequence"] >= 2:
                        jobs.cancel(ACTOR,SCOPES,job["id"])
                        return
                    time.sleep(.01)
                errors.append("progress_missing")
        client = threading.Thread(target=cancel)
        client.start()
        with self.scheduler("race") as scheduler:
            result = scheduler.run_next()
        client.join(timeout=5)
        self.assertFalse(errors)
        self.assertEqual(result["state"],"succeeded")
        self.assertIsNotNone(result["cancel_requested"])

    def test_partial_mismatched_late_and_badexit_results_are_never_published(self):
        for scenario in ("partial","mismatch","late","trailing","badexit"):
            job = self.submit(scenario,key=scenario)
            populate(self.jobs,job["id"])
            with self.scheduler(scenario) as scheduler:
                result = scheduler.run_next()
            self.assertEqual(result["state"],"failed",scenario)
            self.assertIsNone(result["result"])
            self.assertEqual(self.jobs.db.execute("SELECT count(*) FROM job_bytes WHERE job=? AND path LIKE 'result/%'",
                                                 (job["id"],)).fetchone()[0],0)

    def test_checkpoint_restart_preserves_state_and_rejects_changed_identity(self):
        job = self.submit("checkpoint")
        def cancel():
            with ProjectStore(self.project.path) as project:
                jobs = JobStore(project)
                deadline = time.monotonic()+5
                while time.monotonic() < deadline:
                    if jobs._get(job["id"])["checkpoint"]:
                        jobs.cancel(ACTOR,SCOPES,job["id"])
                        return
                    time.sleep(.01)
        client = threading.Thread(target=cancel)
        client.start()
        with self.scheduler("checkpoint") as scheduler:
            previous = scheduler.run_next()
            client.join(timeout=5)
            self.assertEqual(previous["state"],"cancelled")
            checkpoint = previous["checkpoint"]
            self.assertIsNotNone(checkpoint)
            for change in ({"seeds":[8]}, {"execution":execution("success")},
                           {"checkpoint":{**checkpoint,"build_hash":"0"*64}}):
                options = dict(execution=execution("checkpoint"),seeds=[0],checkpoint=checkpoint)
                options.update(change)
                with self.assertRaisesRegex(PersistenceError,"restart_incompatible"):
                    self.jobs.submit(ACTOR,SCOPES,"bad",self.case,expected_revision=0,parent=job["id"],**options)
            resumed = self.submit("checkpoint",key="resume",parent=job["id"],checkpoint=checkpoint)
            populate(self.jobs,resumed["id"])
            self.assertEqual(scheduler.run_next()["state"],"succeeded")
            self.assertEqual(self.jobs._get(job["id"])["state"],"cancelled")

    def test_real_process_kill_points_preserve_job_truth(self):
        for phase,expected in (("job_submitted",None),("service_active","interrupted"),("result_staged","interrupted"),
                               ("terminal_commit","interrupted"),("committed","succeeded")):
            directory = self.root / phase
            directory.mkdir()
            process = subprocess.run([sys.executable,str(Path(__file__).resolve()),"--kill",phase,"--scratch",str(directory)],
                                     capture_output=True,timeout=20)
            self.assertEqual(process.returncode,73,phase)
            with ProjectStore(directory / "project.db") as project:
                jobs = JobStore(project)
                with Scheduler(jobs,directory / "runs",{}) as scheduler:
                    rows = jobs.db.execute("SELECT id FROM jobs").fetchall()
                    if expected is None:
                        self.assertEqual(rows,[])
                        continue
                    record = jobs._get(rows[0][0])
                    self.assertEqual(record["state"],expected)
                    if expected == "succeeded":
                        self.assertEqual(jobs.result(ACTOR,SCOPES,record["id"])["manifest"]["outcome"],"succeeded")
                    else:
                        self.assertIsNone(record["result"])
                if phase == "service_active":
                    import ctypes
                    from ctypes import wintypes
                    pid = int(next((directory / "runs").glob("*/worker.pid")).read_text())
                    api = ctypes.WinDLL("kernel32",use_last_error=True)
                    api.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
                    api.OpenProcess.restype = wintypes.HANDLE
                    api.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
                    api.CloseHandle.argtypes = [wintypes.HANDLE]
                    handle = api.OpenProcess(0x100000,False,pid)
                    if handle:
                        try:
                            self.assertEqual(api.WaitForSingleObject(handle,2000),0)
                        finally:
                            api.CloseHandle(handle)
                self.assertEqual(project.snapshot(),model())

    def test_native_worker_is_engine_only_and_reports_unsupported_physics(self):
        backend = native_backend(WORKER)
        job = self.jobs.submit(ACTOR,SCOPES,"native",self.case,expected_revision=0,execution=backend["execution"])
        with Scheduler(self.jobs,self.root / "native",{"native":backend}) as scheduler:
            result = scheduler.run_next()
        self.assertEqual(result["state"],"failed")
        events = self.jobs.query(ACTOR,SCOPES,job["id"])["events"]
        self.assertEqual([m["type"] for m in events],["handshake","submit","diagnostic","terminal"])
        self.assertEqual(events[2]["payload"]["code"],"not_implemented")
        self.assertIsNone(result["result"])

    def test_local_cli_submit_poll_run_cancel_and_resume_diagnostic(self):
        case = self.case
        def cli(*args,expected=0):
            process = subprocess.run([sys.executable,"-I","-m","fcst_cli",*args],capture_output=True,timeout=20)
            self.assertEqual(process.returncode,expected)
            return json.loads(process.stdout)
        database = str(self.project.path)
        job = cli("job-submit",database,"--worker",str(WORKER),"--case",case,"--key","cli","--expected-revision","0")
        self.assertEqual(cli("job-status",database,"--job",job["id"])["job"]["state"],"queued")
        self.assertEqual(cli("job-run",database,"--worker",str(WORKER))["state"],"failed")
        self.assertEqual(cli("job-retry",database,"--job",job["id"],"--key","resume","--resume",expected=2)["code"],
                         "resume_unsupported_use_fresh_attempt")
        child = cli("job-retry",database,"--job",job["id"],"--key","fresh")
        self.assertEqual(cli("job-cancel",database,"--job",child["id"])["state"],"cancelled")


ACCEPTANCE = [name for name in JobAcceptance.__dict__ if name.startswith("test_")]


def kill(phase, directory):
    with ProjectStore.create(directory / "project.db",model()) as project:
        jobs = JobStore(project)
        def fault(point):
            if (phase == "job_submitted" and point == phase
                    or phase == "result_staged" and point == phase
                    or phase == "terminal_commit" and point == "job_event" and
                       jobs.db.execute("SELECT count(*) FROM job_bytes WHERE path='result/manifest'").fetchone()[0]
                    or phase == "service_active" and point == "job_event" and jobs._get(job["id"])["sequence"] >= 2):
                os._exit(73)
        jobs.fault = fault
        case = next(e["id"] for e in model()["entities"] if e["kind"] == "case")
        scenario = "hang" if phase == "service_active" else "success"
        job = jobs.submit(ACTOR,SCOPES,"kill",case,expected_revision=0,execution=execution(scenario))
        populate(jobs,job["id"])
        with Scheduler(jobs,directory / "runs",{"fixture":{"execution":execution(scenario),
                       "command":[sys.executable,str(PEER),scenario]}}) as scheduler:
            scheduler.run_next()
            if phase == "committed":
                os._exit(73)
    raise RuntimeError("kill_point_not_observed")


def main():
    global WORKER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker",type=Path)
    parser.add_argument("--report",type=Path,default=ROOT / ".local/jobs.json")
    parser.add_argument("--kill")
    parser.add_argument("--scratch",type=Path)
    args = parser.parse_args()
    if args.kill:
        kill(args.kill,args.scratch)
        return 1
    if args.worker is None:
        parser.error("--worker is required")
    WORKER = args.worker.resolve()
    records = []
    for name in sorted(ACCEPTANCE):
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream).run(unittest.TestSuite([JobAcceptance(name)]))
        raw = ROOT / ".local/job-logs" / (name+".log")
        raw.parent.mkdir(parents=True,exist_ok=True)
        raw.write_text(stream.getvalue(),encoding="utf-8")
        records.append({"id":name,"status":"passed" if result.wasSuccessful() and not result.skipped else "failed"})
    report = {"work_package":"WP-06","scope":"Isolated job lifecycle; synthetic peers do not qualify thermal physics",
              "native_build_sha256":sha256(WORKER.read_bytes()).hexdigest(),
              "source_artifacts":{name:sha256((ROOT / name).read_bytes()).hexdigest() for name in
                 ("python/fcst_app/jobs.py","python/fcst_app/process_limits.py","engine/src/contracts.cpp",
                  "engine/worker/main.cpp","tests/test_jobs.py","tests/fixtures/job_worker.py","tools/check_jobs.py")},
              "gate":evaluate(json.loads((ROOT / "ci/coverage.json").read_bytes())["job_cases"],records),"cases":records}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_bytes(encode(report)+b"\n")
    print(json.dumps(report["gate"]))
    return 0 if report["gate"]["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
