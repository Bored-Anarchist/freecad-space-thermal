# SPDX-License-Identifier: MIT OR Apache-2.0
"""Portable, bounded data packages and recoverable same-filesystem publication.

No archive member is extracted and no imported object is executed. See
docs/persistence.md for the managed expanded-directory and recovery contracts.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import stat
import uuid
import zipfile

from fcst_contracts import VERSION, loads, read, snapshot, canonical, verify_artifact


class PersistenceError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def reject(code):
    raise PersistenceError(code)


def is_link(path):
    # Python 3.11 has no Path.is_junction(). Include every Windows reparse point.
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return False


def encode(value):
    def numbers(item):
        if isinstance(item, float) and item.is_integer() and abs(item) <= 9007199254740991:
            return int(item)
        if isinstance(item, dict):
            return {k: numbers(v) for k, v in item.items()}
        if isinstance(item, list):
            return [numbers(v) for v in item]
        return item
    return json.dumps(numbers(value), sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def semantic_hash(model):
    return sha256(b"FCST-semantic-v1\0" + canonical(snapshot(model))).hexdigest()


def safe_path(name):
    if not isinstance(name, str) or len(name) > 240 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", name):
        reject("unsafe_path")
    reserved = {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}
    if any(p in ("", ".", "..") or p.endswith((".", " ")) or p.split(".")[0].upper() in reserved
           for p in name.split("/")):
        reject("unsafe_path")
    return name


@dataclass(frozen=True)
class Limits:
    items: int = 2048
    item_bytes: int = 64 * 1024 * 1024
    total_bytes: int = 256 * 1024 * 1024
    compression_ratio: int = 200


def _check_members(files, limits):
    if not files or len(files) > limits.items:
        reject("package_limit")
    seen = set()
    prefixes = {}
    for name, data in files.items():
        safe_path(name)
        if name.lower() in seen or len(data) > limits.item_bytes:
            reject("package_limit")
        seen.add(name.lower())
        for i in range(1, len(name.split("/")) + 1):
            prefix = "/".join(name.split("/")[:i])
            if prefixes.get(prefix.lower(), prefix) != prefix:
                reject("path_collision")
            prefixes[prefix.lower()] = prefix
    if sum(map(len, files.values())) > limits.total_bytes:
        reject("package_limit")
    # A file cannot also be a parent directory, including Windows case aliases.
    if any("/".join(n.split("/")[:i]).lower() in seen
           for n in files for i in range(1, len(n.split("/")))):
        reject("path_collision")


class Package:
    def __init__(self, manifest, files, *, limits=Limits(), check_arrays=True):
        self.manifest = read("manifest", manifest)
        self.files = dict(files)
        self.limits = limits
        _check_members({"manifest.json": encode(self.manifest), **self.files}, limits)
        records = self.manifest["artifacts"]
        expected = {r["artifact"]["path"] for r in records}
        if set(self.files) != expected or "manifest.json" in expected:
            reject("dependency_closure")
        for record in records:
            ref = record["artifact"]
            verify_artifact(ref, self.files[ref["path"]])
        model_record = next(r for r in records if r["id"] == self.manifest["model_artifact_id"])
        self.model = read("model", loads(self.files[model_record["artifact"]["path"]]))
        if any(self.manifest[k] != self.model[k] for k in ("project_id", "revision")):
            reject("snapshot_mismatch")
        refs = {r["artifact"]["path"]: r["artifact"] for r in records}
        def inspect(value):
            if isinstance(value, dict):
                if set(value) == {"path", "sha256", "byte_length"} and refs.get(value["path"]) != value:
                    reject("dependency_closure")
                for child in value.values():
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)
        inspect(self.model)
        for record in records:
            name = record["artifact"]["path"]
            suffix = Path(name).suffix.lower()
            # Original sources are inert exact bytes, regardless of their suffix.
            if record["role"] in {"source_original", "source_dependency"}:
                continue
            if record["role"] == "mesh" and suffix not in {".h5", ".hdf5"}:
                reject("storage_format")
            if record["role"] == "result" and suffix not in {".json", ".h5", ".hdf5"}:
                reject("storage_format")
            if suffix in {".h5", ".hdf5"}:
                if not check_arrays:
                    reject("array_validation_required")
                from .arrays import validate_arrays
                validate_arrays(self.files[name], limits.item_bytes)
            if record["role"] == "result" and suffix == ".json":
                read("result", loads(self.files[name]))
            if record["role"] in {"audit", "evidence"}:
                if suffix != ".json":
                    reject("storage_format")
                loads(self.files[name])
        if "audit/state.json" in self.files:
            from .store import validate_state
            state = loads(self.files["audit/state.json"])
            validate_state(state, self.model)
            if state["model_artifact_id"] != self.manifest["model_artifact_id"]:
                reject("invalid_journal")

    @classmethod
    def create(cls, model, artifacts=(), *, state=None, model_artifact_id=None):
        model = read("model", model)
        model_id = model_artifact_id or (state or {}).get("model_artifact_id") or str(uuid.uuid5(uuid.UUID(model["project_id"]), "fcst:model"))
        entries = [(model_id, "model", "model/snapshot.json", encode(model), [])]
        entries.extend(artifacts)
        if state is not None:
            entries.append((str(uuid.uuid5(uuid.UUID(model["project_id"]), "fcst:state")),
                            "audit", "audit/state.json", encode(state), []))
        records, files = [], {}
        for artifact_id, role, name, data, dependencies in entries:
            if name in files:
                reject("path_collision")
            files[name] = bytes(data)
            records.append({"id": artifact_id, "role": role, "dependencies": list(dependencies),
                            "artifact": {"path": name, "sha256": sha256(data).hexdigest(), "byte_length": len(data)}})
        return cls({"contract_version": VERSION, "minimum_reader": VERSION, "project_id": model["project_id"],
                    "revision": model["revision"], "model_artifact_id": model_id, "artifacts": records}, files)

    def zip_bytes(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, data in sorted({"manifest.json": encode(self.manifest), **self.files}.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, data)
        return output.getvalue()

    @classmethod
    def from_zip(cls, raw, *, limits=Limits()):
        if len(raw) > limits.total_bytes + limits.items * 512:
            reject("package_limit")
        files, seen, total, directories = {}, set(), 0, set()
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                members = archive.infolist()
                if len(members) > limits.items:
                    reject("package_limit")
                for member in members:
                    name = safe_path(member.filename[:-1] if member.is_dir() else member.filename)
                    mode = member.external_attr >> 16
                    if (member.flag_bits & 1 or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)
                            or member.external_attr & 0x400):
                        reject("unsafe_member")
                    if member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                        reject("unsupported_compression")
                    if name.lower() in seen:
                        reject("path_collision")
                    seen.add(name.lower())
                    if member.is_dir():
                        if member.file_size:
                            reject("unsafe_member")
                        directories.add(name)
                        continue
                    if stat.S_IFMT(mode) == stat.S_IFDIR:
                        reject("unsafe_member")
                    total += member.file_size
                    if (member.file_size > limits.item_bytes or total > limits.total_bytes
                            or member.file_size > max(1, member.compress_size) * limits.compression_ratio):
                        reject("package_limit")
                    with archive.open(member) as stream:
                        data = stream.read(limits.item_bytes + 1)
                    if len(data) != member.file_size:
                        reject("package_limit")
                    files[name] = data
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError):
            reject("invalid_archive")
        _check_members({**files, **{name + "/directory-marker": b"" for name in directories}}, limits)
        if "manifest.json" not in files:
            reject("missing_manifest")
        return cls(loads(files.pop("manifest.json")), files, limits=limits)

    @classmethod
    def open(cls, path, *, limits=Limits()):
        path = Path(path)
        if is_link(path):
            reject("unsafe_member")
        if path.is_file():
            if path.stat().st_nlink > 1:
                reject("unsafe_member")
            if path.stat().st_size > limits.total_bytes + limits.items * 512:
                reject("package_limit")
            return cls.from_zip(path.read_bytes(), limits=limits)
        if not path.is_dir():
            reject("missing_package")
        if (path / "HEAD.json").exists():
            if is_link(path / "HEAD.json") or (path / "HEAD.json").stat().st_size > 4096:
                reject("invalid_head")
            pointer = loads((path / "HEAD.json").read_bytes())
            generation = pointer.get("generation", "")
            if not re.fullmatch(r"[a-f0-9]{32}", generation):
                reject("invalid_head")
            base = path / "revisions" / generation
            if is_link(base) or is_link(path / "revisions"):
                reject("unsafe_member")
        else:
            base = path
        files = {}
        visited_entries = 0
        def walk(directory, depth=0):
            nonlocal visited_entries
            if depth > 32:
                reject("package_limit")
            for child in directory.iterdir():
                visited_entries += 1
                if visited_entries > limits.items + 32:
                    reject("package_limit")
                safe_path(child.relative_to(base).as_posix())
                if is_link(child):
                    reject("unsafe_member")
                if child.is_dir():
                    walk(child, depth + 1)
                elif child.is_file():
                    name = child.relative_to(base).as_posix()
                    safe_path(name)
                    if child.stat().st_nlink > 1:
                        reject("unsafe_member")
                    if child.stat().st_size > limits.item_bytes or len(files) >= limits.items:
                        reject("package_limit")
                    files[name] = child.read_bytes()
                    if sum(map(len, files.values())) > limits.total_bytes:
                        reject("package_limit")
                else:
                    reject("unsafe_member")
        walk(base)
        _check_members(files, limits)
        if "manifest.json" not in files:
            reject("missing_manifest")
        if base != path and sha256(files["manifest.json"]).hexdigest() != pointer.get("manifest_sha256"):
            reject("invalid_head")
        return cls(loads(files.pop("manifest.json")), files, limits=limits)


def _fault(hook, point):
    if hook:
        hook(point)


def replace(source, target):
    """Atomic name replacement, requesting write-through on the Windows target."""
    if os.name == "nt":
        import ctypes
        function = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        function.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
        function.restype = ctypes.c_int
        if not function(str(Path(source).absolute()), str(Path(target).absolute()), 0x9):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.replace(source, target)
        fd = os.open(Path(target).parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def durable_write(path, data, hook=None):
    with Path(path).open("xb") as stream:
        stream.write(data)
        _fault(hook, "write")
        stream.flush()
        _fault(hook, "flush")
        os.fsync(stream.fileno())
        _fault(hook, "fsync")


def atomic_file(path, data):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    durable_write(temporary, data)
    replace(temporary, path)


@contextmanager
def publication_lock(path):
    lock = Path(path).with_name(Path(path).name + ".lock")
    if is_link(lock) or lock.exists() and lock.stat().st_nlink > 1:
        reject("unsafe_target")
    with lock.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            reject("save_busy")
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def save_package(package, path, *, expanded=False, fault=None):
    with publication_lock(path):
        return _save_package(package, path, expanded=expanded, fault=fault)


def _save_package(package, path, *, expanded=False, fault=None):
    """Return only after verification/publication; prior generations are retained.

    An exception after replace means recovery must inspect the committed target.
    This function never returns a clean receipt on an uncertain save.
    """
    path = Path(path)
    # Revalidate the exact bytes even if the caller mutated a Package instance.
    package = Package(package.manifest, package.files, limits=package.limits)
    if is_link(path):
        reject("unsafe_target")
    if expanded:
        path.mkdir(exist_ok=True)
        marker = path / "FORMAT.json"
        if any(path.iterdir()) and not marker.is_file():
            reject("unmanaged_directory")
        if marker.exists():
            if is_link(marker) or marker.stat().st_size > 4096 or loads(marker.read_bytes()) != {"storage_layout": 1}:
                reject("unmanaged_directory")
        else:
            atomic_file(marker, encode({"storage_layout": 1}))
        if (path / "HEAD.json").exists():
            Package.open(path)
        revisions = path / "revisions"
        revisions.mkdir(exist_ok=True)
        if is_link(revisions):
            reject("unsafe_target")
        generation = uuid.uuid4().hex
        stage = revisions / generation
        stage.mkdir()
        for name, data in {"manifest.json": encode(package.manifest), **package.files}.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            durable_write(target, data, fault)
        Package.open(stage)
        _fault(fault, "verify")
        pointer = {"generation": generation, "manifest_sha256": sha256(encode(package.manifest)).hexdigest()}
        head = path / "HEAD.json"
        if head.exists():
            atomic_file(path / "PREVIOUS.json", head.read_bytes())
        _fault(fault, "backup")
        atomic_file(path / "SAVE.json", encode({"state": "prepared", **pointer}))
        _fault(fault, "journal")
        atomic_file(head, encode(pointer))
        _fault(fault, "replace")
        Package.open(path)
        _fault(fault, "sync")
        atomic_file(path / "SAVE.json", encode({"state": "committed", **pointer}))
    else:
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        durable_write(temporary, package.zip_bytes(), fault)
        Package.open(temporary)
        _fault(fault, "verify")
        if path.exists():
            Package.open(path)
            atomic_file(path.with_name(path.name + ".previous"), path.read_bytes())
        _fault(fault, "backup")
        journal = path.with_name(path.name + ".save.json")
        payload = {"state": "prepared", "revision": package.model["revision"],
                   "package_sha256": sha256(temporary.read_bytes()).hexdigest()}
        atomic_file(journal, encode(payload))
        _fault(fault, "journal")
        replace(temporary, path)
        _fault(fault, "replace")
        Package.open(path)
        _fault(fault, "sync")
        atomic_file(journal, encode({**payload, "state": "committed"}))
    return {"revision": package.model["revision"], "semantic_hash": semantic_hash(package.model), "state": "committed"}


def recover_package(path, *, previous=False):
    """Inspect a valid committed/prior snapshot without promoting staged data."""
    path = Path(path)
    if not previous:
        return Package.open(path)
    if path.is_dir():
        if (is_link(path) or is_link(path / "revisions") or is_link(path / "PREVIOUS.json")
                or (path / "PREVIOUS.json").stat().st_size > 4096):
            reject("invalid_head")
        pointer = loads((path / "PREVIOUS.json").read_bytes())
        generation = pointer.get("generation", "")
        if not re.fullmatch(r"[a-f0-9]{32}", generation):
            reject("invalid_head")
        candidate = path / "revisions" / generation
        package = Package.open(candidate)
        if sha256((candidate / "manifest.json").read_bytes()).hexdigest() != pointer.get("manifest_sha256"):
            reject("invalid_head")
        return package
    return Package.open(path.with_name(path.name + ".previous"))


def migrate_legacy(document):
    """Explicit fixture-defined 0.9 envelope -> v1; reject every unknown legacy key."""
    if set(document) != {"storage_version", "snapshot"} or document["storage_version"] != "0.9":
        reject("unsupported_migration")
    model = deepcopy(document["snapshot"])
    if model.get("contract_version") != "0.9" or model.get("minimum_reader") != "0.9":
        reject("unsupported_migration")
    model.update(contract_version=VERSION, minimum_reader=VERSION)
    return Package.create(model)


def downgrade_export(package, version):
    # Deliberately narrow, lossless model-only interchange. Never discard artifacts/audit.
    if version != "0.9" or len(package.files) != 1:
        reject("unsupported_downgrade")
    model = deepcopy(package.model)
    model.update(contract_version="0.9", minimum_reader="0.9")
    return encode({"storage_version": "0.9", "snapshot": model})


def migrate_project(source, destination, *, fault=None):
    """Retain the exact legacy input as an inert source artifact in a new package."""
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or destination.exists():
        reject("migration_requires_new_target")
    if source.stat().st_size > 1048576:
        reject("package_limit")
    raw = source.read_bytes()
    upgraded = migrate_legacy(loads(raw))
    package = Package.create(upgraded.model, [(str(uuid.uuid4()), "source_original", "sources/migration-input.json", raw, [])])
    return save_package(package, destination, fault=fault)
