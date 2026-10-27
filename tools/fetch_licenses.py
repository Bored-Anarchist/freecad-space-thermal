# SPDX-License-Identifier: MIT OR Apache-2.0
"""Retrieve unmodified public license texts from the versioned SPDX data set."""
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    target = ROOT / "LICENSES"
    target.mkdir(exist_ok=True)
    for name in ["MIT", "Apache-2.0", "CC-BY-4.0"]:
        url = f"https://raw.githubusercontent.com/spdx/license-list-data/v3.25.0/text/{name}.txt"
        with urlopen(url, timeout=30) as response:
            data = response.read()
        (target / (name + ".txt")).write_bytes(data)
        print(name + " license text retrieved")
