# SPDX-License-Identifier: MIT OR Apache-2.0
"""Durable isolated jobs. Imported data cannot select commands or acquire authority."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import math
import os
import platform
from pathlib import Path
import queue
import sqlite3
import struct
import subprocess
import threading
import time
import uuid

from fcst_contracts import VERSION, ContractError, frame, loads, read, unframe, verify_artifact
from fcst_contracts.worker import Transcript
from .persistence import (Package, PersistenceError, atomic_file, encode, is_link,
                          publication_lock, read_bounded, reject, safe_path, semantic_hash, _fault)
from .process_limits import WorkerLimits

TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}
MAX_ARTIFACT = 64 * 1024 * 1024
MAX_EVENTS = 1024


def reference(path, data):
    return {"path": safe_path(path), "sha256": sha256(data).hexdigest(), "byte_length": len(data)}


def artifact(root, ref, limit=MAX_ARTIFACT):
    """No traversal, reparse points, hard links or out-of-root artifacts."""
    safe_path(ref["path"])
    root = Path(root).resolve()
    path = root
    for part in ref["path"].split("/"):
        path /= part
        if is_link(path):
            reject("artifact_root")
    if not path.resolve().is_relative_to(root) or path.stat().st_nlink != 1:
        reject("artifact_root")
    data = read_bounded(path, limit)
    verify_artifact(ref, data)
    return data


class JobStore:
    """Jobs share the project database, so attachment and revision checks are atomic.

    Connections belong to their calling thread. A separate client connection may
    cancel/query while the scheduler runs. Closing a client never cancels a job.
    """
    def __init__(self, project, *, clock=time.time, fault=None):
        self.project, self.db = project, project.db
        self.clock, self.fault = clock, fault
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, actor TEXT NOT NULL, request_key TEXT NOT NULL,
            request_hash TEXT NOT NULL, record BLOB NOT NULL, snapshot BLOB NOT NULL,
            UNIQUE(actor, request_key));
          CREATE TABLE IF NOT EXISTS job_bytes (
            job TEXT NOT NULL REFERENCES jobs(id), path TEXT NOT NULL, data BLOB NOT NULL,
            PRIMARY KEY(job,path));
          CREATE TABLE IF NOT EXISTS job_events (
            job TEXT NOT NULL REFERENCES jobs(id), sequence INTEGER NOT NULL, data BLOB NOT NULL,
            PRIMARY KEY(job,sequence));
          CREATE TABLE IF NOT EXISTS job_requests (
            actor TEXT NOT NULL, request_key TEXT NOT NULL, request_hash TEXT NOT NULL,
            response BLOB NOT NULL, PRIMARY KEY(actor,request_key));
        """)

    def _get(self, job_id):
        row = self.db.execute("SELECT record FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            reject("unknown_job")
        return loads(row[0])

    def _put(self, record):
        self.db.execute("UPDATE jobs SET record=? WHERE id=?", (encode(record), record["id"]))

    def _authority(self, actor, scopes, operation, record=None):
        self.project._authorize(actor, scopes, operation)
        if record is not None and actor != record["actor"]:
            reject("unauthorized")

    def submit(self, actor, scopes, key, case_id, *, expected_revision, execution,
               budget=None, seeds=None, parent=None, checkpoint=None):
        self._authority(actor, scopes, "job.submit")
        if not isinstance(key, str) or not key or len(key) > 128:
            reject("invalid_key")
        execution = deepcopy(execution)
        if (not isinstance(execution,dict)
                or set(execution) != {"profile", "features", "mode", "backend", "build_hash", "settings", "dependencies"}
                or any(not isinstance(execution[k],str) or not execution[k] or len(execution[k]) > 128
                       for k in ("profile","backend","build_hash"))
                or execution["mode"] not in {"fcst_native", "prototype_external", "reference_external", "fallback_external"}
                or not isinstance(execution["features"], list) or not isinstance(execution["settings"], dict)
                or not isinstance(execution["dependencies"], dict)
                or len(execution["build_hash"]) != 64
                or any(c not in "0123456789abcdef" for c in execution["build_hash"])):
            reject("execution_identity")
        budget = deepcopy(budget or {"wall_s": 60, "cancel_s": 2, "artifact_bytes": MAX_ARTIFACT})
        if not isinstance(budget,dict):
            reject("resource_budget")
        budget.setdefault("memory_mb",256)
        if (set(budget) != {"wall_s", "cancel_s", "artifact_bytes", "memory_mb"}
                or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in budget.values())
                or budget["wall_s"] > 86400 or budget["cancel_s"] > 60
                or not 32 <= budget["memory_mb"] <= 16384
                or budget["artifact_bytes"] > MAX_ARTIFACT):
            reject("resource_budget")
        seeds = deepcopy(seeds if seeds is not None else [0])
        if (not isinstance(seeds, list) or not 1 <= len(seeds) <= 64
                or any(type(v) not in (int,float) or not math.isfinite(v) or int(v) != v or not 0 <= v < 2**32 for v in seeds)):
            reject("seeds")
        seeds = [int(v) for v in seeds]
        request = dict(case_id=case_id, revision=expected_revision, execution=execution,
                       budget=budget, seeds=seeds, parent=parent, checkpoint=checkpoint)
        request_hash = sha256(encode(request)).hexdigest()
        if len(encode(request)) > 65536:
            reject("request_limit")
        with self.project.transaction():
            self._key_available(actor,key)
            prior = self.db.execute("SELECT request_hash,id FROM jobs WHERE actor=? AND request_key=?", (actor,key)).fetchone()
            if prior:
                if prior[0] != request_hash:
                    reject("idempotency_conflict")
                return self._get(prior[1])
            model = self.project.snapshot()
            if model["revision"] != expected_revision:
                reject("stale_revision")
            if not any(e["id"] == case_id and e["kind"] == "case" for e in model["entities"]):
                reject("case_reference")
            # Freeze the complete validated artifact closure, including v2 spatial envelopes.
            package = Package.create(model, self.project._artifacts(), **self.project._package_metadata())
            reserved = {"request.json","cancel.frame","snapshots/model.json","snapshots/manifest.json","resume/state"}
            if reserved & {path.casefold() for path in package.files}:
                reject("reserved_job_path")
            job_id = str(uuid.uuid4())
            record = {"id": job_id, "actor": actor, "project_id": model["project_id"],
                      "case_id": case_id, "revision": expected_revision, "semantic_hash": semantic_hash(model),
                      "execution": execution, "budget": budget, "seeds": seeds,
                      "parent": parent, "resume": checkpoint, "state": "queued", "sequence": -1,
                      "created": self.clock(), "cancel_requested": None, "cancel_acknowledged": False,
                      "result": None, "checkpoint": None, "reason": None}
            record["platform"] = {"os":platform.system(),"architecture":platform.machine(),"threads":1}
            if parent:
                previous = self._get(parent)
                self._authority(actor, scopes, "job.submit", previous)
                if previous["state"] not in TERMINAL:
                    reject("attempt_active")
                if checkpoint:
                    if (checkpoint != previous["checkpoint"] or execution != previous["execution"]
                            or seeds != previous["seeds"] or case_id != previous["case_id"]
                            or record["semantic_hash"] != previous["semantic_hash"]
                            or expected_revision != previous["revision"]):
                        reject("restart_incompatible")
            elif checkpoint:
                reject("restart_incompatible")
            self.db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?)",
                            (job_id, actor, key, request_hash, encode(record), encode(model)))
            for path, data in {**package.files, "snapshots/model.json": encode(model)}.items():
                self.db.execute("INSERT INTO job_bytes VALUES(?,?,?)", (job_id, "input/"+path, data))
            self.db.execute("INSERT INTO job_bytes VALUES(?,?,?)",(job_id,"input/snapshots/manifest.json",encode(package.manifest)))
            if checkpoint:
                data = self.bytes(parent, "checkpoint/"+checkpoint["state"]["path"])
                verify_artifact(checkpoint["state"], data)
                self.db.execute("INSERT INTO job_bytes VALUES(?,?,?)", (job_id, "resume/state", data))
            _fault(self.fault, "job_submitted")
        return record

    def _key_available(self, actor, key):
        if (any(r["actor"] == actor and r["key"] == key for r in self.project.state()["dedup"])
                or self.db.execute("SELECT 1 FROM job_requests WHERE actor=? AND request_key=?",(actor,key)).fetchone()):
            reject("idempotency_conflict")

    def bytes(self, job_id, path):
        row = self.db.execute("SELECT data FROM job_bytes WHERE job=? AND path=?", (job_id,path)).fetchone()
        if row is None:
            reject("missing_artifact")
        return row[0]

    def retry(self, actor, scopes, job_id, key, *, resume=False):
        previous = self._get(job_id)
        self._authority(actor,scopes,"job.submit",previous)
        if resume and previous["checkpoint"] is None:
            reject("resume_unsupported_use_fresh_attempt")
        return self.submit(actor,scopes,key,previous["case_id"],expected_revision=self.project.snapshot()["revision"],
                           execution=previous["execution"],budget=previous["budget"],seeds=previous["seeds"],parent=job_id,
                           checkpoint=previous["checkpoint"] if resume else None)

    def query(self, actor, scopes, job_id, *, offset=0, limit=64):
        record = self._get(job_id)
        self._authority(actor, scopes, "job.query", record)
        if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 64:
            reject("response_limit")
        events = self.db.execute("SELECT data FROM job_events WHERE job=? AND sequence>=? ORDER BY sequence LIMIT ?",
                                 (job_id,offset,limit)).fetchall()
        # Each event is <=64 KiB; callers page rather than collect unbounded logs.
        return {"job": record, "events": [loads(row[0]) for row in events]}

    def cancel(self, actor, scopes, job_id):
        with self.project.transaction():
            record = self._get(job_id)
            self._authority(actor, scopes, "job.cancel", record)
            if record["state"] == "queued":
                record.update(state="cancelled", reason="cancelled_before_start")
            elif record["state"] == "running":
                record.update(state="cancelling", cancel_requested=self.clock())
            self._put(record)
        return record

    def finish(self, job_id, outcome, reason=None):
        if outcome not in TERMINAL - {"succeeded"}:
            reject("invalid_transition")
        with self.project.transaction():
            record = self._get(job_id)
            if record["state"] not in TERMINAL:
                record.update(state=outcome, reason=reason)
                self._put(record)
        return record

    def accept(self, job_id, message, root):
        """Persist the message and its verified bytes in the same commit as state."""
        with self.project.transaction():
            record = self._get(job_id)
            if record["state"] not in {"running", "cancelling"}:
                reject("terminal_job")
            transcript = Transcript()
            # State and sequence are committed with each event. Reconstructing the
            # receiver from that durable cursor avoids quadratic progress replay.
            transcript.sequence = record["sequence"]
            transcript.job_id = job_id if record["sequence"] >= 0 else None
            transcript.snapshot_hash = record["semantic_hash"] if record["sequence"] >= 1 else None
            transcript.state = ("new" if record["sequence"] < 0 else "ready" if record["sequence"] == 0
                                else "cancelling" if record["cancel_acknowledged"] else "running")
            message = transcript.accept(message)
            if message["job_id"] != job_id or message["sequence"] >= MAX_EVENTS:
                reject("protocol_limit")
            kind, payload = message["type"], message["payload"]
            if kind == "handshake":
                caps = payload["capabilities"]
                if caps["execution_mode"] != "fcst_native" or "job.submit" not in caps["operations"]:
                    reject("capability")
            if kind == "submit":
                snapshot = self.bytes(job_id, "input/snapshots/model.json")
                if (payload != {"case_id": record["case_id"], "snapshot": reference("snapshots/model.json", snapshot),
                                "semantic_hash": record["semantic_hash"]}):
                    reject("snapshot_binding")
            if kind == "cancel":
                if record["cancel_requested"] is None:
                    reject("unsolicited_cancel")
                record["cancel_acknowledged"] = True
            if kind == "checkpoint":
                model = loads(self.db.execute("SELECT snapshot FROM jobs WHERE id=?",(job_id,)).fetchone()[0])
                case = next(e for e in model["entities"] if e["id"] == record["case_id"])
                if (payload["snapshot_hash"] != record["semantic_hash"]
                        or payload["build_hash"] != record["execution"]["build_hash"]
                        or payload["case_id"] != record["case_id"]
                        or payload["sequence"] != message["sequence"]):
                    reject("restart_incompatible")
                if (not case["start"]["value"] <= payload["time"]["value"] <= case["end"]["value"]
                        or record["checkpoint"] and payload["time"]["value"] < record["checkpoint"]["time"]["value"]):
                    reject("restart_incompatible")
                data = artifact(root, payload["state"], int(record["budget"]["artifact_bytes"]))
                self.db.execute("INSERT OR REPLACE INTO job_bytes VALUES(?,?,?)",
                                (job_id,"checkpoint/"+payload["state"]["path"],data))
                self._output_budget(record)
                record["checkpoint"] = payload
            if kind == "terminal":
                outcome = payload["outcome"]
                if outcome == "cancelled" and not record["cancel_acknowledged"]:
                    reject("cancel_unacknowledged")
                if outcome == "succeeded":
                    self._publish(record, root, payload["result"])
                record.update(state=outcome, reason=None)
            raw = encode(message)
            if len(raw) > 65536:
                reject("protocol_limit")
            self.db.execute("INSERT INTO job_events VALUES(?,?,?)", (job_id,message["sequence"],raw))
            record["sequence"] = message["sequence"]
            self._put(record)
            _fault(self.fault, "job_event")
        return record

    def _publish(self, record, root, ref):
        manifest_bytes = artifact(root, ref, 1048576)
        manifest = read("result", loads(manifest_bytes))
        for key in ("project_id", "case_id", "revision", "semantic_hash"):
            if manifest[key] != record[key]:
                reject("result_binding")
        if (manifest["build_hash"] != record["execution"]["build_hash"]
                or manifest["execution_mode"] != record["execution"]["mode"]
                or manifest["adapter"] != record["execution"]["backend"] or manifest["outcome"] != "succeeded"):
            reject("result_binding")
        data = artifact(root, manifest["data"], int(record["budget"]["artifact_bytes"]))
        from .arrays import validate_arrays
        metadata = validate_arrays(data)
        if (metadata["role"] != "result" or metadata["semantic_hash"] != record["semantic_hash"]
                or any(metadata[k] != manifest[k] for k in ("node_ids", "time_count"))
                or metadata["quantities"] != sorted(manifest["quantities"])):
            reject("result_binding")
        model = loads(self.db.execute("SELECT snapshot FROM jobs WHERE id=?", (record["id"],)).fetchone()[0])
        nodes = {e["id"] for e in model["entities"] if e["kind"] == "node"}
        if not set(manifest["node_ids"]) <= nodes:
            reject("result_binding")
        for path, content in (("result/manifest", manifest_bytes), ("result/data", data)):
            self.db.execute("INSERT INTO job_bytes VALUES(?,?,?)", (record["id"],path,content))
        record["result"] = {"manifest": ref, "id": manifest["id"]}
        self._output_budget(record)
        _fault(self.fault, "result_staged")

    def _output_budget(self, record):
        total = self.db.execute("SELECT coalesce(sum(length(data)),0) FROM job_bytes WHERE job=? AND path NOT LIKE 'input/%'",
                                (record["id"],)).fetchone()[0]
        if total > record["budget"]["artifact_bytes"]:
            reject("output_budget")

    def result(self, actor, scopes, job_id, *, historical=False):
        record = self._get(job_id)
        self._authority(actor, scopes, "result.query", record)
        if record["state"] != "succeeded":
            reject("result_unavailable")
        raw = self.bytes(job_id,"result/manifest")
        verify_artifact(record["result"]["manifest"],raw)
        manifest = read("result",loads(raw))
        verify_artifact(manifest["data"],self.bytes(job_id,"result/data"))
        model = self.project.snapshot()
        if not historical and (model["revision"] != record["revision"] or semantic_hash(model) != record["semantic_hash"]):
            reject("stale_result")
        return {"job": record, "manifest": manifest,
                "snapshot": loads(self.db.execute("SELECT snapshot FROM jobs WHERE id=?", (job_id,)).fetchone()[0])}

    def attach(self, actor, scopes, job_id):
        with self.project.transaction():
            result = self.result(actor, scopes, job_id)
            self._authority(actor, scopes, "result.attach", result["job"])
            state = self.project.state()
            result_id = result["manifest"]["id"]
            if any(d["id"] == result_id for d in state["derived"]):
                if any(d["id"] == result_id and d["kind"] == "solve" and d["semantic_hash"] == result["job"]["semantic_hash"]
                       for d in state["derived"]) and any(a[0] == result_id and a[2] == "results/"+job_id+"/result.json"
                                                         for a in self.project._artifacts()):
                    return result_id
                reject("duplicate_id")
            if any(e["id"] == result_id for e in state["model"]["entities"]):
                reject("duplicate_id")
            state["derived"].append({"id": result_id, "kind": "solve",
                                     "dependencies": [e["id"] for e in state["model"]["entities"]], "revision": state["model"]["revision"],
                                     "semantic_hash": result["job"]["semantic_hash"], "stale": False})
            data = self.bytes(job_id,"result/data")
            manifest = deepcopy(result["manifest"])
            prefix = "results/"+job_id
            manifest["data"] = reference(prefix+"/arrays.h5",data)
            data_id = str(uuid.uuid5(uuid.UUID(result_id),"data"))
            additions = [(data_id,"result",prefix+"/arrays.h5",data,[]),
                         (result_id,"result",prefix+"/result.json",encode(manifest),[data_id]),
                         (str(uuid.uuid5(uuid.UUID(result_id),"provenance")),"evidence",prefix+"/provenance.json",
                          encode({k:v for k,v in result["job"].items() if k != "actor"}),[result_id])]
            package = Package.create(state["model"],[*self.project._artifacts(),*additions],state=state,
                                     **self.project._package_metadata())
            for artifact_id, role, path, content, dependencies in additions:
                self.db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?)",(artifact_id,role,path,encode(dependencies),content))
            self.db.execute("UPDATE package_manifest SET data=? WHERE id=1",(encode(package.manifest),))
            self.project._write(state)
        return result_id

    def dispatch(self, actor, scopes, envelope, *, execution):
        """Frozen application operations with server-owned execution configuration."""
        request = read("operation",envelope)
        operation, args = request["operation"], request["arguments"]
        self._authority(actor,scopes,operation)
        if request["project_id"] != self.project.snapshot()["project_id"]:
            reject("wrong_project")
        request_hash = sha256(encode(request)).hexdigest()
        if operation == "job.cancel":
            # Cancellation and its key reservation share a transaction. A retry
            # returns the original response even after service restart.
            with self.project.transaction():
                prior = self.db.execute("SELECT request_hash,response FROM job_requests WHERE actor=? AND request_key=?",
                                        (actor,request["idempotency_key"])).fetchone()
                if prior:
                    if prior[0] != request_hash:
                        reject("idempotency_conflict")
                    return read("response",loads(prior[1]))
                self._key_available(actor,request["idempotency_key"])
                if self.db.execute("SELECT 1 FROM jobs WHERE actor=? AND request_key=?",(actor,request["idempotency_key"])).fetchone():
                    reject("idempotency_conflict")
                record = self._get(args["job_id"])
                self._authority(actor,scopes,operation,record)
                if record["state"] == "queued":
                    record.update(state="cancelled",reason="cancelled_before_start")
                elif record["state"] == "running":
                    record.update(state="cancelling",cancel_requested=self.clock())
                self._put(record)
                response = read("response",{"contract_version":VERSION,"operation":operation,
                                             "result":{"job_id":args["job_id"],"accepted":True}})
                self.db.execute("INSERT INTO job_requests VALUES(?,?,?,?)",(actor,request["idempotency_key"],request_hash,encode(response)))
                return response
        if operation == "job.submit":
            prior = self.db.execute("SELECT id,snapshot FROM jobs WHERE actor=? AND request_key=?",
                                    (actor,request["idempotency_key"])).fetchone()
            data = prior[1] if prior else encode(self.project.snapshot())
            if args["snapshot"] != reference("snapshots/model.json",data) or args["semantic_hash"] != semantic_hash(loads(data)):
                reject("snapshot_binding")
            job = self.submit(actor,scopes,request["idempotency_key"],args["case_id"],
                              expected_revision=request["expected_revision"],execution=execution)
            result = {"job_id":job["id"]}
        elif operation == "result.query":
            candidates = [loads(row[0]) for row in self.db.execute("SELECT record FROM jobs WHERE actor=?",(actor,))]
            record = next((r for r in candidates if r["result"] and r["result"]["id"] == args["result_id"]),None)
            if record is None:
                reject("result_unavailable")
            self.result(actor,scopes,record["id"])
            from .arrays import read_arrays, write_arrays
            arrays = read_arrays(self.bytes(record["id"],"result/data"))["arrays"]
            nodes = [str(uuid.UUID(bytes=bytes(row))) for row in arrays["index/node_uuid"]]
            if args["quantity"] not in arrays or any(node not in nodes for node in args["entity_ids"]):
                reject("result_query")
            offset, limit = int(args["offset"]),int(args["limit"])
            count = min(limit,len(arrays["time"])-offset)
            if count <= 0:
                reject("result_query")
            indices = [nodes.index(node) for node in args["entity_ids"]]
            content = write_arrays("result",record["semantic_hash"],{
                "index/node_uuid":arrays["index/node_uuid"][indices],"time":arrays["time"][offset:offset+count],
                args["quantity"]:arrays[args["quantity"]][offset:offset+count][:,indices]})
            path = "queries/"+str(uuid.uuid4())+".h5"
            with self.project.transaction():
                # Recheck the live revision inside the publication transaction.
                self.result(actor,scopes,record["id"])
                self.db.execute("INSERT INTO job_bytes VALUES(?,?,?)",(record["id"],path,content))
                self._output_budget(record)
            result = {"artifact":reference(path,content),"offset":offset,"count":count}
        else:
            reject("unsupported_operation")
        return read("response",{"contract_version":VERSION,"operation":operation,"result":result})


class Scheduler:
    """One leased scheduler per project; parallel clients use independent stores.

    A backend registry is trusted application configuration. Commands never come
    from a model, job request, checkpoint, or worker message.
    """
    def __init__(self, jobs, root, backends):
        self.jobs, self.root, self.backends = jobs, Path(root).resolve(), deepcopy(backends)
        self.root.mkdir(parents=True, exist_ok=True)
        if is_link(root):
            reject("artifact_root")
        self.lease = publication_lock(jobs.project.path.with_name(jobs.project.path.name+".scheduler"))
        self.active = False

    def __enter__(self):
        self.lease.__enter__()
        try:
            with self.jobs.project.transaction():
                for row in self.jobs.db.execute("SELECT record FROM jobs").fetchall():
                    record = loads(row[0])
                    if record["state"] in {"running", "cancelling"}:
                        record.update(state="interrupted", reason="service_restart")
                        self.jobs._put(record)
        except BaseException:
            self.lease.__exit__(None,None,None)
            raise
        self.active = True
        return self

    def __exit__(self, *args):
        self.active = False
        self.lease.__exit__(*args)

    def run_next(self):
        if not self.active:
            reject("scheduler_lease_required")
        with self.jobs.project.transaction():
            queued = [loads(row[0]) for row in self.jobs.db.execute("SELECT record FROM jobs ORDER BY rowid")]
            record = next((r for r in queued if r["state"] == "queued"), None)
            if record is None:
                return None
            backend = self.backends.get(record["execution"]["backend"])
            if backend is None or backend["execution"] != record["execution"]:
                reject("backend_unavailable")
            if record["resume"] and not backend.get("resume_supported",False):
                reject("resume_unsupported_use_fresh_attempt")
            if "identity_file" in backend and sha256(Path(backend["identity_file"]).read_bytes()).hexdigest() != record["execution"]["build_hash"]:
                reject("backend_build_changed")
            record.update(state="running", started=self.jobs.clock())
            self.jobs._put(record)
        try:
            return self._run(record, backend)
        except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError):
            return self.jobs.finish(record["id"], "failed", "worker_or_artifact_invalid")

    def _run(self, record, backend):
        job_id = record["id"]
        directory = self.root / job_id
        # Attempts always get a new directory. Leftovers cannot masquerade as output.
        directory.mkdir(exist_ok=False)
        frozen = self.jobs.bytes(job_id,"input/snapshots/model.json")
        frozen_model = read("model",loads(frozen))
        if (semantic_hash(frozen_model) != record["semantic_hash"] or frozen_model["revision"] != record["revision"]
                or frozen_model["project_id"] != record["project_id"]
                or frozen != self.jobs.db.execute("SELECT snapshot FROM jobs WHERE id=?",(job_id,)).fetchone()[0]):
            reject("snapshot_binding")
        manifest = loads(self.jobs.bytes(job_id,"input/snapshots/manifest.json"))
        Package(manifest,{a["artifact"]["path"]:self.jobs.bytes(job_id,"input/"+a["artifact"]["path"])
                          for a in manifest["artifacts"]})
        for path, data in self.jobs.db.execute("SELECT path,data FROM job_bytes WHERE job=? AND path LIKE 'input/%'", (job_id,)):
            target = directory / path.removeprefix("input/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        request = {"job": record, "snapshot": reference("snapshots/model.json", self.jobs.bytes(job_id,"input/snapshots/model.json"))}
        if record["resume"]:
            (directory / "resume").mkdir()
            (directory / "resume/state").write_bytes(self.jobs.bytes(job_id,"resume/state"))
        atomic_file(directory / "request.json", encode(request))
        events = queue.Queue(maxsize=8)  # Backpressure includes pipe buffers and this bounded queue.
        stop = threading.Event()
        def put(item):
            while not stop.is_set():
                try:
                    events.put(item, timeout=.05)
                    return
                except queue.Full:
                    pass
        def reader(stream):
            try:
                def exact(size, allow_eof=False):
                    result = b""
                    while len(result) < size:
                        part = stream.read(size-len(result))
                        if not part:
                            if allow_eof and not result:
                                raise EOFError
                            raise ValueError("truncated_frame")
                        result += part
                    return result
                while not stop.is_set():
                    header = exact(4,allow_eof=True)
                    size = struct.unpack("<I", header)[0]
                    if not 1 <= size <= 65536:
                        raise ValueError
                    put(("message", unframe(header+exact(size))))
            except EOFError:
                put(("eof", None))
            except (OSError, ValueError):
                put(("invalid",None))
        # No inherited vendor search paths, PYTHONPATH, secrets, or executable model inputs.
        env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "TEMP", "TMP") if k in os.environ}
        env.update(PATH=str(Path(backend["command"][0]).resolve().parent), OMP_NUM_THREADS="1",
                   OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        process = subprocess.Popen([*backend["command"], str(directory), job_id], cwd=directory,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
                                   creationflags=0x4 if os.name == "nt" else 0)
        try:
            containment = WorkerLimits(process,record["budget"]["memory_mb"])
        except BaseException:
            process.kill()
            process.wait(timeout=5)
            process.stdin.close()
            process.stdout.close()
            raise
        thread = threading.Thread(target=reader, args=(process.stdout,), daemon=True)
        thread.start()
        started = time.monotonic()
        cancel_sent = False
        terminal = None
        try:
            while True:
                live = self.jobs._get(job_id)
                elapsed = time.monotonic()-started
                if live["state"] == "cancelling" and not cancel_sent:
                    # Separate bounded request channel. The worker serializes its ack
                    # with progress; only the ack enters the ordered transcript.
                    atomic_file(directory / "cancel.frame", frame({"contract_version": VERSION, "type": "cancel",
                        "job_id": job_id, "sequence": int(live["sequence"])+1, "payload": {}}))
                    cancel_sent = True
                if live["cancel_requested"] is not None and self.jobs.clock()-live["cancel_requested"] >= live["budget"]["cancel_s"]:
                    return self.jobs.finish(job_id,"cancelled","cancel_deadline_terminated")
                if elapsed >= record["budget"]["wall_s"]:
                    return self.jobs.finish(job_id,"failed","worker_timeout")
                try:
                    kind, message = events.get(timeout=.02)
                except queue.Empty:
                    continue
                if kind == "eof":
                    if terminal is None:
                        return self.jobs.finish(job_id,"interrupted","worker_disconnected")
                    if process.wait(timeout=2) != 0:
                        return self.jobs.finish(job_id,"failed","worker_exit")
                    return self.jobs.accept(job_id,terminal,directory)
                if kind == "invalid":
                    return self.jobs.finish(job_id,"failed","invalid_frame")
                if terminal is not None:
                    return self.jobs.finish(job_id,"failed","message_after_terminal")
                if message["type"] == "checkpoint" and not backend.get("resume_supported",False):
                    return self.jobs.finish(job_id,"failed","checkpoint_unsupported")
                if message["type"] == "terminal":
                    terminal = message
                    continue  # Publication requires clean EOF and exit, not just a success frame.
                self.jobs.accept(job_id,message,directory)
                if message["type"] == "handshake":
                    submit = {"contract_version": VERSION,"type":"submit","job_id":job_id,"sequence":1,
                              "payload":{"case_id":record["case_id"],"snapshot":request["snapshot"],
                                         "semantic_hash":record["semantic_hash"]}}
                    self.jobs.accept(job_id,submit,directory)
                    process.stdin.write(frame(submit))
                    process.stdin.flush()
        finally:
            stop.set()
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            containment.close()
            thread.join(timeout=5)
            process.stdin.close()
            process.stdout.close()


def native_backend(executable):
    """Pin the executable's bytes and capabilities, not a caller-supplied build label."""
    executable = Path(executable).resolve()
    build_hash = sha256(executable.read_bytes()).hexdigest()
    env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR") if k in os.environ}
    env["PATH"] = str(executable.parent)
    process = subprocess.run([str(executable), "--build-info"], capture_output=True, env=env, timeout=10)
    info = loads(process.stdout)
    if process.returncode or info["engine"] != "fcst_native" or info["protocol_version"] != 1:
        reject("capability")
    return {"command": [str(executable), "--worker"],
            "identity_file":str(executable),"resume_supported":False,
            "execution": {"profile": "native", "features": [], "mode": "fcst_native", "backend": "native",
                          "build_hash": build_hash, "settings": {}, "dependencies": {"source_revision":info["source_revision"]}}}
