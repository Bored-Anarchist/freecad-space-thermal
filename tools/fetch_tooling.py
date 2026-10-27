# SPDX-License-Identifier: MIT OR Apache-2.0
"""Populate a local wheelhouse with TLS-verified, lock-matching PyPI wheels.

Useful when an older pip lacks the operating system's CA integration. This
does not disable TLS verification or relax the checked-in hash lock.
"""
import hashlib
import json
import re
from pathlib import Path
from urllib.request import urlopen
from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import parse_wheel_filename


def main():
    root = Path(__file__).resolve().parents[1]
    lock = (root / "ci/requirements.lock").read_text()
    hashes = set(re.findall(r"--hash=sha256:([a-f0-9]{64})", lock))
    tags = set(sys_tags())
    target = root / ".local/wheelhouse"
    target.mkdir(parents=True, exist_ok=True)
    for name, version in re.findall(r"^([A-Za-z0-9_-]+)==([^\s]+)", lock, re.M):
        with urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as response:
            files = json.load(response)["urls"]
        wheels = [item for item in files if item["filename"].endswith(".whl")
                  and parse_wheel_filename(item["filename"])[3] & tags]
        if not wheels:
            raise SystemExit("No compatible locked wheel")
        item = sorted(wheels, key=lambda wheel: wheel["filename"])[0]
        with urlopen(item["url"], timeout=120) as response:
            data = response.read()
        digest = hashlib.sha256(data).hexdigest()
        if digest not in hashes or digest != item["digests"]["sha256"]:
            raise SystemExit("Wheel hash differs from the reviewed lock")
        (target / item["filename"]).write_bytes(data)
        print(name + " verified")


if __name__ == "__main__":
    main()
