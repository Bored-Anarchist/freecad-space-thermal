# SPDX-License-Identifier: MIT OR Apache-2.0
"""Cache pristine public distributions only; never upload build trees or pip metadata.

Clearance requires actual bytes to match reviewed upstream distribution hashes.
This is not clearance for generated binaries, arbitrary archives or test evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".local/public-download-cache"


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            checksum.update(block)
    return checksum.hexdigest()


def no_links(path):
    for parent in (path, *path.parents):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("download_cache_link")


def regular(path):
    no_links(path)
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("download_cache_file")


def wheel_hashes(locks):
    result = {}
    for lock in locks:
        current = None
        for line in lock.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            pin = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)\s*\\?", line)
            if pin:
                current = (re.sub(r"[-_.]+", "-", pin[1]).lower(), pin[2])
                result.setdefault(current, set())
            else:
                match = re.fullmatch(r"\s+--hash=sha256:([0-9a-f]{64})\s*\\?", line)
                if current is None or match is None:
                    raise ValueError("download_cache_lock")
                result[current].add(match[1])
    if not result or any(not hashes for hashes in result.values()):
        raise ValueError("download_cache_lock")
    return result


def public_archives(root):
    """Only original upstream artifacts named in reviewed project locks."""
    entries = []
    def add(path, item):
        entries.append((path, item["sha256"], item.get("bytes")))
    for item in json.loads((root / "ci/probe-sources.json").read_bytes())["sources"]:
        add(root / ".local/profile-downloads" / (item["id"] + ".tar.gz"), item)
    host = json.loads((root / "ci/host-profile.json").read_bytes())["platforms"]["Windows"]
    add(root / ".local/profile-downloads" / host["asset"], host)
    dwg = json.loads((root / "ci/dwg-backend.json").read_bytes())
    for key in ("source", "compiler"):
        item = dwg[key]
        add(root / ".local/dwg-backend/downloads" / item["filename"], item)
    reference = json.loads((root / "ci/pycanha-reference-runtime.json").read_bytes())
    add(root / ".local/pycanha-wheelhouse/python-3.13.2-embed-amd64.zip", reference["python"])
    add(root / ".local/pycanha-wheelhouse/pip-25.0.1-py3-none-any.whl", reference["bootstrap_pip"])
    for item in reference["wheels"]:
        add(root / ".local/pycanha-wheelhouse" / item["filename"], item)
    if any(not re.fullmatch("[0-9a-f]{64}", value) for _, value, _ in entries):
        raise ValueError("download_cache_registry")
    return entries


def validate(cache, locks, archives):
    no_links(cache)
    wheels = wheel_hashes(locks)
    objects = {value: size for _, value, size in archives}
    if not cache.exists():
        return
    if not cache.is_dir():
        raise ValueError("download_cache_root")
    for path in cache.rglob("*"):
        if path.is_dir():
            if path.relative_to(cache).as_posix() not in {"wheels", "objects"}:
                raise ValueError("download_cache_directory")
            regular_directory = path.stat()
            if path.is_symlink() or getattr(regular_directory, "st_file_attributes", 0) & 0x400:
                raise ValueError("download_cache_link")
            continue
        regular(path)
        parts = path.relative_to(cache).parts
        if len(parts) != 2:
            raise ValueError("download_cache_layout")
        actual = digest(path)
        if parts[0] == "wheels":
            match = re.fullmatch(r"([A-Za-z0-9_.]+)-([A-Za-z0-9_.+]+)-[A-Za-z0-9_.+-]+\.whl", path.name)
            if match is None:
                raise ValueError("download_cache_wheel")
            pin = (re.sub(r"[-_.]+", "-", match[1]).lower(), match[2])
            if actual not in wheels.get(pin, set()):
                raise ValueError("download_cache_wheel_hash")
        elif parts[0] == "objects" and path.name in objects:
            if actual != path.name or (objects[path.name] is not None and path.stat().st_size != objects[path.name]):
                raise ValueError("download_cache_object_hash")
        else:
            raise ValueError("download_cache_unlisted")


def restore(cache, archives):
    for destination, value, size in archives:
        source = cache / "objects" / value
        if not source.exists():
            continue
        no_links(destination)
        if destination.exists():
            regular(destination)
            if digest(destination) != value:
                raise ValueError("download_cache_destination_changed")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            # No archive is extracted or executable launched by this tool.
            shutil.copyfile(source, destination)


def seal(cache, locks, archives):
    validate(cache, locks, archives)
    for source, value, size in archives:
        if not source.exists():
            continue
        regular(source)
        if digest(source) != value or (size is not None and source.stat().st_size != size):
            raise ValueError("download_cache_source_changed")
        destination = cache / "objects" / value
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(source, destination)
    validate(cache, locks, archives)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "seal"))
    parser.add_argument("--lock", action="append", type=Path, required=True)
    args = parser.parse_args()
    locks = [(ROOT / path).resolve() for path in args.lock]
    if any(path.parent != ROOT / "ci" or path.suffix != ".lock" for path in locks):
        raise ValueError("download_cache_lock_path")
    archives = public_archives(ROOT)
    if args.operation == "prepare":
        validate(CACHE, locks, archives)
        restore(CACHE, archives)
        (CACHE / "wheels").mkdir(parents=True, exist_ok=True)
        command = [sys.executable, "-m", "pip", "download", "--disable-pip-version-check",
                   "--no-cache-dir", "--require-hashes", "--only-binary=:all:", "--dest", str(CACHE / "wheels"),
                   "--find-links", str(CACHE / "wheels")]
        for lock in locks:
            command.extend(["-r", str(lock)])
        with (ROOT / ".local/download-tooling.log").open("wb") as log:
            # A complete restored wheelhouse resolves without any index requests.
            offline = subprocess.run([*command, "--no-index"],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=300)
            if offline.returncode:
                subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
        validate(CACHE, locks, archives)
    else:
        seal(CACHE, locks, archives)
    print("Public download cache: cleared")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError):
        print("Public download cache: failed; raw details retained locally")
        raise SystemExit(1)
