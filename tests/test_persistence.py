# SPDX-License-Identifier: MIT OR Apache-2.0
from copy import deepcopy
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
import zipfile

from fcst_contracts import ContractError
from fcst_app.persistence import (Package, PersistenceError, Limits, encode, safe_path,
                                  save_package, recover_package, semantic_hash,
                                  migrate_legacy, downgrade_export, migrate_project, publication_lock)
from fcst_app.store import ProjectStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/contracts"
SCOPES = {"changes.apply", "changes.undo"}


def model():
    return json.loads((FIXTURES / "network.json").read_text())


def change(value=4):
    entity = deepcopy(model()["entities"][-1])
    entity["conductance"]["value"] = value
    return {"upsert": [entity], "delete": []}


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".local/test-scratch").mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".local/test-scratch")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = model()["project_id"]

    def store(self, name="project.db", **kwargs):
        store = ProjectStore.create(self.root / name, model(), **kwargs)
        self.addCleanup(store.close)
        return store

    def apply(self, store, payload=None, **kwargs):
        return store.apply("synthetic-actor", SCOPES, self.project, 0, "apply-1", payload or change(), **kwargs)

    def test_zip_expanded_roundtrip_and_exact_originals(self):
        original = b"opaque source\x00\xff\r\nimport os; raise RuntimeError('inert')\n"
        package = Package.create(model(), [(str(uuid.uuid4()), "source_original", "sources/input.dat", original, [])])
        for expanded in (False, True):
            target = self.root / ("expanded" if expanded else "project.fcst")
            receipt = save_package(package, target, expanded=expanded)
            reopened = Package.open(target)
            self.assertEqual(reopened.files["sources/input.dat"], original)
            self.assertEqual(semantic_hash(reopened.model), receipt["semantic_hash"])
            store = ProjectStore.create(self.root / (str(expanded) + ".db"), package=reopened)
            with store:
                self.apply(store)
                copied = store.export_package()
                self.assertEqual(copied.files["sources/input.dat"], original)

    def test_archive_paths_modes_duplicates_and_expansion_limits(self):
        for name in ("../escape", "a/../b", "A//B", "A/./B", "C:/test", "a\\b", "/root", "a/NUL.txt", "a/end.", "a/end "):
            with self.subTest(name=name), self.assertRaises(PersistenceError):
                safe_path(name)
        def archive(entries):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as output:
                for name, data, mode in entries:
                    info = zipfile.ZipInfo(name)
                    info.external_attr = mode << 16
                    output.writestr(info, data)
            return stream.getvalue()
        for entries in ([('A.txt', b'a', stat.S_IFREG), ('a.txt', b'b', stat.S_IFREG)],
                        [('link', b'elsewhere', stat.S_IFLNK)], [('a', b'a', stat.S_IFREG), ('a/b', b'b', stat.S_IFREG)],
                        [('A/one', b'a', stat.S_IFREG), ('a/two', b'b', stat.S_IFREG)]):
            with self.assertRaises(PersistenceError):
                Package.from_zip(archive(entries))
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as output:
            output.writestr("bomb.json", b"0" * 100000)
        with self.assertRaises(PersistenceError):
            Package.from_zip(stream.getvalue())
        for compression in (zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w", compression=compression) as output:
                output.writestr("small.json", b"{}")
            with self.assertRaisesRegex(PersistenceError, "unsupported_compression"):
                Package.from_zip(stream.getvalue())
        with self.assertRaises(PersistenceError):
            Package.from_zip(Package.create(model()).zip_bytes(), limits=Limits(items=1))
        with self.assertRaises(PersistenceError):
            Package.from_zip(b"not a zip")

    def test_checksum_closure_and_flat_directory_validation(self):
        package = Package.create(model())
        files = dict(package.files)
        files['model/snapshot.json'] += b' '
        with self.assertRaises(ContractError):
            Package(package.manifest, files)
        files = dict(package.files, **{'undeclared.json': b'{}'})
        with self.assertRaises(PersistenceError):
            Package(package.manifest, files)
        reference = {"path": "geometry/missing.brep", "byte_length": 1, "sha256": "0" * 64}
        document = model()
        # A valid frame/geometry pair isolates dependency closure from model validation.
        document["entities"].extend([
            {"id": "00000000-0000-4000-8000-000000000080", "kind": "frame", "origin": [{"value": 0, "unit": "m"}] * 3,
             "rotation": [[1,0,0],[0,1,0],[0,0,1]]},
            {"id": "00000000-0000-4000-8000-000000000081", "kind": "geometry", "frame_id": "00000000-0000-4000-8000-000000000080",
             "artifact": reference, "revision": 0}])
        with self.assertRaises(PersistenceError):
            Package.create(document)
        flat = self.root / "flat"
        (flat / 'model').mkdir(parents=True)
        (flat / 'manifest.json').write_bytes(encode(package.manifest))
        (flat / 'model/snapshot.json').write_bytes(package.files['model/snapshot.json'])
        self.assertEqual(Package.open(flat).model, package.model)
        (flat / 'CON.txt').write_bytes(b'bad')
        with self.assertRaises(PersistenceError):
            Package.open(flat)

    def test_save_faults_retain_previous_or_committed_recovery(self):
        for expanded in (False, True):
            for point in ("write", "flush", "fsync", "verify", "backup", "journal", "replace", "sync"):
                target = self.root / (str(expanded) + point)
                old = Package.create(model())
                save_package(old, target, expanded=expanded)
                edited = model(); edited["revision"] = 1; edited["entities"][-1]["conductance"]["value"] = 4
                new = Package.create(edited)
                def fault(observed):
                    if observed == point:
                        raise OSError("synthetic fault")
                with self.subTest(expanded=expanded, point=point), self.assertRaises(OSError):
                    save_package(new, target, expanded=expanded, fault=fault)
                recovered = recover_package(target)
                self.assertIn(recovered.model["revision"], (0, 1))
                self.assertEqual(recovered.model["revision"], 1 if point in {"replace", "sync"} else 0)
                if point in {"journal", "replace", "sync"}:
                    self.assertEqual(recover_package(target, previous=True).model["revision"], 0)

    def test_durable_retries_actor_project_scope_and_conflicts(self):
        store = self.store()
        first = self.apply(store)
        with ProjectStore(store.path) as restarted:
            self.assertEqual(self.apply(restarted), first)
            self.assertEqual(restarted.snapshot()["revision"], 1)
            with self.assertRaisesRegex(PersistenceError, "idempotency_conflict"):
                self.apply(restarted, change(9))
            with self.assertRaisesRegex(PersistenceError, "stale_revision"):
                restarted.apply("another-actor", SCOPES, self.project, 0, "apply-1", change())
            with self.assertRaisesRegex(PersistenceError, "wrong_project"):
                restarted.apply("synthetic-actor", SCOPES, str(uuid.uuid4()), 0, "apply-1", change())
            with self.assertRaisesRegex(PersistenceError, "unauthorized"):
                restarted.apply("synthetic-actor", set(), self.project, 1, "apply-2", change())
        other = self.store("other.db")
        self.assertEqual(self.apply(other)["revision"], 1)

    def test_atomic_multi_edit_undo_inverse_and_reader_snapshot(self):
        store = self.store()
        before = store.snapshot()
        payload = change()
        invalid = deepcopy(payload["upsert"][0]); invalid["id"] = str(uuid.uuid4()); invalid["to_node_id"] = str(uuid.uuid4())
        payload["upsert"].append(invalid)
        with self.assertRaises(ContractError):
            self.apply(store, payload)
        self.assertEqual(store.snapshot(), before)
        observer = sqlite3.connect(store.path, isolation_level=None)
        self.addCleanup(observer.close)
        observer.execute("BEGIN")
        observed = observer.execute("SELECT data FROM project").fetchone()[0]
        self.apply(store)
        self.assertEqual(observer.execute("SELECT data FROM project").fetchone()[0], observed)
        observer.execute("ROLLBACK")
        outcome = store.apply("synthetic-actor", SCOPES, self.project, 1, "undo-1", {"revision": 1}, operation="changes.undo")
        self.assertEqual(outcome["revision"], 2)
        self.assertEqual(outcome["semantic_hash"], semantic_hash(before))
        self.assertEqual(len(store.state()["history"]), 2)
        store.apply("synthetic-actor", SCOPES, self.project, 2, "apply-2", change(8))
        with self.assertRaisesRegex(PersistenceError, "undo_conflict"):
            store.apply("synthetic-actor", SCOPES, self.project, 3, "undo-2", {"revision": 1}, operation="changes.undo")

    def test_preview_is_durable_bound_expiring_and_has_no_apply_key(self):
        clock = [1000]
        store = self.store(clock=lambda: clock[0])
        plan = store.preview("synthetic-actor", SCOPES, self.project, 0, change(), ttl=10)
        self.assertFalse(store.state()["dedup"])
        for actor, scopes, payload, digest in (("another-actor", SCOPES, change(), plan["hash"]),
                ("synthetic-actor", {"changes.apply"}, change(), plan["hash"]),
                ("synthetic-actor", SCOPES, change(9), plan["hash"]),
                ("synthetic-actor", SCOPES, change(), "0" * 64)):
            with self.assertRaisesRegex(PersistenceError, "invalid_plan"):
                store.apply(actor, scopes, self.project, 0, "apply", payload, plan_id=plan["id"], plan_hash=digest)
        with ProjectStore(store.path, clock=lambda: clock[0]) as restarted:
            clock[0] = 1011
            with self.assertRaisesRegex(PersistenceError, "invalid_plan"):
                self.apply(restarted, plan_id=plan["id"], plan_hash=plan["hash"])
            clock[0] = 1005
            self.apply(restarted, plan_id=plan["id"], plan_hash=plan["hash"])
            # A lost response may be retried after expiry and still returns the original outcome.
            clock[0] = 1100
            self.assertEqual(self.apply(restarted, plan_id=plan["id"], plan_hash=plan["hash"])["revision"], 1)
        with self.assertRaisesRegex(PersistenceError, "stale_revision"):
            store.preview("synthetic-actor", SCOPES, self.project, 0, change())

    def test_commit_faults_and_process_termination_do_not_duplicate(self):
        for point in ("journal_write", "before_commit", "after_commit"):
            store = self.store(point + ".db")
            script = """import os,sys
from fcst_app.store import ProjectStore
from test_persistence import change, SCOPES
def fault(point):
    if point == sys.argv[2]: os._exit(73)
with ProjectStore(sys.argv[1], fault=fault) as store:
    store.apply('synthetic-actor', SCOPES, store.snapshot()['project_id'], 0, 'apply-1', change())
"""
            env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT/'python'), str(ROOT/'tests')]))
            result = subprocess.run([sys.executable, "-S", "-c", script, str(store.path), point], env=env, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 73)
            self.assertEqual(store.snapshot()["revision"], 1 if point == "after_commit" else 0)
            outcome = self.apply(store)
            self.assertEqual(outcome["revision"], 1)
            self.assertEqual(len(store.state()["history"]), 1)

    def test_concurrent_writers_commit_one_revision_and_retry_one_outcome(self):
        store = self.store()
        barrier = threading.Barrier(2)
        outcomes = []
        def execute(key):
            with ProjectStore(store.path) as writer:
                barrier.wait(timeout=15)
                try:
                    outcomes.append(writer.apply("synthetic-actor", SCOPES, self.project, 0, key, change()))
                except PersistenceError as error:
                    outcomes.append(error.code)
        threads = [threading.Thread(target=execute, args=(key,)) for key in ("first", "second")]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=20)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(sum(isinstance(o, dict) for o in outcomes), 1)
        self.assertIn("stale_revision", outcomes)
        self.assertEqual(store.snapshot()["revision"], 1)

    def test_dependency_invalidation_and_historical_results(self):
        store = self.store()
        root = model()["entities"][-1]["id"]
        # Exercise every persistence-owned derived category and transitive invalidation.
        for kind in ("geometry", "mesh", "optics", "environment", "solve", "comparison", "acceptance"):
            store.register_derived(kind, kind, [root], expected_revision=0)
            root = kind
        unrelated = model()["entities"][0]["id"]
        store.register_derived("unrelated", "mesh", [unrelated], expected_revision=0)
        self.apply(store)
        for kind in ("geometry", "mesh", "optics", "environment", "solve", "comparison", "acceptance"):
            with self.assertRaisesRegex(PersistenceError, "stale_result"):
                store.derived(kind)
            historical = store.derived(kind, historical=True)
            self.assertEqual(historical["revision"], 0)
            self.assertEqual(historical["semantic_hash"], semantic_hash(model()))
        self.assertFalse(store.derived("unrelated")["stale"])

    def test_portable_journal_reconstructs_retries_and_rejects_corruption(self):
        store = self.store()
        outcome = self.apply(store)
        target = self.root / "portable.fcst"
        store.save(target)
        package = Package.open(target)
        with ProjectStore.create(self.root / "rebuilt.db", package=package) as rebuilt:
            self.assertEqual(self.apply(rebuilt), outcome)
            self.assertEqual(rebuilt.state()["history"], store.state()["history"])
        state = store.state()
        state["history"][-1]["after_hash"] = "0" * 64
        with self.assertRaisesRegex(PersistenceError, "invalid_journal"):
            corrupt = Package.create(store.snapshot(), state=state)
            ProjectStore.create(self.root / "bad.db", package=corrupt)
        for field, value in (("history", [1]), ("dedup", [None]), ("storage_version", 99)):
            state = store.state(); state[field] = value
            with self.assertRaisesRegex(PersistenceError, "invalid_journal"):
                Package.create(store.snapshot(), state=state)

    def test_imported_model_artifact_identity_and_dependency_edges_survive(self):
        package = Package.create(model())
        model_id = str(uuid.uuid4())
        package.manifest["model_artifact_id"] = model_id
        package.manifest["artifacts"][0]["id"] = model_id
        raw = b"synthetic unchanged original"
        package.manifest["artifacts"].append({"id": str(uuid.uuid4()), "role": "source_original", "dependencies": [model_id],
            "artifact": {"path": "sources/original.dat", "sha256": sha256(raw).hexdigest(), "byte_length": len(raw)}})
        package.files["sources/original.dat"] = raw
        with ProjectStore.create(self.root / "imported.db", package=package) as store:
            self.apply(store)
            exported = store.export_package()
            self.assertEqual(exported.manifest["model_artifact_id"], model_id)
            self.assertEqual(next(r for r in exported.manifest["artifacts"] if r["role"] == "source_original")["dependencies"], [model_id])
            self.assertEqual(exported.files["sources/original.dat"], raw)

    def test_explicit_migration_backup_and_lossless_downgrade(self):
        package = Package.create(model())
        legacy = downgrade_export(package, "0.9")
        upgraded = migrate_legacy(json.loads(legacy))
        self.assertEqual(semantic_hash(upgraded.model), semantic_hash(model()))
        target = self.root / "migrated.fcst"
        save_package(package, target)
        save_package(upgraded, target)
        self.assertEqual(recover_package(target, previous=True).model, package.model)
        with self.assertRaises(PersistenceError):
            downgrade_export(Package.create(model(), state={}), "0.9")
        with self.assertRaises(PersistenceError):
            migrate_legacy({**json.loads(legacy), "unknown": True})
        with self.assertRaises(PersistenceError):
            downgrade_export(package, "future")

    def test_host_dirty_failed_sync_and_dual_file_recovery(self):
        for point in ("host_prepared", "host_replace", "write", "replace", "package_saved", None):
            directory = self.root / str(point); directory.mkdir()
            with ProjectStore.create(directory / "project.db", model()) as store:
                host_path, package_path = directory / "host.FCStd", directory / "project.fcst"
                store.mark_host_dirty()
                def fault(observed):
                    if point == observed: raise OSError("synthetic fault")
                if point:
                    with self.assertRaises(OSError):
                        store.synchronize_host(host_path, b"synthetic-host-bytes", package_path, expected_revision=0, fault=fault)
                    self.assertTrue(store.state()["host"]["dirty"])
                else:
                    host = store.synchronize_host(host_path, b"synthetic-host-bytes", package_path, expected_revision=0)
                    self.assertFalse(host["dirty"])
                    self.apply(store)
                    self.assertTrue(store.state()["host"]["dirty"])
                if point in {"package_saved", "replace"}:
                    self.assertFalse(store.reconcile_host(host_path, package_path)["dirty"])
                    host_path.write_bytes(b"direct external host edit")
                    with self.assertRaisesRegex(PersistenceError, "host_reconciliation_required"):
                        store.reconcile_host(host_path, package_path)
                    self.assertTrue(store.state()["host"]["dirty"])

    def test_optics_and_load_changes_invalidate_only_their_dependents(self):
        document = model()
        optics = {"id": str(uuid.uuid4()), "kind": "optics", "solar_absorptivity": 0.5,
                  "ir_emissivity": 0.8, "specular_fraction": 0.1, "transmissivity": 0.1}
        load = {"id": str(uuid.uuid4()), "kind": "load", "node_id": document["entities"][2]["id"],
                "power": {"value": 2, "unit": "W"}}
        document["entities"].extend([optics, load])
        with ProjectStore.create(self.root / "optics.db", document) as store:
            store.register_derived("radiation", "optics", [optics["id"]], expected_revision=0)
            store.register_derived("solve", "solve", [load["id"]], expected_revision=0)
            store.register_derived("checks", "acceptance", ["solve"], expected_revision=0)
            edited = deepcopy(optics); edited["ir_emissivity"] = 0.7
            store.apply("synthetic-actor", SCOPES, self.project, 0, "optics", {"upsert": [edited], "delete": []})
            self.assertTrue(store.derived("radiation", historical=True)["stale"])
            self.assertFalse(store.derived("solve")["stale"])
            edited = deepcopy(load); edited["power"]["value"] = 3
            store.apply("synthetic-actor", SCOPES, self.project, 1, "loads", {"upsert": [edited], "delete": []})
            self.assertTrue(store.derived("checks", historical=True)["stale"])
            with self.assertRaisesRegex(PersistenceError, "invalid_dependency"):
                store.register_derived("new-check", "acceptance", ["solve"], expected_revision=2)

    def test_directory_links_save_lock_and_first_save_recovery(self):
        package = Package.create(model())
        flat = self.root / "flat"; (flat / "model").mkdir(parents=True)
        (flat / "manifest.json").write_bytes(encode(package.manifest))
        original = self.root / "original.json"
        original.write_bytes(package.files["model/snapshot.json"])
        os.link(original, flat / "model/snapshot.json")
        with self.assertRaisesRegex(PersistenceError, "unsafe_member"):
            Package.open(flat)
        target = self.root / "lock.fcst"
        with publication_lock(target), self.assertRaisesRegex(PersistenceError, "save_busy"):
            save_package(package, target)
        target = self.root / "first"
        def fault(point):
            if point == "write": raise OSError("synthetic fault")
        with self.assertRaises(OSError):
            save_package(package, target, expanded=True, fault=fault)
        with self.assertRaises(PersistenceError):
            Package.open(target)
        self.assertEqual(save_package(package, target, expanded=True)["revision"], 0)
        save_package(package, target, expanded=True)
        pointer = json.loads((target / "PREVIOUS.json").read_bytes())
        prior_manifest = target / "revisions" / pointer["generation"] / "manifest.json"
        prior_manifest.write_bytes(prior_manifest.read_bytes() + b" ")
        with self.assertRaisesRegex(PersistenceError, "invalid_head"):
            recover_package(target, previous=True)

    def test_migration_tool_preserves_exact_input_and_cli_errors_are_bounded(self):
        source = ROOT / "tests/fixtures/persistence/legacy-0.9.json"
        original = source.read_bytes()
        target = self.root / "migrated.fcst"
        migrate_project(source, target)
        self.assertEqual(Package.open(target).files["sources/migration-input.json"], original)
        self.assertEqual(source.read_bytes(), original)
        with self.assertRaisesRegex(PersistenceError, "migration_requires_new_target"):
            migrate_project(source, source)
        env = dict(os.environ, PYTHONPATH=str(ROOT/"python"))
        result = subprocess.run([sys.executable, "-S", "-m", "fcst_cli", "project-inspect", str(target)], env=env, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["revision"], 0)
        result = subprocess.run([sys.executable, "-S", "-m", "fcst_cli", "project-inspect", str(self.root/"absent.fcst")], env=env, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(str(self.root).encode(), result.stdout + result.stderr)

    def test_normalized_retry_order_and_payload_conflicts_are_deterministic(self):
        store = self.store()
        initial = store.state()
        with patch("fcst_app.store.MAX_STATE_BYTES", len(encode(initial)) + 200):
            with self.assertRaisesRegex(PersistenceError, "audit_capacity"):
                self.apply(store)
        self.assertEqual(store.state(), initial)
        payload = change()
        payload["upsert"].append({"id": str(uuid.uuid4()), "kind": "submodel", "label": "Synthetic"})
        outcome = self.apply(store, payload)
        reordered = deepcopy(payload)
        reordered["upsert"].reverse()
        self.assertEqual(self.apply(store, reordered), outcome)
        with self.assertRaises(PersistenceError):
            self.apply(store, {"upsert": payload["upsert"] * 2, "delete": []})
        self.assertEqual(store.snapshot()["revision"], 1)

    def test_frozen_operation_dispatch_and_unimplemented_jobs(self):
        store = self.store()
        request = json.loads((FIXTURES/'operation-thermal.conductor.create.json').read_text())
        scope = {"thermal.conductor.create"}
        first = store.dispatch("synthetic-actor", scope, request)
        self.assertEqual(store.dispatch("synthetic-actor", scope, request), first)
        request["idempotency_key"] = str(uuid.uuid4()); request["expected_revision"] = 1
        with self.assertRaisesRegex(PersistenceError, "entity_exists"):
            store.dispatch("synthetic-actor", scope, request)
        request = json.loads((FIXTURES/'operation-job.submit.json').read_text())
        with self.assertRaisesRegex(PersistenceError, "not_implemented"):
            store.dispatch("synthetic-actor", {"job.submit"}, request)


if __name__ == "__main__":
    unittest.main()
