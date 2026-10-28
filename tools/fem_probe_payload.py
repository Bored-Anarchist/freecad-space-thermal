# SPDX-License-Identifier: LGPL-2.1-or-later
"""Application-thread foundation probes in the pinned host; raw files stay local."""
import json
import os
from pathlib import Path
import sys
import traceback


def main():
    import FreeCAD as App
    import Fem
    import Part
    import ObjectsFem
    root = Path(os.environ["FCST_HOST_SMOKE_SOURCE"])
    folder = Path(os.environ["FCST_FEM_OUTPUT"])
    sys.path.insert(0, str(root / "python"))
    from fcst_contracts import read, loads
    from fcst_app.persistence import PersistenceError, semantic_hash, Package
    from fcst_app.store import ProjectStore
    from fcst_app import fem_adapter as adapter
    value = read("spatial", loads((root / "tests/fixtures/spatial/solid-surface-rotated.json").read_bytes()))
    model = loads((root / "tests/fixtures/contracts/network.json").read_bytes())
    assert list(App.Version()[:3]) == ["1", "1", "4"] and sys.version_info[:2] == (3,11)
    doc = App.newDocument("FCSTFEMFoundation")
    doc.UndoMode = 1
    obj, result = adapter.create(doc, value)
    assert obj.FemMesh.NodeCount == 4 and obj.FemMesh.VolumeCount == 1 and obj.FemMesh.FaceCount == 1
    assert list(obj.FemMesh.getElementNodes(1)) == [1,2,3,4]
    assert tuple(obj.FemMesh.Nodes[2]) == (1000,0,0)
    fields = adapter.query(result, value, semantic_hash(model))
    assert fields["heat_flux"] == [[-3,2,8]]*4
    # API mesh export/import is the selected offline path; no executable discovery.
    mesh_file = folder / "synthetic.unv"
    obj.FemMesh.write(str(mesh_file))
    imported = Fem.read(str(mesh_file))
    assert imported.NodeCount == 4 and imported.VolumeCount == 1
    (folder / "mesh-observed.json").write_text(json.dumps({"volumes": list(imported.Volumes), "faces": list(imported.Faces), "nodes": {str(i): list(imported.getElementNodes(i)) for i in [*imported.Volumes, *imported.Faces]}}))
    assert len(imported.Volumes) == 1
    assert list(imported.getElementNodes(next(iter(imported.Volumes)))) == [1,2,3,4]
    assert tuple(imported.Nodes[2]) == (1000,0,0)
    shape = doc.addObject("PartDesign::Feature", "SyntheticSolid")
    shape.Shape = Part.makeBox(1000,1000,1000)
    mat = ObjectsFem.makeMaterialSolid(doc, "FCSTMaterial")
    mat.References = [(shape, ("Face1",))]
    mat.Material = {"Name": "Synthetic", "ThermalConductivity": "2 W/m/K", "Density": "1000 kg/m^3", "SpecificHeat": "500 J/kg/K"}
    load = ObjectsFem.makeConstraintHeatflux(doc, "FCSTFlux")
    load.References = [(shape, ("Face1",))]
    assert mat.References[0][1] == ("Face1",) and load.References[0][1] == ("Face1",)
    for name in ("missing_symbol",):
        try: adapter.capability(ObjectsFem, name)
        except PersistenceError as e: assert e.code == "host_capability_missing"
        else: raise AssertionError("missing capability accepted")
    path = folder / "synthetic.FCStd"
    doc.recompute()
    doc.saveAs(str(path))
    App.closeDocument(doc.Name)
    doc = App.openDocument(str(path)); doc.UndoMode = 1
    assert adapter.query(doc.FCSTResult, value, semantic_hash(model)) == fields
    with ProjectStore.create(folder / "host.db", model) as store, ProjectStore.create(folder / "standalone.db", model) as standalone:
        observer = adapter.DocumentObserver(doc, store)
        App.addDocumentObserver(observer)
        entity = model["entities"][-1].copy()
        entity["conductance"] = {"value": 4, "unit": "W/K"}
        change = {"upsert": [entity], "delete": []}
        scopes = {"changes.apply", "changes.undo"}
        actual = adapter.edit_through_service(doc, store, "synthetic", scopes, "edit", change)
        expected = standalone.apply("synthetic", scopes, model["project_id"], 0, "edit", change)
        assert actual == expected and store.state()["host"]["dirty"]
        try: adapter.query(doc.FCSTResult, value, actual["semantic_hash"])
        except PersistenceError as e: assert e.code == "stale_result"
        else: raise AssertionError("stale display accepted")
        doc.undo()
        undo = store.apply("synthetic", scopes, model["project_id"], 1, "undo", {"revision": 1}, operation="changes.undo")
        assert undo["semantic_hash"] == semantic_hash(model)
        assert doc.FCSTMesh.FCSTDescriptor == (root / "tests/fixtures/spatial/solid-surface-rotated.json").read_text().strip()
        old = {"id": "face-1", "revision": 0, "signature": "same"}
        assert adapter.reconcile_attachment(old, [old, {"id": "other"}]) == old
        for candidates in ([], [old, old], [{**old,"revision":1}], [{**old,"id":"split-a"},{**old,"id":"split-b"}], [{**old,"id":"merged"}]):
            try: adapter.reconcile_attachment(old, candidates)
            except PersistenceError as e: assert e.code == "attachment_reassignment_required"
            else: raise AssertionError("ambiguous attachment adopted")
        def interrupted(point):
            if point == "host_replace": raise RuntimeError("synthetic interruption")
        try: store.synchronize_host(folder / "coordinated.FCStd", path.read_bytes(), folder / "coordinated.fcst", expected_revision=2, fault=interrupted)
        except RuntimeError: pass
        assert store.state()["host"]["dirty"]
        store.synchronize_host(folder / "coordinated.FCStd", path.read_bytes(), folder / "coordinated.fcst", expected_revision=2)
        assert not store.state()["host"]["dirty"]
        # Real host topology changes and direct property changes trigger dirty state.
        original_shape = doc.SyntheticSolid.Shape
        doc.SyntheticSolid.Shape = original_shape.cut(Part.makeBox(500,1000,1000))
        assert doc.SyntheticSolid.Shape.Volume != original_shape.Volume and store.state()["host"]["dirty"]
        doc.SyntheticSolid.Shape = original_shape.fuse(Part.makeBox(500,1000,1000,App.Vector(1000,0,0)))
        assert doc.SyntheticSolid.Shape.Volume > original_shape.Volume
        doc.FCSTMesh.FemMesh = imported
        doc.removeObject("SyntheticSolid")
        assert store.state()["host"]["dirty"]
        # A competing canonical update during prepared host synchronization cannot
        # turn the old host revision clean.
        def competing(point):
            if point == "host_replace":
                store.apply("synthetic", scopes, model["project_id"], 2, "competing", change)
        try: store.synchronize_host(folder / "coordinated.FCStd", path.read_bytes(), folder / "coordinated.fcst", expected_revision=2, fault=competing)
        except PersistenceError as e: assert e.code in {"stale_revision", "host_reconciliation_required"}
        else: raise AssertionError("competing revision appeared clean")
        assert store.state()["host"]["dirty"]
        App.removeDocumentObserver(observer)
    App.closeDocument(doc.Name)
    report = {"status": "passed", "scope": "WP-05.5 representative FEM foundation; full GUI and spatial solving remain unqualified",
        "freecad_version": list(App.Version()), "python_abi": "cp311", "occt": Part.OCC_VERSION,
        "cases": [{"id": i, "status": "passed"} for i in ("WP055-HOST-001", "WP055-HOST-002", "WP055-HOST-003", "WP055-HOST-004")],
        "mesh": {"nodes": 4, "tet4": 1, "tri3": 1, "host_length_unit": "mm", "canonical_length_unit": "m", "path": "FemMesh.write/Fem.read UNV"},
        "fields": {"temperature_unit": "K", "heat_flux_unit": "W/m2", "frame": "global", "projection": "raw"},
        "solver_available": False, "gui_qualified": False}
    (folder / "fem-probe.json").write_text(json.dumps(report, indent=2)+"\n")


try:
    main()
except Exception:
    (Path(os.environ["FCST_FEM_OUTPUT"]) / "payload-error.log").write_text(traceback.format_exc())
    raise
