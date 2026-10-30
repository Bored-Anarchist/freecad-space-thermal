# SPDX-License-Identifier: MIT OR Apache-2.0
"""Atomic new-tree exports. No call path overwrites or patches an original."""
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import shutil
import tempfile
import time

from fcst_app.persistence import Package, encode, is_link
from .core import Limits, artifact_references, checked_path, path_name, preservation_check, preview, reject, target_id
from .syntax import parse


@dataclass(frozen=True)
class Patch:
    path: str
    start: int
    end: int
    original_sha256: str
    replacement: bytes


def rename_new(source, destination):
    # Windows scanners may briefly hold newly written directories. A bounded
    # retry never turns publication into an overwrite or masks other failures.
    for attempt in range(20):
        if destination.exists() or is_link(destination):
            reject("export_requires_new_tree")
        try:
            source.rename(destination)
            return
        except PermissionError as error:
            if os.name != "nt" or getattr(error,"winerror",None) not in {5,32,33} or attempt == 19:
                raise
            time.sleep(.05)


def export_tree(staged, destination, patches=(), *, limits=Limits(), adapter=None):
    if adapter is not None and adapter.profile != staged.dialect:
        reject("adapter_profile_mismatch")
    name_check = adapter.path_name if adapter is not None else path_name
    source_path = adapter.checked_path if adapter is not None else checked_path
    tree_check = adapter.preservation_check if adapter is not None else preservation_check
    report = staged.report
    if not next(r for r in report["operations"] if r["operation"] == "unchanged-export")["supported"]:
        reject("dependency_closure")
    if tree_check(staged.root,staged.sources,limits):
        reject("stale_source_tree")
    destination = Path(destination).absolute()
    if destination.exists() or destination.resolve().is_relative_to(staged.root.resolve()) or staged.root.resolve().is_relative_to(destination.resolve()):
        reject("export_requires_new_tree")
    if not destination.parent.is_dir() or any(is_link(p) for p in (destination, *destination.parents)):
        reject("unsafe_export_parent")
    files = {s.path:s.content for s in staged.sources}
    for name, raw in files.items():
        path = source_path(staged.root, name)
        try:
            with path.open("rb") as stream:
                current = stream.read(limits.file_bytes+1)
        except OSError:
            reject("source_unavailable")
        if current != raw:
            reject("stale_source")
    patches = tuple(patches)
    if patches and not report["runnable"]:
        reject("opaque_edit")
    edits = {}
    for patch in patches:
        if type(patch.start) is not int or type(patch.end) is not int or not isinstance(patch.replacement, bytes):
            reject("invalid_patch")
        name_check(patch.path)
        source = next((s for s in staged.sources if s.path == patch.path), None)
        record = next((r for r in source.records if r.start == patch.start and r.end == patch.end), None) if source else None
        if not record or record.digest != patch.original_sha256:
            reject("unsupported_patch")
        # Preserve line termination, record kind and source identity. No include/code injection.
        if adapter is not None:
            adapter.validate_patch(record,patch.replacement,limits)
        else:
            if record.kind not in {"ENTITY","CASE","MAPPING","ATTACHMENT","EXPRESSION","PROCEDURE"}:
                reject("unsupported_patch")
            replacement = parse(patch.path, patch.replacement, limits)
            if len(replacement) != 1 or replacement[0].code or replacement[0].kind != record.kind:
                reject("unsupported_patch")
            before, after = record.value, replacement[0].value
            if any(before.get(k) != after.get(k) for k in ("namespace","handle")):
                reject("identity_edit")
        ending = b"\r\n" if record.content.endswith(b"\r\n") else b"\n" if record.content.endswith(b"\n") else b""
        new_ending = b"\r\n" if patch.replacement.endswith(b"\r\n") else b"\n" if patch.replacement.endswith(b"\n") else b""
        if ending != new_ending:
            reject("line_ending_edit")
        edits.setdefault(patch.path, []).append(patch)
    for path, changes in edits.items():
        ordered = sorted(changes, key=lambda p:p.start)
        if any(a.end > b.start for a,b in zip(ordered,ordered[1:])):
            reject("overlapping_patch")
        for patch in reversed(ordered):
            files[path] = files[path][:patch.start]+patch.replacement+files[path][patch.end:]
    temporary = Path(tempfile.mkdtemp(prefix=".fcst-export-", dir=destination.parent))
    try:
        for name, raw in files.items():
            target = temporary / name_check(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        validated = adapter.preview(temporary,staged.entry,limits=limits) if adapter is not None else preview(temporary, staged.entry, dialect=staged.dialect, limits=limits)
        if patches and not validated.report["runnable"]:
            reject("unsafe_edit")
        if len(validated.sources) != len(staged.sources):
            reject("export_closure_changed")
        # Windows rename fails if another actor created the destination meanwhile.
        rename_new(temporary,destination)
        return {"operation":"controlled-edit" if patches else "unchanged-export", "source_revision":report["source_revision"],
                "export_revision":validated.report["source_revision"], "files":[{"path":p,"sha256":sha256(b).hexdigest()} for p,b in sorted(files.items())]}
    finally:
        if temporary.exists():
            # This path is created above and always stays in the destination parent.
            if temporary.resolve().parent != destination.parent.resolve() or not temporary.name.startswith(".fcst-export-"):
                reject("unsafe_cleanup")
            shutil.rmtree(temporary)


def source_package(staged):
    """Persist only a fully mapped native conversion, with exact source bytes."""
    model = staged.require_native()
    files = {"model.json":encode(model), "exchange/fidelity.json":staged.report_bytes}
    for source in staged.sources:
        files["source/"+source.path] = source.content
    artifact_roles = {}
    for artifact in artifact_references(model):
        name = artifact["path"]
        if name in artifact_roles:
            continue
        if name in files:
            reject("package_path_collision")
        files[name] = next(s.content for s in staged.sources if s.path == name)
        artifact_roles[name] = "mesh" if any(e["kind"] == "mesh" and e.get("artifact") == artifact for e in model["entities"]) else "geometry"
    ids = {name:target_id(("artifact",name)) for name in files}
    graph = {r["path"]:r["includes"] for r in staged.report["dependencies"]}
    records = []
    for name, raw in files.items():
        role = artifact_roles.get(name) or ("model" if name == "model.json" else "evidence" if name.startswith("exchange/") else "source_original" if name == "source/"+staged.entry else "source_dependency")
        records.append({"id":ids[name], "role":role,
                        "artifact":{"path":name,"sha256":sha256(raw).hexdigest(),"byte_length":len(raw)},
                        "dependencies":[ids["source/"+p] for p in graph.get(name.removeprefix("source/"), [])]})
    manifest = {"contract_version":"2.0.0", "minimum_reader":"2.0.0", "project_id":model["project_id"],
                "revision":model["revision"], "model_artifact_id":ids["model.json"], "artifacts":records}
    return Package(manifest, files)
