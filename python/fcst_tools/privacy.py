# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded, fail-closed publication scanner. Never include matched values in reports."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "ci/publication-policy.json"
PATTERNS = {
    "personal_path": r"(?i)(?:[a-z]:[\\/]+(?:users|documents and settings)[\\/]+[^\s\\/]+|/(?:home|Users)/[^\s/]+)",
    "private_key": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    "credential": r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{20,})",
    "credential_url": r"(?i)https?://[^\s/@:]+:[^\s/@]+@",
    "internal_network": r"(?i)(?:\b(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|\b192\.168\.\d{1,3}\.\d{1,3}\b|\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b|\b[a-z0-9-]+\.(?:internal|local|corp)\b|\\\\[a-z0-9_-]+\\)",
    "contact": r"(?<![\w.+-])[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])",
    "phone": r"(?<!\d)(?:\+1[ .-]?)?\(\d{3}\)[ .-]?\d{3}[ .-]?\d{4}(?!\d)",
    "assigned_secret": r"(?i)\b(?:password|api_key|access_token|license_key)\s*[:=]\s*[\"']?[a-z0-9/+_=.-]{8,}",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError("git inspection unavailable")
    return result.stdout


class Scanner:
    def __init__(self, policy: dict):
        self.policy = policy
        self.findings: list[dict] = []
        self.items: list[dict] = []
        self.total = 0
        self.count = 0

    def finding(self, category: str, location: str) -> None:
        # Paths and archive entry names themselves can be sensitive.
        self.findings.append({"category": category, "location_id": sha(location.encode("utf-8"))[:20]})

    def text(self, value: str, location: str) -> None:
        for token in re.findall(r"[A-Za-z0-9_.-]+", value):
            if sha(token.casefold().encode()) in self.policy.get("private_term_hashes", []):
                self.finding("private_identifier", location)
                break
        for category, pattern in PATTERNS.items():
            for match in re.finditer(pattern, value):
                if category == "contact" and any(match.group() == identity["email"]
                                                 for identity in self.policy["approved_identities"]):
                    continue
                # Exceptions bind one complete content hash and one category.
                if any(item.get("sha256") == sha(value.encode()) and item.get("category") == category
                       for item in self.policy.get("exceptions", [])):
                    continue
                self.finding(category, location)
                break

    def scan(self, name: str, data: bytes, depth: int = 0) -> None:
        self.count += 1
        self.total += len(data)
        self.text(name, "path:" + name)
        path = PurePosixPath(name.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or any(p.casefold() in self.policy["denied_segments"] for p in path.parts):
            self.finding("restricted_or_unsafe_path", name)
        if (len(data) > self.policy["max_item_bytes"] or self.total > self.policy["max_total_bytes"]
                or self.count > self.policy["max_items"]):
            self.finding("inspection_limit", name)
            raise ValueError("inspection budget exceeded")
        self.items.append({"location_id": sha(name.encode())[:20], "sha256": sha(data), "bytes": len(data)})
        if data[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
            if depth >= self.policy["max_archive_depth"]:
                self.finding("archive_depth", name)
                return
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    for entry in archive.infolist():
                        if entry.is_dir():
                            continue
                        child = name + "!/" + entry.filename
                        member = PurePosixPath(entry.filename.replace("\\", "/"))
                        if member.is_absolute() or ".." in member.parts or re.match(r"^[A-Za-z]:", entry.filename):
                            self.finding("archive_traversal", child)
                        mode = entry.external_attr >> 16
                        if entry.flag_bits & 1 or mode & 0o170000 == 0o120000:
                            self.finding("encrypted_or_link", child)
                        elif entry.file_size > self.policy["max_item_bytes"]:
                            self.finding("inspection_limit", child)
                        else:
                            self.scan(child, archive.read(entry), depth + 1)
            except (OSError, RuntimeError, zipfile.BadZipFile):
                self.finding("unreadable_archive", name)
            return
        if path.suffix.lower() in {".tar", ".gz", ".tgz"}:
            if depth >= self.policy["max_archive_depth"]:
                self.finding("archive_depth", name)
                return
            try:
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
                    for entry in archive:
                        if entry.isdir():
                            continue
                        child = name + "!/" + entry.name
                        member = PurePosixPath(entry.name.replace("\\", "/"))
                        if member.is_absolute() or ".." in member.parts or re.match(r"^[A-Za-z]:", entry.name):
                            self.finding("archive_traversal", child)
                        if not entry.isfile():
                            self.finding("archive_link_or_special", child)
                        elif entry.size > self.policy["max_item_bytes"]:
                            self.finding("inspection_limit", child)
                        else:
                            stream = archive.extractfile(entry)
                            if stream is None:
                                self.finding("unreadable_archive", child)
                            else:
                                self.scan(child, stream.read(self.policy["max_item_bytes"] + 1), depth + 1)
            except (OSError, tarfile.TarError):
                self.finding("unreadable_archive", name)
            return
        if path.suffix.lower() not in self.policy["text_extensions"] and path.name not in self.policy["text_names"]:
            self.finding("unchecked_type", name)
            return
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            self.finding("unchecked_encoding", name)
            return
        if "\x00" in text:
            self.finding("binary_in_text", name)
            return
        self.text(text, name)

    def identity(self, name: str, email: str, location: str) -> None:
        if {"name": name, "email": email} not in self.policy["approved_identities"]:
            self.finding("unapproved_identity", location)

    def report(self) -> dict:
        items = sorted(self.items, key=lambda item: (item["location_id"], item["sha256"]))
        policy_hash = sha(json.dumps(self.policy, sort_keys=True, separators=(",", ":")).encode())
        payload_hash = sha(json.dumps(items, sort_keys=True, separators=(",", ":")).encode())
        return {"schema_version": 1, "status": "failed" if self.findings else "passed",
                "policy_version": self.policy["version"], "policy_sha256": policy_hash,
                "payload_sha256": payload_hash, "items": items, "findings": self.findings}


def inspect_git(scanner: Scanner, root: Path, revision: str | None, staged: bool) -> None:
    if staged:
        entries = git(root, "ls-files", "--stage", "-z")
        for record in entries.split(b"\0"):
            if not record:
                continue
            header, raw_name = record.split(b"\t", 1)
            mode, blob, stage = header.decode().split()
            name = raw_name.decode("utf-8")
            if mode not in {"100644", "100755"} or stage != "0":
                scanner.finding("link_submodule_or_unmerged", name)
                continue
            scanner.scan("index/" + name, git(root, "cat-file", "blob", blob))
    if revision:
        object_id = git(root, "rev-parse", "--verify", revision).decode().strip()
        for depth in range(scanner.policy["max_archive_depth"] + 1):
            kind = git(root, "cat-file", "-t", object_id).decode().strip()
            if kind != "tag":
                if kind != "commit":
                    scanner.finding("non_commit_publication_ref", "git-ref")
                break
            tag = git(root, "cat-file", "tag", object_id)
            scanner.scan(object_id + "/tag.txt", tag)
            match = re.search(rb"^tagger (.+) <([^>]+)> ", tag, re.M)
            if not match:
                scanner.finding("missing_tag_identity", object_id)
            else:
                scanner.identity(match[1].decode(), match[2].decode(), object_id + "/tagger")
            object_id = tag.splitlines()[0].decode().split(" ", 1)[1]
        else:
            raise ValueError("tag nesting exceeded")
        commits = git(root, "rev-list", revision, "--").decode().splitlines()
        if len(commits) > scanner.policy["max_items"]:
            raise ValueError("history inspection budget exceeded")
        for commit in commits:
            metadata = git(root, "show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", commit).decode("utf-8")
            author, email, committer, committer_email, message = metadata.split("\x00", 4)
            scanner.identity(author, email, commit + "/author")
            scanner.identity(committer, committer_email, commit + "/committer")
            scanner.scan(commit + "/commit.txt", git(root, "cat-file", "commit", commit))
            for record in git(root, "ls-tree", "-rz", commit).split(b"\0"):
                if not record:
                    continue
                header, raw_name = record.split(b"\t", 1)
                mode, kind, blob = header.decode().split()
                name = raw_name.decode("utf-8")
                if kind != "blob" or mode not in {"100644", "100755"}:
                    scanner.finding("link_or_submodule", commit + "/" + name)
                    continue
                scanner.scan(commit + "/" + name, git(root, "cat-file", "blob", blob))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--revision", help="Inspect all ancestors and their complete trees")
    parser.add_argument("--file", type=Path, action="append", default=[])
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-clearance", type=Path)
    args = parser.parse_args(argv)
    scanner = Scanner(json.loads(args.policy.read_text(encoding="utf-8")))
    try:
        if not (args.staged or args.revision or args.file):
            raise ValueError("no outgoing content selected")
        inspect_git(scanner, args.root, args.revision, args.staged)
        for path in args.file:
            if path.is_symlink():
                scanner.finding("symlink", path.name)
            else:
                if path.stat().st_size > scanner.policy["max_item_bytes"]:
                    scanner.finding("inspection_limit", path.name)
                else:
                    scanner.scan(path.name, path.read_bytes())
        report = scanner.report()
        if args.verify_clearance:
            prior = json.loads(args.verify_clearance.read_text(encoding="utf-8"))
            if prior != report or prior["status"] != "passed":
                scanner.finding("clearance_mismatch", "clearance")
                report = scanner.report()
    except (ValueError, OSError, subprocess.SubprocessError, UnicodeError, KeyError, TypeError):
        scanner.finding("inspection_unavailable", "publication")
        report = scanner.report()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "items"}, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
