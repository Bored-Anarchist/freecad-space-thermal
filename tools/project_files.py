# SPDX-License-Identifier: MIT OR Apache-2.0
"""Select project documentation without reading ignored engineering/build stores."""
import subprocess
from pathlib import Path


def markdown_files(root: Path):
    result = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.md"],
                            cwd=root, capture_output=True, timeout=30, check=True)
    for name in sorted(set(result.stdout.decode("utf-8").split("\0")) - {""}):
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Project documentation escapes source root")
        if path.is_file():
            yield path
