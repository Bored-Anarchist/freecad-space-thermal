# SPDX-License-Identifier: MIT OR Apache-2.0
"""Reference transcript validator for the frozen worker protocol, without execution."""
from . import ContractError, read


class Transcript:
    """One job and direction at a time; the receiver owns this state."""
    def __init__(self):
        self.job_id = None
        self.sequence = -1
        self.state = "new"
        self.snapshot_hash = None

    def accept(self, message):
        message = read("worker", message)
        kind = message["type"]
        allowed = {"new": {"handshake"}, "ready": {"submit"},
                   "running": {"progress", "diagnostic", "checkpoint", "cancel", "terminal"},
                   "cancelling": {"progress", "diagnostic", "checkpoint", "terminal"}, "terminal": set()}
        if kind not in allowed[self.state] or message["sequence"] != self.sequence + 1:
            raise ContractError("reference")
        if self.job_id is not None and message["job_id"] != self.job_id:
            raise ContractError("reference")
        if kind == "checkpoint" and message["payload"]["snapshot_hash"] != self.snapshot_hash:
            raise ContractError("artifact")
        self.job_id = message["job_id"]
        self.sequence = message["sequence"]
        if kind == "submit":
            self.snapshot_hash = message["payload"]["semantic_hash"]
        self.state = {"handshake": "ready", "submit": "running", "cancel": "cancelling", "terminal": "terminal"}.get(kind, self.state)
        return message
