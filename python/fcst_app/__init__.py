# SPDX-License-Identifier: MIT OR Apache-2.0
"""Host-independent application contracts; no thermal solver in Python."""
from dataclasses import dataclass

__version__ = "0.1.0"


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str


def capabilities() -> dict:
    return {"api_version": 1, "engine": "fcst_native", "solver_available": False,
            "freecad_required": False, "vendor_runtime_required": False}
