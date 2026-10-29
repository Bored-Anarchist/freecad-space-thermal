# SPDX-License-Identifier: MIT OR Apache-2.0
"""Trusted Windows converters, bounded trees/resources, explicit authorization.

The working root is an input/output boundary, not an OS filesystem sandbox.
Only application-reviewed tools may be registered. Imported text has no authority.
"""
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import threading
import time
import math

from fcst_app.persistence import is_link
from fcst_app.process_limits import WorkerLimits
from .core import Limits, checked_path, path_name, reject


@dataclass(frozen=True)
class Tool:
    profile: str
    executable: Path
    executable_sha256: str
    arguments: tuple[str, ...]
    # Absolute trusted scripts/data that appear in fixed argv need their own seals.
    assets: tuple[tuple[Path, str], ...] = ()
    timeout_seconds: float = 30
    memory_mb: int = 256
    output_bytes: int = 1048576


@dataclass(frozen=True)
class Authorization:
    profile: str
    operation: str
    decision_id: str


class ToolRunner:
    def __init__(self, tools=()):
        self.tools = {}
        for tool in tools:
            if tool.profile in self.tools:
                reject("duplicate_tool")
            if (not tool.executable.is_absolute() or tool.executable.suffix.lower() != ".exe"
                    or not math.isfinite(tool.timeout_seconds) or tool.timeout_seconds <= 0
                    or type(tool.memory_mb) is not int or not 16 <= tool.memory_mb <= 16384
                    or type(tool.output_bytes) is not int or tool.output_bytes <= 0):
                reject("invalid_tool")
            self.tools[tool.profile] = tool

    def probe(self, profile):
        tool = self.tools.get(profile)
        if tool is None:
            reject("tool_unregistered")
        for path, digest in ((tool.executable, tool.executable_sha256), *tool.assets):
            if not path.is_absolute() or not path.is_file() or any(is_link(p) for p in (path,*path.parents)):
                reject("tool_unavailable")
            # Trusted installed binaries can exceed source-model byte limits.
            with path.open("rb") as stream:
                if sha256_stream(stream) != digest:
                    reject("tool_hash")
        return tool

    def run(self, profile, root, inputs, outputs, authorization, *, limits=Limits()):
        if (not isinstance(authorization, Authorization) or authorization.profile != profile
                or authorization.operation != "convert" or not authorization.decision_id):
            reject("tool_authorization")
        tool = self.probe(profile)
        if os.name != "nt":
            reject("unsupported_tool_platform")
        root = Path(root).absolute()
        if root.exists() or not root.parent.is_dir() or any(is_link(p) for p in (root,*root.parents)):
            reject("tool_requires_new_root")
        # Only declared immutable bytes enter the root; no arbitrary source argv.
        if not inputs or len(inputs) > limits.files or sum(len(b) for b in inputs.values()) > limits.total_bytes:
            reject("tool_input_limit")
        seen = set()
        for name, raw in inputs.items():
            path_name(name)
            if not isinstance(raw, bytes) or len(raw) > limits.file_bytes or name.lower() in seen:
                reject("tool_input_limit")
            seen.add(name.lower())
        outputs = tuple(outputs)
        if not outputs or len(outputs) > limits.files:
            reject("tool_output_limit")
        for name in outputs:
            path_name(name)
            if name.lower() in seen:
                reject("tool_output_collision")
            seen.add(name.lower())
        root.mkdir()
        for name, raw in inputs.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        environment = {k:v for k,v in os.environ.items() if k.upper() in {"SYSTEMROOT","WINDIR"}}
        environment.update(TEMP=str(root), TMP=str(root), PATH=str(tool.executable.parent),
                           OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        process = subprocess.Popen([str(tool.executable), *tool.arguments], cwd=root, env=environment,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=0x4 | subprocess.CREATE_NO_WINDOW)
        containment, readers = None, []
        exceeded, counter, lock = threading.Event(), [0], threading.Lock()
        def drain(pipe):
            try:
                while chunk := pipe.read(4096):
                    with lock:
                        counter[0] += len(chunk)
                        if counter[0] > tool.output_bytes:
                            exceeded.set()
                    # Discard all raw stdout/stderr; never include it in public evidence.
            except OSError:
                exceeded.set()
        code = ""
        try:
            containment = WorkerLimits(process, tool.memory_mb)
            for pipe in (process.stdout,process.stderr):
                reader = threading.Thread(target=drain, args=(pipe,), daemon=True)
                reader.start()
                readers.append(reader)
            deadline = time.monotonic()+tool.timeout_seconds
            while process.poll() is None:
                if exceeded.is_set():
                    code = "tool_log_limit"
                    break
                if time.monotonic() >= deadline:
                    code = "tool_timeout"
                    break
                if not bounded_tree(root,limits):
                    code = "tool_output_limit"
                    break
                time.sleep(.01)
            if process.poll() is None:
                containment.close()
            process.wait(timeout=10)
        finally:
            if containment:
                containment.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            for reader in readers:
                reader.join(timeout=5)
            process.stdout.close()
            process.stderr.close()
        if exceeded.is_set():
            code = "tool_log_limit"
        if code:
            reject(code)
        if process.returncode:
            reject("tool_failed")
        result, total = {}, 0
        # Reject undeclared output, reparses, input modification and oversized files.
        actual = set()
        for path in root.rglob("*"):
            if is_link(path):
                reject("linked_path")
            if path.is_file():
                name = path.relative_to(root).as_posix()
                actual.add(name)
                if len(actual) > limits.files*2 or name not in {*inputs, *outputs}:
                    reject("undeclared_tool_output")
        if actual != {*inputs, *outputs}:
            reject("tool_output_missing")
        for name in sorted(actual):
            with checked_path(root,name).open("rb") as stream:
                raw = stream.read(limits.file_bytes+1)
            total += len(raw)
            if len(raw) > limits.file_bytes or total > limits.total_bytes:
                reject("tool_output_limit")
            if name in inputs and raw != inputs[name]:
                reject("tool_modified_input")
            if name in outputs:
                result[name] = raw
        return result, {"profile":profile,"operation":"convert", "status":"bridged-executable",
                        "tool_sha256":tool.executable_sha256,
                        "asset_sha256":[digest for _,digest in tool.assets],
                        "authorization_sha256":sha256(authorization.decision_id.encode()).hexdigest(),
                        "outputs":[{"path":p,"sha256":sha256(b).hexdigest(),"byte_length":len(b)} for p,b in sorted(result.items())]}


def sha256_stream(stream):
    digest = sha256()
    while block := stream.read(1048576):
        digest.update(block)
    return digest.hexdigest()


def bounded_tree(root, limits):
    pending, count, total = [(root,0)], 0, 0
    try:
        while pending:
            parent, depth = pending.pop()
            if depth > limits.include_depth:
                return False
            with os.scandir(parent) as entries:
                for entry in entries:
                    count += 1
                    if count > limits.files*4 or is_link(Path(entry.path)):
                        return False
                    if entry.is_dir(follow_symlinks=False):
                        pending.append((entry.path,depth+1))
                    elif entry.is_file(follow_symlinks=False):
                        size = entry.stat(follow_symlinks=False).st_size
                        total += size
                        if size > limits.file_bytes or total > limits.total_bytes:
                            return False
                    else:
                        return False
    except OSError:
        return False
    return True
