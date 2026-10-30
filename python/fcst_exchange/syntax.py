# SPDX-License-Identifier: MIT OR Apache-2.0
"""Byte-preserving line syntax for the explicit fcst-network/1 reference dialect."""
from dataclasses import dataclass
from hashlib import sha256
import json

from fcst_contracts import ContractError, loads

KINDS = {"ENTITY", "CASE", "MAPPING", "ATTACHMENT", "EXPRESSION", "PROCEDURE", "INCLUDE", "RESULT", "DATA"}


@dataclass(frozen=True)
class Record:
    path: str
    start: int
    end: int
    line: int
    kind: str
    content: bytes
    payload: bytes | None
    code: str = ""

    @property
    def value(self):
        return json.loads(self.payload) if self.payload is not None else None

    @property
    def source_id(self):
        return f"{self.path}:{self.line}"

    @property
    def digest(self):
        return sha256(self.content).hexdigest()


def parse(path, raw, limits):
    # Decode only for recognition. Byte offsets and every original byte survive.
    if len(raw) > limits.file_bytes:
        from .core import reject
        reject("file_limit")
    records, offset = [], 0
    for line, content in enumerate(raw.splitlines(keepends=True), 1):
        if len(records) >= limits.records or len(content) > limits.line_bytes:
            from .core import reject
            reject("record_limit")
        payload, code = None, ""
        try:
            text = content.decode("utf-8").strip()
            if not text or text.startswith("#"):
                kind = "COMMENT"
            else:
                parts = text.split(None, 1)
                kind = parts[0]
                if kind not in KINDS:
                    kind, code = "OPAQUE", "unknown_syntax"
                else:
                    try:
                        value = loads(parts[1]) if len(parts) == 2 else None
                        if not isinstance(value, dict):
                            raise ValueError()
                        payload = json.dumps(value, sort_keys=True, allow_nan=False).encode()
                    except (ContractError, ValueError, UnicodeError, RecursionError):
                        code = "malformed_record"
        except UnicodeError:
            kind, code = "OPAQUE", "unsupported_encoding"
        records.append(Record(path, offset, offset+len(content), line, kind, content, payload, code))
        offset += len(content)
    return tuple(records)
