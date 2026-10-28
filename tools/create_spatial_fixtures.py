# SPDX-License-Identifier: MIT OR Apache-2.0
"""Author deterministic synthetic conformance cases. Run only to revise frozen inputs."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from fcst_app.persistence import encode, semantic_hash
from fcst_contracts import inspect
from fcst_contracts.spatial import mesh_hash


def main():
    folder = ROOT / "tests/fixtures/spatial"
    folder.mkdir(exist_ok=True)
    uid = lambda n: str(uuid.UUID(int=(0x12345678123440008000000000000000+n)))
    h = sha256((ROOT / "LICENSE").read_bytes()).hexdigest()
    model = json.loads((ROOT / "tests/fixtures/contracts/network.json").read_bytes())
    ids = [uid(i) for i in range(1, 5)]
    value = {"contract_version": "2.0.0", "minimum_reader": "2.0.0", "capability": "spatial-linear-vertex-v2",
        "id": uid(50), "project_id": model["project_id"], "model_hash": semantic_hash(model), "mesh_revision": h,
        "execution_mode": "fcst_native", "vertex_ids": ids, "vertices": [[0,0,0], [1,0,0], [0,1,0], [0,0,1]],
        "cells": [{"id": uid(10), "topology": "tet4", "order": 1, "vertices": [0,1,2,3]},
                  {"id": uid(11), "topology": "tri3", "order": 1, "vertices": [0,2,1]}],
        "frames": [{"id": uid(20), "basis": [[0,-1,0], [1,0,0], [0,0,1]]}],
        "material": {"conductivity": [[2,0,0], [0,3,0], [0,0,4]], "conductivity_unit": "W/(m*K)", "frame_id": uid(20),
                     "density": 1000, "density_unit": "kg/m3", "specific_heat": 500, "specific_heat_unit": "J/(kg*K)"},
        "times": [0,1], "fields": [],
        "mappings": [{"from_id": uid(30), "from_kind": "cad_face", "to_id": uid(11), "to_kind": "facet", "weight": 1, "area_m2": .5, "provenance": h},
                     {"from_id": uid(10), "from_kind": "element", "to_id": uid(31), "to_kind": "thermal_node", "weight": 1, "area_m2": 1, "provenance": h}],
        "cad_face_ids": [uid(30)], "thermal_node_ids": [uid(31)], "source_license_hash": h,
        "boundary": {"kind": "surface_flux", "value": 8, "unit": "W/m2", "cell_ids": [uid(11)]}}
    for quantity, unit, components, values in [("temperature", "K", ["scalar"], [[300],[301],[302],[303]]), ("heat_flux", "W/m2", ["x","y","z"], [[2,3,8]]*4)]:
        value["fields"].append({"quantity": quantity, "unit": unit, "components": components, "location": "mesh_vertex",
             "entity_ids": list(ids), "frame_id": uid(20), "projection": "raw", "provenance": h, "values": [values, values]})
    cases = []
    def add(name, v, status="passed", code=None):
        raw = encode(v)
        (folder / (name+".json")).write_bytes(raw+b"\n")
        actual = inspect("spatial", raw)
        assert actual["status"] == status and actual.get("code") == code, (name, actual)
        cases.append({"id": name, "kind": "spatial", "path": name+".json", "status": status, **({"code": code} if code else {"semantic_hash": actual["semantic_hash"]}), "sha256": sha256(raw+b"\n").hexdigest()})
    value["mesh_revision"] = mesh_hash(value)
    add("solid-surface-rotated", value)
    mutations = [
      ("higher-order", lambda v: v["cells"][0].update(order=2), "schema"),
      ("midside-truncation", lambda v: v["cells"][0]["vertices"].append(2), "schema"),
      ("reversed-tet", lambda v: v["cells"][0].update(vertices=[1,0,2,3]), "spatial_orientation"),
      ("degenerate-tet", lambda v: v["vertices"].__setitem__(3,[1,1,0]), "spatial_orientation"),
      ("bad-connectivity", lambda v: v["cells"][0].update(vertices=[0,1,2,4]), "spatial_connectivity"),
      ("duplicate-identity", lambda v: v["thermal_node_ids"].__setitem__(0,v["vertex_ids"][0]), "spatial_identity"),
      ("reordered-field", lambda v: v["fields"][0]["entity_ids"].reverse(), "spatial_reference"),
      ("wrong-flux-unit", lambda v: v["fields"][1].update(unit="W"), "schema"),
      ("wrong-rank", lambda v: v["fields"][1].update(components=["scalar"]), "schema"),
      ("integration-point", lambda v: v["fields"][1].update(location="integration_point"), "schema"),
      ("unknown-projection", lambda v: v["fields"][1].update(projection="averaged"), "schema"),
      ("field-shape", lambda v: v["fields"][0]["values"][0].pop(), "spatial_shape"),
      ("negative-kelvin", lambda v: v["fields"][0]["values"][0][0].__setitem__(0,-1), "spatial_range"),
      ("bad-frame", lambda v: v["frames"][0]["basis"][0].__setitem__(1,1), "spatial_frame"),
      ("indefinite-material", lambda v: v["material"]["conductivity"][2].__setitem__(2,-1), "spatial_material"),
      ("missing-frame", lambda v: v["material"].update(frame_id=uid(999)), "spatial_reference"),
      ("weight-sum", lambda v: v["mappings"][0].update(weight=.75), "spatial_weight"),
      ("dangling-map", lambda v: v["mappings"][0].update(to_id=uid(999)), "spatial_reference"),
      ("wrong-boundary-unit", lambda v: v["boundary"].update(unit="W"), "spatial_boundary"),
      ("time-order", lambda v: v.update(times=[1,0]), "spatial_time"),
      ("stale-mesh-revision", lambda v: v["vertices"][1].__setitem__(0,2), "spatial_mesh_revision"),
      ("unknown-major", lambda v: v.update(contract_version="3.0.0"), "version"),
      ("minimum-reader", lambda v: v.update(minimum_reader="3.0.0"), "version"),
      ("unknown-field", lambda v: v.update(extra=True), "schema")]
    for name, mutation, code in mutations:
        v = deepcopy(value); mutation(v); add(name, v, "failed", code)
    (folder / "cases.json").write_text(json.dumps({"cases": cases}, indent=2)+"\n")


if __name__ == "__main__":
    main()

