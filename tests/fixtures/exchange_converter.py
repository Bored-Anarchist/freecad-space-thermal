# SPDX-License-Identifier: MIT OR Apache-2.0
"""Trusted synthetic subprocess for Windows converter containment acceptance."""
import os
from pathlib import Path
import subprocess
import sys
import time

scenario = sys.argv[1]
if scenario == "timeout":
    time.sleep(30)
elif scenario == "flood":
    while True:
        os.write(sys.stdout.fileno(),b"x"*4096)
elif scenario == "disk":
    Path("result.txt").write_bytes(b"x"*2000000)
    time.sleep(30)
elif scenario == "child":
    subprocess.Popen([sys.executable,__file__,"late-child"])
    time.sleep(30)
elif scenario == "late-child":
    time.sleep(2)
    Path("escaped.txt").write_text("bad")
elif scenario == "undeclared":
    Path("unexpected.txt").write_text("bad")
elif scenario == "mutate":
    Path("input.txt").write_text("changed")
    Path("result.txt").write_text("output")
else:
    assert "SECRET_TEST_VALUE" not in os.environ
    Path("result.txt").write_bytes(Path("input.txt").read_bytes().upper())
