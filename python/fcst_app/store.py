# SPDX-License-Identifier: MIT OR Apache-2.0
"""Durable project transactions. SQLite is operational; audit JSON is portable."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import hmac
from pathlib import Path
import sqlite3
import time
import uuid

from fcst_contracts import VERSION, ContractError, loads, read, normalize, dependency_order
from .persistence import (Package, PersistenceError, encode, reject, semantic_hash,
                          save_package, atomic_file, _fault)

MAX_STATE_BYTES = 1048576  # No silent audit/dedup pruning; explicit capacity failure.
DERIVED_KINDS = {"geometry", "mesh", "optics", "environment", "solve", "comparison", "acceptance"}


def initial_state(model):
    return {"storage_version": 1, "model_artifact_id": str(uuid.uuid5(uuid.UUID(model["project_id"]), "fcst:model")),
            "model": read("model", model), "history": [],
            "dedup": [], "previews": [], "derived": [],
            "host": {"status": "unlinked", "dirty": True}}


def validate_state(state, model):
    try:
        _validate_state(state, model)
    except (KeyError, TypeError, IndexError, AttributeError):
        reject("invalid_journal")


def _validate_state(state, model):
    if (not isinstance(state, dict) or set(state) != set(initial_state(model))
            or state["storage_version"] != 1 or encode(state["model"]) != encode(model)):
        reject("invalid_journal")
    for key in ("history", "dedup", "previews", "derived"):
        if not isinstance(state[key], list):
            reject("invalid_journal")
    # Check history links and inverse snapshots, including revisions after undo.
    revision = None
    previous_hash = None
    for record in state["history"]:
        if set(record) != {"revision", "before", "after_hash", "actor", "operation", "inverse"}:
            reject("invalid_journal")
        before = read("model", record["before"])
        if (before["project_id"] != model["project_id"] or record["revision"] != before["revision"] + 1
                or revision is not None and (before["revision"] != revision or semantic_hash(before) != previous_hash)):
            reject("invalid_journal")
        inverse = record["inverse"]
        before_entities = {e["id"]: e for e in before["entities"]}
        if (not isinstance(inverse, dict) or set(inverse) != {"restore", "expected"}
                or not isinstance(inverse["restore"], dict) or not isinstance(inverse["expected"], dict)
                or set(inverse["restore"]) != set(inverse["expected"])
                or any(value != before_entities.get(key) for key, value in inverse["restore"].items())):
            reject("invalid_journal")
        revision = record["revision"]
        previous_hash = record["after_hash"]
    if revision is not None and (revision != model["revision"] or state["history"][-1]["after_hash"] != semantic_hash(model)):
        reject("invalid_journal")
    for index, record in enumerate(state["history"]):
        after = state["history"][index + 1]["before"] if index + 1 < len(state["history"]) else model
        before_entities = {e["id"]: e for e in record["before"]["entities"]}
        after_entities = {e["id"]: e for e in after["entities"]}
        changed = {key for key in before_entities.keys() | after_entities.keys() if before_entities.get(key) != after_entities.get(key)}
        if (record["after_hash"] != semantic_hash(after) or set(record["inverse"]["expected"]) != changed
                or any(value != after_entities.get(key) for key, value in record["inverse"]["expected"].items())):
            reject("invalid_journal")
    seen = set()
    for record in state["dedup"]:
        if set(record) != {"actor", "key", "payload_hash", "outcome"} or (record["actor"], record["key"]) in seen:
            reject("invalid_journal")
        seen.add((record["actor"], record["key"]))
        if (not isinstance(record["outcome"], dict) or record["outcome"].get("revision", -1) > model["revision"]
                or not isinstance(record["payload_hash"], str) or len(record["payload_hash"]) != 64
                or not any(h["revision"] == record["outcome"].get("revision") and h["after_hash"] == record["outcome"].get("semantic_hash")
                           for h in state["history"])):
            reject("invalid_journal")
    if not isinstance(state["host"], dict) or state["host"].get("status") not in {
            "unlinked", "dirty", "prepared", "host_written", "package_written", "clean"}:
        reject("invalid_journal")
    roots = {e["id"] for e in model["entities"]}
    roots.update(e["id"] for h in state["history"] for e in h["before"]["entities"])
    graph = {key: set() for key in roots}
    for item in state["derived"]:
        if (not isinstance(item, dict) or set(item) != {"id", "kind", "dependencies", "revision", "semantic_hash", "stale"}
                or item["id"] in graph or item["kind"] not in DERIVED_KINDS or not isinstance(item["dependencies"], list)
                or not isinstance(item["stale"], bool) or item["revision"] > model["revision"]):
            reject("invalid_journal")
        graph[item["id"]] = set(item["dependencies"])
    dependency_order(graph, "artifact")
    for plan in state["previews"]:
        if not isinstance(plan, dict) or set(plan) != {"id", "actor", "project_id", "base_revision", "payload", "operation", "scopes", "expires", "hash"}:
            reject("invalid_journal")
    if len(encode(state)) > MAX_STATE_BYTES:
        reject("audit_capacity")


def references(value):
    """Typed model IDs are collected structurally; source handles stay inert."""
    result = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key.endswith("_id") and isinstance(child, str):
                result.add(child)
            elif key.endswith("_ids") and isinstance(child, list):
                result.update(v for v in child if isinstance(v, str))
            else:
                result.update(references(child))
    elif isinstance(value, list):
        for child in value:
            result.update(references(child))
    return result


def invalidate(state, before, after):
    old = {e["id"]: e for e in before["entities"]}
    new = {e["id"]: e for e in after["entities"]}
    changed = {key for key in old.keys() | new.keys() if old.get(key) != new.get(key)}
    # Non-entity engineering inputs (mappings, assumptions, attachments) may affect everything.
    global_change = any(before[k] != after[k] for k in ("mappings", "assumptions", "limitations", "source_maps", "attachments"))
    dependents = {}
    for entity in [*old.values(), *new.values()]:
        dependents.setdefault(entity["id"], set()).update(references(entity))
    for derived in state["derived"]:
        dependents[derived["id"]] = set(derived["dependencies"])
        if global_change:
            changed.add(derived["id"])
    while True:
        additions = {key for key, dependencies in dependents.items() if dependencies & changed} - changed
        if not additions:
            break
        changed.update(additions)
    for derived in state["derived"]:
        if derived["id"] in changed:
            derived["stale"] = True
    return sorted(d["id"] for d in state["derived"] if d["stale"])


class ProjectStore:
    """One project per database, FULL synchronous commits, no executable state.

    Actor and scopes must come from the trusted caller, never imported content.
    Job scheduling/worker execution are deliberately deferred to WP-06.
    """
    def __init__(self, database, *, fault=None, clock=time.time):
        self.path = Path(database)
        self.fault, self.clock = fault, clock
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=15)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("CREATE TABLE IF NOT EXISTS project (id INTEGER PRIMARY KEY CHECK(id=1), data BLOB NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, role TEXT NOT NULL, path TEXT UNIQUE NOT NULL, dependencies BLOB NOT NULL, data BLOB NOT NULL)")

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @classmethod
    def create(cls, database, model=None, *, package=None, **options):
        store = cls(database, **options)
        try:
            if package is None:
                package = Package.create(model)
            package = Package(package.manifest, package.files)
            state = loads(package.files["audit/state.json"]) if "audit/state.json" in package.files else initial_state(package.model)
            if "audit/state.json" not in package.files:
                state["model_artifact_id"] = package.manifest["model_artifact_id"]
            validate_state(state, package.model)
            # A portable package has no authority to assert current host synchronization.
            if state["host"]["status"] != "unlinked":
                state["host"] = {"status": "dirty", "dirty": True}
            with store.transaction():
                if store.db.execute("SELECT 1 FROM project").fetchone():
                    reject("project_exists")
                store.db.execute("INSERT INTO project VALUES(1, ?)", (encode(state),))
                for record in package.manifest["artifacts"]:
                    if record["id"] == package.manifest["model_artifact_id"] or record["artifact"]["path"] == "audit/state.json":
                        continue
                    store.db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?)", (record["id"], record["role"],
                                     record["artifact"]["path"], encode(record["dependencies"]), package.files[record["artifact"]["path"]]))
            return store
        except BaseException:
            store.close()
            raise

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            _fault(self.fault, "before_commit")
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        _fault(self.fault, "after_commit")

    def state(self):
        row = self.db.execute("SELECT data FROM project WHERE id=1").fetchone()
        if row is None:
            reject("missing_project")
        state = loads(row[0])
        validate_state(state, read("model", state["model"]))
        return state

    def _write(self, state):
        validate_state(state, state["model"])
        self.db.execute("UPDATE project SET data=? WHERE id=1", (encode(state),))
        _fault(self.fault, "journal_write")

    def snapshot(self):
        return self.state()["model"]

    @staticmethod
    def _authorize(actor, scopes, operation):
        if (not isinstance(actor, str) or not actor or len(actor) > 128
                or not isinstance(scopes, (list, tuple, set, frozenset)) or not all(isinstance(s, str) for s in scopes)
                or operation not in scopes):
            reject("unauthorized")

    @staticmethod
    def _payload(operation, payload):
        if operation in {"changes.apply", "entity.create"}:
            if not isinstance(payload, dict) or set(payload) != {"upsert", "delete"}:
                reject("invalid_changes")
            try:
                value = normalize(loads(encode(payload)))
            except (KeyError, TypeError):
                reject("invalid_changes")
            if not isinstance(value["upsert"], list) or not isinstance(value["delete"], list) or not all(isinstance(x, dict) and "id" in x for x in value["upsert"]):
                reject("invalid_changes")
            ids = [x["id"] for x in value["upsert"]] + value["delete"]
            if not all(isinstance(x, str) for x in ids) or len(ids) != len(set(ids)) or not ids:
                reject("invalid_changes")
            value["upsert"].sort(key=lambda x: x["id"])
            value["delete"].sort()
            return value
        if operation == "changes.undo":
            if not isinstance(payload, dict) or set(payload) != {"revision"} or type(payload["revision"]) not in (int, float):
                reject("invalid_changes")
            return payload
        reject("unsupported_operation")

    @staticmethod
    def _edit(state, operation, payload):
        before = state["model"]
        after = deepcopy(before)
        entities = {e["id"]: e for e in after["entities"]}
        if operation in {"changes.apply", "entity.create"}:
            for key in payload["delete"]:
                if key not in entities:
                    reject("missing_entity")
                del entities[key]
            for entity in payload["upsert"]:
                if operation == "entity.create" and entity["id"] in entities:
                    reject("entity_exists")
                entities[entity["id"]] = entity
            after["entities"] = list(entities.values())
        else:
            record = next((r for r in state["history"] if r["revision"] == payload["revision"]), None)
            if record is None:
                reject("unknown_revision")
            # Revert only this commit's affected entities; reject intervening edits.
            changed = record["inverse"]
            for key, expected in changed["expected"].items():
                if entities.get(key) != expected:
                    reject("undo_conflict")
            for key, value in changed["restore"].items():
                if value is None:
                    entities.pop(key, None)
                else:
                    entities[key] = value
            after["entities"] = list(entities.values())
        after["revision"] = before["revision"] + 1
        return read("model", after)

    def preview(self, actor, scopes, project_id, expected_revision, payload, *, operation="changes.apply", ttl=300):
        self._authorize(actor, scopes, operation)
        payload = self._payload(operation, payload)
        if not 0 < ttl <= 3600:
            reject("plan_expiry")
        with self.transaction():
            state = self.state()
            self._revision(state, project_id, expected_revision)
            after = self._edit(state, operation, payload)
            self._validate_artifacts(after)
            plan = {"id": str(uuid.uuid4()), "actor": actor, "project_id": project_id,
                    "base_revision": expected_revision, "payload": payload, "operation": operation,
                    "scopes": sorted(set(scopes)), "expires": self.clock() + ttl}
            plan["hash"] = sha256(encode(plan)).hexdigest()
            state["previews"].append(plan)
            self._write(state)
        return deepcopy(plan)

    @staticmethod
    def _revision(state, project_id, expected):
        if state["model"]["project_id"] != project_id:
            reject("wrong_project")
        if type(expected) not in (int, float) or state["model"]["revision"] != expected:
            reject("stale_revision")

    def _validate_artifacts(self, model):
        Package.create(model, self._artifacts(), model_artifact_id=self.state()["model_artifact_id"])

    def _artifacts(self):
        return [(r[0], r[1], r[2], r[4], loads(r[3])) for r in self.db.execute("SELECT * FROM artifacts ORDER BY id")]

    def apply(self, actor, scopes, project_id, expected_revision, key, payload,
              *, operation="changes.apply", plan_id=None, plan_hash=None):
        self._authorize(actor, scopes, operation)
        if not isinstance(key, str) or not key or len(key) > 128:
            reject("invalid_key")
        payload = self._payload(operation, payload)
        request_hash = sha256(encode({"project_id": project_id, "base_revision": expected_revision,
                                      "operation": operation, "payload": payload,
                                      "plan_id": plan_id, "plan_hash": plan_hash})).hexdigest()
        with self.transaction():
            state = self.state()
            if project_id != state["model"]["project_id"]:
                reject("wrong_project")
            duplicate = next((r for r in state["dedup"] if r["actor"] == actor and r["key"] == key), None)
            if duplicate:
                if duplicate["payload_hash"] != request_hash:
                    reject("idempotency_conflict")
                return deepcopy(duplicate["outcome"])
            self._revision(state, project_id, expected_revision)
            if plan_id is not None or plan_hash is not None:
                plan = next((p for p in state["previews"] if p["id"] == plan_id), None)
                if (not plan or not isinstance(plan_hash, str) or not hmac.compare_digest(plan["hash"], plan_hash)
                        or plan["hash"] != sha256(encode({k: v for k, v in plan.items() if k != "hash"})).hexdigest()
                        or plan["actor"] != actor or plan["project_id"] != project_id
                        or plan["base_revision"] != expected_revision or plan["expires"] <= self.clock()
                        or plan["operation"] != operation or plan["payload"] != payload
                        or plan["scopes"] != sorted(set(scopes))):
                    reject("invalid_plan")
            before = state["model"]
            after = self._edit(state, operation, payload)
            self._validate_artifacts(after)
            old = {e["id"]: e for e in before["entities"]}
            new = {e["id"]: e for e in after["entities"]}
            changed = {k for k in old.keys() | new.keys() if old.get(k) != new.get(k)}
            inverse = {"restore": {k: old.get(k) for k in sorted(changed)},
                       "expected": {k: new.get(k) for k in sorted(changed)}}
            stale = invalidate(state, before, after)
            state["model"] = after
            if state["host"]["status"] != "unlinked":
                state["host"] = {"status": "dirty", "dirty": True}
            outcome = {"revision": after["revision"], "semantic_hash": semantic_hash(after), "invalidated": stale}
            state["history"].append({"revision": after["revision"], "before": before, "after_hash": outcome["semantic_hash"],
                                     "actor": actor, "operation": operation, "inverse": inverse})
            state["dedup"].append({"actor": actor, "key": key, "payload_hash": request_hash, "outcome": outcome})
            self._write(state)
        return outcome

    def dispatch(self, actor, scopes, envelope):
        request = read("operation", envelope)
        if request["project_id"] != self.snapshot()["project_id"]:
            reject("wrong_project")
        operation, args = request["operation"], request["arguments"]
        self._authorize(actor, scopes, operation)
        def response(result):
            return read("response", {"contract_version": VERSION, "operation": operation, "result": result})
        if operation in {"model.validate", "model.hash"}:
            return response({"valid": True} if operation == "model.validate" else {"semantic_hash": semantic_hash(args["snapshot"])})
        if operation == "capabilities.get":
            return response({"contract_version": VERSION, "minimum_reader": VERSION,
                             "operations": ["model.validate", "model.hash", "capabilities.get", "thermal.conductor.create"],
                             "solver_available": False, "execution_mode": "fcst_native"})
        if operation == "thermal.conductor.create":
            outcome = self.apply(actor, {"entity.create"}, request["project_id"], request["expected_revision"],
                                 request["idempotency_key"], {"upsert": [{"kind": "conductor", **args}], "delete": []},
                                 operation="entity.create")
            return response({"entity_id": args["id"], "revision": outcome["revision"]})
        reject("not_implemented")

    def register_derived(self, artifact_id, kind, dependencies, *, expected_revision):
        if kind not in DERIVED_KINDS or not dependencies:
            reject("invalid_dependency")
        with self.transaction():
            state = self.state()
            self._revision(state, state["model"]["project_id"], expected_revision)
            known = {e["id"] for e in state["model"]["entities"]} | {d["id"] for d in state["derived"]}
            if (artifact_id in known or not set(dependencies) <= known
                    or any(d["stale"] and d["id"] in dependencies for d in state["derived"])):
                reject("invalid_dependency")
            item = {"id": artifact_id, "kind": kind, "dependencies": sorted(set(dependencies)),
                    "revision": expected_revision, "semantic_hash": semantic_hash(state["model"]), "stale": False}
            state["derived"].append(item)
            self._write(state)
        return item

    def derived(self, artifact_id, *, historical=False):
        item = next((d for d in self.state()["derived"] if d["id"] == artifact_id), None)
        if not item:
            reject("unknown_derived")
        if item["stale"] and not historical:
            reject("stale_result")
        return item

    def export_package(self):
        # A single read transaction keeps state and immutable artifacts consistent.
        self.db.execute("BEGIN")
        try:
            state = self.state()
            return Package.create(state["model"], self._artifacts(), state=state)
        finally:
            self.db.execute("ROLLBACK")

    def save(self, path, *, expanded=False, fault=None):
        return save_package(self.export_package(), path, expanded=expanded, fault=fault)

    def mark_host_dirty(self):
        with self.transaction():
            state = self.state()
            state["host"] = {"status": "dirty", "dirty": True}
            self._write(state)

    def synchronize_host(self, host_path, host_bytes, package_path, *, expected_revision, fault=None):
        """Host bytes come from the trusted adapter, never from imported code.

        Journal each half of the two-file save. Every interrupted state is dirty;
        clean is established only by subsequent exact-byte reconciliation.
        """
        with self.transaction():
            state = self.state()
            self._revision(state, state["model"]["project_id"], expected_revision)
            state["host"] = {"status": "prepared", "dirty": True, "revision": expected_revision,
                             "semantic_hash": semantic_hash(state["model"]), "artifact_sha256": sha256(host_bytes).hexdigest()}
            self._write(state)
        _fault(fault, "host_prepared")
        atomic_file(host_path, host_bytes)
        _fault(fault, "host_replace")
        with self.transaction():
            state = self.state()
            self._revision(state, state["model"]["project_id"], expected_revision)
            state["host"]["status"] = "host_written"
            self._write(state)
        self.save(package_path, fault=fault)
        _fault(fault, "package_saved")
        return self.reconcile_host(host_path, package_path)

    def reconcile_host(self, host_path, package_path):
        matched = False
        with self.transaction():
            state = self.state()
            host = state["host"]
            try:
                package = Package.open(package_path)
                saved_host = loads(package.files.get("audit/state.json", b"{}" )).get("host", {})
                matched = (host.get("status") in {"host_written", "package_written", "clean"}
                           and host.get("revision") == state["model"]["revision"]
                           and host.get("semantic_hash") == semantic_hash(state["model"])
                           and package.model == state["model"]
                           and sha256(Path(host_path).read_bytes()).hexdigest() == host.get("artifact_sha256")
                           and saved_host.get("status") in {"host_written", "clean"}
                           and all(saved_host.get(k) == host.get(k) for k in ("revision", "semantic_hash", "artifact_sha256")))
            except (OSError, PersistenceError, ContractError):
                matched = False
            state["host"] = {**host, "status": "clean", "dirty": False} if matched else {"status": "dirty", "dirty": True}
            self._write(state)
        if not matched:
            reject("host_reconciliation_required")
        return deepcopy(state["host"])
