# SPDX-License-Identifier: MIT OR Apache-2.0
"""Adapter discovery, bounded include resolution, immutable previews and fidelity."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import uuid

from fcst_contracts import BUNDLE, ContractError, dependency_order, loads, read, validate, verify_artifact
from fcst_app.persistence import encode, is_link, safe_path, PersistenceError
from .syntax import parse
from .logic import translate, LANGUAGE, PROCEDURE_LANGUAGE, REGRESSION

STATUSES = ("native-reconstructed", "bridged-executable", "retained-opaque", "approximated", "unsupported")
DIALECT = "fcst-network/1"
NAMESPACE = uuid.UUID("079aebc9-bbe6-56cc-87b7-7a9812d63b86")


class ExchangeError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def reject(code):
    raise ExchangeError(code)


@dataclass(frozen=True)
class Limits:
    files: int = 128
    file_bytes: int = 1048576
    total_bytes: int = 8388608
    line_bytes: int = 65536
    records: int = 10000
    include_depth: int = 32

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in self.__dict__.values()):
            reject("invalid_limits")


def path_name(name):
    try:
        return safe_path(name)
    except PersistenceError:
        reject("unsafe_path")


def checked_path(root, name):
    path_name(name)
    root = Path(root).absolute()
    path = root / name
    # Check every ancestor, including the declared root and Windows junctions.
    for item in (path, *path.parents):
        if is_link(item):
            reject("linked_path")
    if not path.resolve().is_relative_to(root.resolve()):
        reject("unsafe_path")
    if path.is_file() and path.stat().st_nlink != 1:
        reject("linked_path")
    return path


def preservation_check(root, sources, limits):
    """Prove the declared closure covers every file/directory of the source tree.

    Unknown content can name dependencies we cannot interpret. Never silently omit
    an undeclared sibling, and never follow it or copy unrelated data implicitly.
    """
    expected = {s.path for s in sources}
    directories = {str(parent) for name in expected for parent in PurePosixPath(name).parents if str(parent) != "."}
    files, dirs, pending, count = set(), set(), [(Path(root),0)], 0
    try:
        while pending:
            parent, depth = pending.pop()
            if depth > limits.include_depth:
                return "preservation_limit"
            with os.scandir(parent) as entries:
                for entry in entries:
                    count += 1
                    if count > limits.files*4:
                        return "preservation_limit"
                    path = Path(entry.path)
                    if is_link(path):
                        return "linked_path"
                    name = path.relative_to(root).as_posix()
                    path_name(name)
                    if entry.is_dir(follow_symlinks=False):
                        dirs.add(name)
                        pending.append((path,depth+1))
                    elif entry.is_file(follow_symlinks=False):
                        files.add(name)
                        if name not in expected:
                            return "undeclared_source_content"
                    else:
                        return "unsupported_source_entry"
    except (OSError,ExchangeError):
        return "preservation_unavailable"
    return "" if files == expected and dirs == directories else "undeclared_source_content"


def identity(namespace, handle):
    if not all(isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}", x) for x in (namespace, handle)):
        reject("source_identity")
    return namespace, handle


def target_id(key):
    return str(uuid.uuid5(NAMESPACE, json.dumps(key, separators=(",", ":"))))


@dataclass(frozen=True)
class Source:
    path: str
    content: bytes
    records: tuple
    role: str = "network"


@dataclass(frozen=True)
class ConversionPlan:
    profile: str
    operation: str
    source_revision: str
    supported: bool
    required_source_ids: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class Preview:
    root: Path
    entry: str
    dialect: str
    sources: tuple[Source, ...]
    report_bytes: bytes
    model_bytes: bytes | None

    @property
    def report(self):
        return json.loads(self.report_bytes)

    @property
    def model(self):
        return json.loads(self.model_bytes) if self.model_bytes is not None else None

    def require_native(self):
        if not self.report["runnable"]:
            reject("required_semantics_unresolved")
        return self.model

    def plan(self, operation):
        report = self.report
        selected = next((r for r in report["operations"] if r["operation"] == operation),None)
        if selected is None:
            reject("unsupported_operation")
        limitations = set(selected["limitations"])
        if not selected["supported"]:
            limitations.update(d["code"] for d in report["diagnostics"])
            limitations.update(code for r in report["records"] for code in r["limitations"])
        return ConversionPlan(self.dialect,operation,report["source_revision"],selected["supported"],
                              tuple(r["source_id"] for r in report["records"] if r["required"]),tuple(sorted(limitations)))


def _resolve(root, entry, limits):
    sources, graph, diagnostics = {}, {}, []
    aliases, total, record_count = {}, 0, 0
    def walk(name, stack, role="network"):
        nonlocal total, record_count
        path_name(name)
        for i in range(1, len(name.split("/"))+1):
            prefix = "/".join(name.split("/")[:i])
            if aliases.get(prefix.lower(), prefix) != prefix:
                reject("path_collision")
            aliases[prefix.lower()] = prefix
        if name in stack:
            reject("include_cycle")
        if len(stack) >= limits.include_depth:
            reject("include_depth")
        if name in sources:
            if sources[name].role != role:
                reject("dependency_role_collision")
            return
        if len(sources) >= limits.files:
            reject("file_count")
        path = checked_path(root, name)
        try:
            if not path.is_file():
                reject("missing_dependency")
            with path.open("rb") as stream:
                raw = stream.read(limits.file_bytes+1)
        except OSError:
            reject("source_unavailable")
        total += len(raw)
        if total > limits.total_bytes:
            reject("total_bytes")
        if len(raw) > limits.file_bytes:
            reject("file_limit")
        records = parse(name, raw, limits) if role == "network" else ()
        record_count += len(records)
        if record_count > limits.records:
            reject("record_limit")
        sources[name], graph[name] = Source(name, raw, records, role), set()
        for record in records:
            if record.kind not in {"INCLUDE", "RESULT", "DATA"} or record.code:
                continue
            value = record.value
            try:
                if set(value) != {"path"}:
                    reject("include_fields")
                child = str(PurePosixPath(name).parent / path_name(value["path"]))
                graph[name].add(child)
                walk(child, (*stack, name), {"INCLUDE":"network","RESULT":"result","DATA":"data"}[record.kind])
            except ExchangeError as error:
                diagnostics.append({"code":error.code, "source_id":record.source_id})
    walk(path_name(entry), ())
    # Catch cycles/depth through cached shared includes, independent of traversal order.
    if not diagnostics:
        try:
            dependency_order(graph, "include_depth")
            heights = {}
            for name in dependency_order(graph, "include_depth"):
                heights[name] = 1+max((heights[c] for c in graph[name]), default=0)
            if max(heights.values()) > limits.include_depth:
                reject("include_depth")
        except ContractError:
            reject("include_cycle_or_depth")
    return tuple(sources[k] for k in sorted(sources)), graph, diagnostics


def fidelity(record, status, *, category=None, target=None, code="", evidence=None):
    return {"source_id":record.source_id, "target_id":target,
            "category":category or {"INCLUDE":"dependency", "DATA":"dependency", "PROCEDURE":"procedure", "CASE":"case", "RESULT":"result"}.get(record.kind, "entity"),
            "operation":"import", "status":status, "required":True,
            "location":{"path":record.path, "line":record.line, "start":record.start, "end":record.end},
            "evidence":{"sha256":record.digest, "regressions":evidence or []}, "limitations":[code] if code else []}


def _convert(sources, graph, diagnostics):
    records = [r for source in sources for r in source.records if r.kind != "COMMENT"]
    rows, accepted, keys = [], [], {}
    for record in records:
        status, target, code = "native-reconstructed", None, record.code
        value = record.value
        if code:
            status = "retained-opaque" if record.kind == "OPAQUE" else "unsupported"
        else:
            try:
                if record.kind in {"ENTITY", "CASE", "MAPPING", "ATTACHMENT", "EXPRESSION", "PROCEDURE"}:
                    field = {"MAPPING":"mapping", "ATTACHMENT":"attachment"}.get(record.kind,"entity")
                    fields = {"namespace", "handle", field} if record.kind in {"ENTITY", "CASE", "MAPPING", "ATTACHMENT"} else {"namespace", "handle", "language", "text", "dimension"}
                    if set(value) != fields:
                        reject("unknown_fields")
                    key = identity(value["namespace"], value["handle"])
                    if key in keys:
                        reject("source_collision")
                    target = target_id(key)
                    keys[key] = target
                    accepted.append((record, key, target))
                elif record.kind == "INCLUDE":
                    problem = next((d for d in diagnostics if d["source_id"] == record.source_id), None)
                    if problem:
                        reject(problem["code"])
                    if set(value) != {"path"}:
                        reject("include_fields")
                elif record.kind in {"RESULT", "DATA"}:
                    if set(value) != {"path"}:
                        reject("result_fields")
                    path_name(value["path"])
                    problem = next((d for d in diagnostics if d["source_id"] == record.source_id), None)
                    if problem:
                        reject(problem["code"])
            except ExchangeError as error:
                status, code = "unsupported", error.code
        rows.append(fidelity(record, status, target=target, code=code))
    by_source = {r["source_id"]:r for r in rows}
    entities, entries, mappings, attachments = [], [], [], []
    expression_symbols = {}
    for record, (namespace, handle), target in accepted:
        if record.kind in {"EXPRESSION","PROCEDURE"} and handle.isidentifier():
            expression_symbols.setdefault(namespace,{})[handle] = target
    def references(value):
        if isinstance(value, dict):
            if "source_ref" in value:
                ref = value["source_ref"]
                if set(value) != {"source_ref"} or not isinstance(ref, list) or len(ref) != 2:
                    reject("source_reference")
                key = identity(*ref)
                if key not in keys:
                    reject("missing_reference")
                return keys[key]
            return {k:references(v) for k, v in value.items()}
        return [references(v) for v in value] if isinstance(value, list) else value
    for record, key, target in accepted:
        row, value = by_source[record.source_id], record.value
        try:
            if record.kind in {"EXPRESSION", "PROCEDURE"}:
                language = LANGUAGE if record.kind == "EXPRESSION" else PROCEDURE_LANGUAGE
                if value["language"] != language:
                    reject("unreviewed_language")
                symbols = expression_symbols.get(key[0],{})
                entity = {"id":target, "kind":"expression", "dimension":value["dimension"],
                          "ast":translate(value["text"], language, symbols)}
                row["evidence"]["regressions"] = [REGRESSION]
            else:
                field = {"MAPPING":"mapping", "ATTACHMENT":"attachment"}.get(record.kind,"entity")
                entity = references(value[field])
                if not isinstance(entity, dict) or "id" in entity or field == "entity" and "kind" not in entity:
                    reject("entity_fields")
                entity["id"] = target
                if record.kind == "CASE" and entity["kind"] != "case":
                    reject("case_kind")
            kind = {"MAPPING":"mapping", "ATTACHMENT":"attachment"}.get(record.kind,entity.get("kind"))
            if kind not in {*BUNDLE["entity_kinds"],"mapping","attachment"}:
                reject("entity_kind")
            schema = BUNDLE["schemas"]["model"]
            item_schema = schema["properties"]["mappings" if kind == "mapping" else "attachments"]["items"] if kind in {"mapping","attachment"} else schema["$defs"][kind]
            validate(item_schema, entity, schema)
            if kind == "case":
                row["category"] = "case"
            {"mapping":mappings,"attachment":attachments}.get(kind,entities).append(entity)
            if kind not in {"mapping","attachment"}:
                entries.append({"namespace":key[0], "handle":key[1], "entity_id":target})
        except (ExchangeError, ContractError, TypeError, KeyError, RecursionError) as error:
            row.update(status="retained-opaque" if record.kind == "PROCEDURE" else "unsupported", limitations=[error.code if isinstance(error, ExchangeError) else "entity_contract"])
    revision = sha256(encode([{ "path":s.path, "sha256":sha256(s.content).hexdigest()} for s in sources])).hexdigest()
    model = {"contract_version":"1.0.0", "minimum_reader":"1.0.0", "project_id":target_id(("project", revision)),
             "revision":0, "entities":entities, "source_maps":[{"id":target_id(("map", revision)), "version":"1.0.0",
             "source_revision":revision, "source_tool":DIALECT, "source_version":"1", "entries":entries}],
             "mappings":mappings, "attachments":attachments, "assumptions":[], "limitations":[], "audit":{"timestamp":"source-import"}, "gui":{"selection":[]}}
    try:
        model = read("model", loads(encode(model)))
    except (ContractError, TypeError, KeyError, RecursionError) as error:
        source_id = "model"
        if isinstance(error,ContractError):
            row = next((r for r in rows if r["target_id"] == error.diagnostic.entity_id and r["target_id"] is not None),None)
            if row:
                source_id = row["source_id"]
                row.update(status="unsupported",limitations=["model_"+error.diagnostic.code])
        diagnostics.append({"code":"model_contract", "source_id":source_id})
        model = None
    if model is not None:
        from .results import read_results
        data_files = {s.path:s.content for s in sources}
        try:
            for artifact in artifact_references(model):
                if artifact["path"] not in {s.path for s in sources if s.role == "data"}:
                    reject("artifact_unresolved")
                verify_artifact(artifact,data_files[artifact["path"]])
        except (ExchangeError, ContractError):
            diagnostics.append({"code":"artifact_unresolved_or_hash", "source_id":"model"})
        for record in records:
            if record.kind == "RESULT" and by_source[record.source_id]["status"] == "native-reconstructed":
                try:
                    name = str(PurePosixPath(record.path).parent / record.value["path"])
                    read_results(data_files[name], model)
                except (ExchangeError, KeyError):
                    by_source[record.source_id].update(status="unsupported", limitations=["result_contract"])
    for row in rows:
        if row["status"] == "unsupported":
            diagnostics.append({"code":row["limitations"][0], "source_id":row["source_id"]})
    runnable = model is not None and bool(entities) and not diagnostics and all(r["status"] == "native-reconstructed" for r in rows)
    operations = [
        {"operation":"native-reconstruction", "status":"native-reconstructed" if runnable else "unsupported", "supported":runnable},
        {"operation":"unchanged-export", "status":"retained-opaque", "supported":all(by_source[r.source_id]["status"] == "native-reconstructed" for r in records if r.kind in {"INCLUDE","RESULT","DATA"}) and all(v <= set(graph) for v in graph.values())},
        {"operation":"controlled-edit", "status":"native-reconstructed" if runnable else "unsupported", "supported":runnable},
        {"operation":"vendor-qualification", "status":"unsupported", "supported":False}]
    for operation in operations:
        operation.update(source_id="project",target_id=model["project_id"] if model else None,
                         profile=DIALECT,evidence={"source_revision":revision},
                         limitations=[] if operation["supported"] else ["operation_not_supported"])
    report = {"schema_version":"1.0.0", "adapter":DIALECT, "profile":DIALECT,
              "source_revision":revision, "runnable":runnable, "qualified":False,
              "records":rows, "operations":operations, "diagnostics":diagnostics,
              "dependencies":[{"path":k,"includes":sorted(v)} for k,v in sorted(graph.items())]}
    return report, model


def artifact_references(value):
    if isinstance(value, dict):
        if set(value) == {"path","sha256","byte_length"}:
            yield value
        else:
            for child in value.values():
                yield from artifact_references(child)
    elif isinstance(value,list):
        for child in value:
            yield from artifact_references(child)


def preview(root, entry, *, dialect, limits=Limits()):
    if dialect != DIALECT:
        reject("unsupported_dialect")
    sources, graph, diagnostics = _resolve(Path(root), entry, limits)
    report, model = _convert(sources, graph, diagnostics)
    preservation = preservation_check(Path(root).absolute(),sources,limits)
    if preservation:
        for operation in report["operations"]:
            if operation["operation"] in {"unchanged-export","controlled-edit"}:
                operation.update(supported=False,status="unsupported",limitations=[preservation])
    return Preview(Path(root).absolute(), entry, dialect, sources, encode(report), encode(model) if model else None)


class ReferenceAdapter:
    profile = DIALECT

    def probe(self):
        return {"profile":self.profile, "available":True, "runtime":"python-standard-library",
                "operations":["preview", "unchanged-export", "controlled-edit", "source-results"],
                "model_versions":["1.0.0"], "manifest_versions":["1.0.0", "2.0.0"],
                "spatial_versions":["2.0.0"], "vendor_qualified":False}

    def preview(self, root, entry, *, limits=Limits()):
        return preview(root, entry, dialect=self.profile, limits=limits)

    def read_foundation(self, kind, raw):
        if kind not in {"model", "manifest", "manifest2", "spatial"}:
            reject("unsupported_contract")
        try:
            return read(kind, loads(raw))
        except ContractError:
            reject("foundation_contract")


class Registry:
    """Explicit adapter objects supplied by trusted application code, never files."""
    def __init__(self, adapters=()):
        self._adapters = {}
        for adapter in adapters:
            if adapter.profile in self._adapters:
                reject("duplicate_adapter")
            self._adapters[adapter.profile] = adapter

    def discover(self):
        return [self._adapters[k].probe() for k in sorted(self._adapters)]

    def get(self, profile):
        if profile not in self._adapters:
            reject("adapter_unavailable")
        adapter = self._adapters[profile]
        if not adapter.probe()["available"]:
            reject("runtime_unavailable")
        return adapter
