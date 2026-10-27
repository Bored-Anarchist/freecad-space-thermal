# SPDX-License-Identifier: MIT OR Apache-2.0
"""Hash-locked downloads and bounded local process logs for foundation probes."""
from __future__ import annotations
import hashlib
import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


class ProbeFailure(ValueError):
    def __init__(self, stage, reason="process_failure"):
        super().__init__("Probe failed; raw output retained locally")
        self.stage = stage
        self.reason = reason


def verified_download(url, destination, size, digest):
    if (urlsplit(url).scheme != "https" or urlsplit(url).hostname not in
            {"github.com", "codeload.github.com"} or len(digest) != 64 or not 0 < size < 1024 ** 3):
        raise ValueError("Invalid source lock")
    destination = Path(destination)
    if destination.exists():
        if destination.stat().st_size == size and hashlib.sha256(destination.read_bytes()).hexdigest() == digest:
            return destination
        raise ValueError("Cached source does not match lock")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    checksum = hashlib.sha256()
    count = 0
    with urlopen(url, timeout=180) as response, temporary.open("wb") as stream:
        if urlsplit(response.geturl()).scheme != "https":
            raise ValueError("Insecure download redirect")
        while block := response.read(1024 * 1024):
            count += len(block)
            if count > size:
                raise ValueError("Source exceeds locked size")
            checksum.update(block)
            stream.write(block)
    if count != size or checksum.hexdigest() != digest:
        raise ValueError("Source hash mismatch")
    temporary.replace(destination)
    return destination


def cmake_tools():
    import cmake
    suffix = ".exe" if os.name == "nt" else ""
    return tuple(str(Path(cmake.CMAKE_BIN_DIR) / (name + suffix)) for name in ("cmake", "ctest"))


def revision():
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=15)
    value = result.stdout.strip()
    if result.returncode or len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Candidate revision unavailable")
    return value


def run(command, directory, log, env=None, timeout=1800):
    with Path(log).open("wb") as output:
        process = subprocess.run(command, cwd=directory, stdout=output, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, env=env, timeout=timeout)
    if process.returncode:
        text = Path(log).read_text(encoding="utf-8", errors="replace").lower()
        reason = "process_failure"
        if "blas" in text and any(token in text for token in ("could not find", "unable to find", "cannot find")):
            reason = "blas_lapack_unavailable"
        elif "no targets specified and no makefile found" in text:
            reason = "installed_makefile_unavailable"
        elif "target was not found" in text:
            reason = "exported_target_unavailable"
        raise ProbeFailure(Path(log).stem, reason)
