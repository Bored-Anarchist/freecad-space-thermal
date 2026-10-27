# SPDX-License-Identifier: MIT OR Apache-2.0
"""Use the repository's reviewed scanner before any upload, including prose."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from fcst_tools.privacy import main

if __name__ == "__main__":
    raise SystemExit(main())
