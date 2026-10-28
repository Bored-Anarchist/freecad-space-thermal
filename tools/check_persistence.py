# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded WP-05 acceptance report; raw array/crash diagnostics stay local."""
from __future__ import annotations

import argparse
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from fcst_app.arrays import libraries, read_arrays, write_arrays
from fcst_app.persistence import (Package, PersistenceError, encode, save_package,
                                  recover_package, semantic_hash)
from fcst_app.store import ProjectStore
from fcst_tools.gate import evaluate


def network():
    return json.loads((ROOT / "tests/fixtures/contracts/network.json").read_bytes())


def result_arrays():
    return {"index/node_uuid": [list(uuid.UUID(e["id"]).bytes) for e in network()["entities"] if e["kind"] == "node"],
            "time": [0.0, 1.0], "temperature": [[293.15, 300.0], [294.0, 300.0]],
            "power": [[1.0, -1.0], [0.5, -0.5]], "residual": [[0.0, 0.0], [0.0, 0.0]]}


class PersistenceAcceptance(unittest.TestCase):
    def setUp(self):
        (ROOT / ".local/test-scratch").mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".local/test-scratch")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_hdf5_result_exact_layout_and_portable_package(self):
        data = write_arrays("result", semantic_hash(network()), result_arrays())
        observed = read_arrays(data)
        self.assertEqual(observed["semantic_hash"], semantic_hash(network()))
        self.assertEqual(observed["arrays"]["temperature"].shape, (2, 2))
        package = Package.create(network(), [(str(uuid.uuid4()), "result", "results/arrays.h5", data, [])])
        target = self.root / "arrays.fcst"
        save_package(package, target)
        self.assertEqual(Package.open(target).files["results/arrays.h5"], data)
        script = "from fcst_app.persistence import Package; import sys; p=Package.open(sys.argv[1]); assert len(p.files)==2"
        result = subprocess.run([sys.executable, "-I", "-c", script, str(target)], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0)

    def test_hdf5_mesh_connectivity_normals_and_dtypes(self):
        mesh = {"index/entity_uuid": [list(uuid.uuid4().bytes)], "vertices": [[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],
                "connectivity/offsets": [0, 3], "connectivity/vertex_index": [0, 1, 2], "normals": [[0.,0.,1.]]}
        for role in ("radiation_mesh", "conduction_mesh"):
            self.assertEqual(read_arrays(write_arrays(role, "0"*64, mesh))["role"], role)
        for name, value in (("connectivity/vertex_index", [0,1,9]), ("connectivity/offsets", [1,3]), ("normals", [[0.,0.,2.]])):
            invalid = {**mesh, name: value}
            with self.assertRaises(PersistenceError):
                write_arrays("radiation_mesh", "0"*64, invalid)
        with self.assertRaises(PersistenceError):
            write_arrays("radiation_mesh", "0"*64, {**mesh, "connectivity/vertex_index": [-1,1,2]})

    def test_hdf5_nonfinite_shapes_units_and_version(self):
        arrays = result_arrays()
        for name, value in (("temperature", [[float('nan'), 1.], [2.,3.]]),
                            ("temperature", [[-1.,1.],[2.,3.]]), ("temperature", [[1.,2.,3.]]),
                            ("time", [1.,1.]), ("index/node_uuid", [[0]*16,[0]*16])):
            with self.assertRaises(PersistenceError):
                write_arrays("result", "0"*64, {**arrays, name: value})
        h5py, _ = libraries()
        data = write_arrays("result", "0"*64, arrays)
        for key, value in (("contract_version", "99.0"), ("semantic_hash", "invalid")):
            stream = io.BytesIO(data)
            with h5py.File(stream, "r+") as file: file.attrs[key] = value
            with self.assertRaises(PersistenceError): read_arrays(stream.getvalue())
        stream = io.BytesIO(data)
        with h5py.File(stream, "r+") as file: file["time"].attrs["unit"] = "W"
        with self.assertRaises(PersistenceError): read_arrays(stream.getvalue())

    def test_hdf5_external_soft_virtual_hard_links_and_filters_rejected(self):
        h5py, np = libraries()
        original = write_arrays("result", "0"*64, result_arrays())
        for kind in ("external", "soft", "hard", "virtual", "filter", "external_storage"):
            stream = io.BytesIO(original)
            with h5py.File(stream, "r+") as file:
                del file["temperature"]
                if kind == "external": file["temperature"] = h5py.ExternalLink("absent.h5", "/temperature")
                elif kind == "soft": file["temperature"] = h5py.SoftLink("/power")
                elif kind == "hard": file["temperature"] = file["power"]
                elif kind == "virtual":
                    layout = h5py.VirtualLayout(shape=(2,2), dtype="<f8")
                    layout[:] = h5py.VirtualSource("absent.h5", "/temperature", shape=(2,2))
                    file.create_virtual_dataset("temperature", layout).attrs["unit"] = "K"
                elif kind == "external_storage":
                    file.create_dataset("temperature", shape=(2,2), dtype="<f8", external=[("absent.dat", 0, 32)]).attrs["unit"] = "K"
                else:
                    file.create_dataset("temperature", data=np.ones((2,2)), compression="gzip").attrs["unit"] = "K"
            with self.subTest(kind=kind), self.assertRaises(PersistenceError):
                read_arrays(stream.getvalue())
        self.assertFalse((self.root / "absent.dat").exists())

    def test_hdf5_logical_size_limit_precedes_materialization(self):
        h5py, _ = libraries()
        stream = io.BytesIO(write_arrays("result", "0"*64, result_arrays()))
        with h5py.File(stream, "r+") as file:
            del file["temperature"]
            file.create_dataset("temperature", shape=(10000000,2), chunks=(128,2), dtype="<f8").attrs["unit"] = "K"
        self.assertLess(len(stream.getvalue()), 100000)
        with self.assertRaisesRegex(PersistenceError, "hdf5_limit"):
            read_arrays(stream.getvalue(), 1024*1024)

    def test_hard_kill_each_package_save_boundary(self):
        for expanded in (False, True):
            for point in ("write", "flush", "fsync", "verify", "backup", "journal", "replace", "sync"):
                target = self.root / (str(expanded) + point)
                save_package(Package.create(network()), target, expanded=expanded)
                script = """import os,sys,json
from fcst_app.persistence import Package,save_package
model=json.loads(sys.argv[4]);model['revision']=1
def fault(point):
    if point == sys.argv[2]: os._exit(73)
save_package(Package.create(model),sys.argv[1],expanded=sys.argv[3]=='True',fault=fault)
"""
                env = dict(os.environ, PYTHONPATH=str(ROOT / "python"))
                result = subprocess.run([sys.executable, "-c", script, str(target), point, str(expanded), json.dumps(network())],
                                        env=env, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 73)
                reopened = recover_package(target)
                self.assertEqual(reopened.model["revision"], 1 if point in {"replace", "sync"} else 0)
                if point in {"journal", "replace", "sync"}:
                    self.assertEqual(recover_package(target, previous=True).model["revision"], 0)

    def test_fresh_process_portable_rebuild_retry(self):
        with ProjectStore.create(self.root / "project.db", network()) as store:
            request = json.loads((ROOT / "tests/fixtures/contracts/operation-thermal.conductor.create.json").read_bytes())
            first = store.dispatch("synthetic-actor", {"thermal.conductor.create"}, request)
            target = self.root / "portable.fcst"
            store.save(target)
        script = """import sys,json
from fcst_app.persistence import Package
from fcst_app.store import ProjectStore
with ProjectStore.create(sys.argv[2],package=Package.open(sys.argv[1])) as store:
    actual=store.dispatch('synthetic-actor', {'thermal.conductor.create'},json.loads(sys.argv[3]))
    assert actual==json.loads(sys.argv[4]) and len(store.snapshot()['entities'])==6
"""
        result = subprocess.run([sys.executable, "-I", "-c", script, str(target), str(self.root/"rebuilt.db"), json.dumps(request), json.dumps(first)],
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / ".local/persistence.json")
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    cases = []
    for test in unittest.defaultTestLoader.loadTestsFromTestCase(PersistenceAcceptance):
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream).run(unittest.TestSuite([test]))
        (args.report.parent / (test.id() + ".log")).write_text(stream.getvalue(), encoding="utf-8")
        cases.append({"id": test._testMethodName, "status": "passed" if result.wasSuccessful() and not result.skipped else "failed"})
    expected = json.loads((ROOT / "ci/coverage.json").read_bytes())["persistence_cases"]
    verdict = evaluate(expected, cases)
    sources = ["python/fcst_app/persistence.py", "python/fcst_app/store.py", "python/fcst_app/arrays.py",
               "tests/test_persistence.py", "tools/check_persistence.py", "ci/requirements.lock"]
    report = {"schema_version": 1, "work_package": "WP-05", "gate": verdict, "cases": cases,
              "input_sha256": {name: sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
              "scope": "Synthetic package, transaction, crash and HDF5 acceptance; no worker, GUI or vendor qualification"}
    args.report.write_bytes(encode(report) + b"\n")
    print(json.dumps({"gate": verdict, "cases": cases}))
    return 0 if verdict["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
