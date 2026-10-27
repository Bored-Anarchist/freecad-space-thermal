# SPDX-License-Identifier: MIT OR Apache-2.0
"""Run only inside the pinned FreeCAD bundle; synthetic data and bounded reports."""
import importlib.util
import json
import os
import platform
import sys
import sysconfig
from pathlib import Path
import FreeCAD as App
import Part


def main():
    directory = Path(os.environ["FCST_HOST_SMOKE_OUTPUT"])
    project = directory / "synthetic.FCStd"
    doc = App.newDocument("FCSTFoundationSmoke")
    doc.UndoMode = 1
    box = doc.addObject("PartDesign::Feature", "SyntheticBox")
    box.Shape = Part.makeBox(2, 3, 4)
    box.addProperty("App::PropertyFloat", "SyntheticLoad", "FCST")
    box.SyntheticLoad = 1.25
    doc.recompute()
    assert abs(box.Shape.Volume - 24) < 1e-12
    doc.saveAs(str(project))
    App.closeDocument(doc.Name)
    reopened = App.openDocument(str(project))
    reopened.UndoMode = 1
    assert reopened.SyntheticBox.SyntheticLoad == 1.25
    assert abs(reopened.SyntheticBox.Shape.Volume - 24) < 1e-12
    reopened.openTransaction("Synthetic edit")
    reopened.SyntheticBox.SyntheticLoad = 2.5
    reopened.commitTransaction()
    reopened.undo()
    assert reopened.SyntheticBox.SyntheticLoad == 1.25
    App.closeDocument(reopened.Name)
    source = Path(os.environ["FCST_HOST_SMOKE_SOURCE"])
    for name in ("fcst_app", "fcst_cli", "fcst_mcp"):
        spec = importlib.util.spec_from_file_location(name, source / "python" / name / "__init__.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    report = {"status": "passed", "scope": "foundation_host_smoke",
              "freecad_version": list(App.Version()[:3]), "python": platform.python_version(),
              "python_abi": "cp" + str(sys.version_info.major) + str(sys.version_info.minor),
              "soabi": sysconfig.get_config_var("SOABI"), "occt": Part.OCC_VERSION,
              "cases": ["create_geometry", "save_reopen", "edit_undo", "application_imports"],
              "volume": 24, "solver_available": False, "gui_qualified": False}
    assert report["freecad_version"] == ["1", "1", "4"], "Unexpected FreeCAD version"
    assert report["python_abi"] == "cp311"
    (directory / "host-smoke.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


try:
    main()
except Exception:
    import traceback
    (Path(os.environ["FCST_HOST_SMOKE_OUTPUT"]) / "payload-error.log").write_text(traceback.format_exc(), encoding="utf-8")
    raise
