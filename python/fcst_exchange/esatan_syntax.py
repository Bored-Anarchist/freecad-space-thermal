# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded, byte-preserving ESATAN statement scanning; source is always data."""
import re

from fcst_app.persistence import encode
from .core import Limits, reject
from .syntax import Record

NAME = r'[A-Za-z][A-Za-z0-9_]{0,63}'


class EsatanRecord(Record):
    @property
    def source_id(self):
        # Several semicolon statements may occupy one physical source line.
        return f'{self.path}:{self.line}:{self.start}'


def statements(path, raw, *, native=False, limits=Limits(), line_statements=False):
    """Keep whitespace/comments in each span. Quotes/comments cannot end statements.

    D-deck directives and BEGIN/END_MODEL are line records; other declarations
    are semicolon records. Unfinished source is retained with an explicit error.
    Offsets are byte offsets, including non-ASCII labels and CRLF line endings.
    """
    if not isinstance(raw, bytes) or len(raw) > limits.file_bytes:
        reject('esatan_file_limit')
    if any(len(line) > limits.line_bytes for line in raw.splitlines()):
        reject('esatan_line_limit')
    records = []
    start = pos = line = 0
    quote = None
    block = False
    comment = False
    depth = []
    text = bytearray()
    line_mode = line_statements

    def emit(end, code=''):
        nonlocal start, text, line, line_mode
        content = raw[start:end]
        try:
            value = text.decode('utf-8').strip()
        except UnicodeError:
            value = ''; code = 'esatan_encoding'
        kind = 'COMMENT' if not value else 'STATEMENT'
        if value.startswith('$') or native and re.match(r'^(?:BEGIN_MODEL|END_MODEL)\b', value):
            kind = 'DIRECTIVE'
        if not native and value.startswith('$'):
            line_mode = value.split()[0].upper() in {'$INITIAL','$EXECUTION','$VARIABLES1','$VARIABLES2','$OUTPUTS','$SUBROUTINES'}
        if len(records) >= limits.records:
            reject('esatan_record_limit')
        records.append(EsatanRecord(path, start, end, line + 1, kind, content,
                              encode({'text': value}), code))
        line += content.count(b'\n')
        start = end; text = bytearray()

    while pos < len(raw):
        char = raw[pos]
        following = raw[pos:pos+2]
        if block:
            if following == b'*/':
                block = False; text.extend(b' '); pos += 2; continue
        elif comment:
            if char == 10:
                comment = False
                if not text.strip() or line_mode or text.lstrip().startswith(b'$'):
                    emit(pos+1); pos += 1; continue
                text.extend(b' ')
        elif quote is not None:
            text.append(char)
            if char == quote:
                # Fortran doubled quotes are literal quote characters.
                if pos+1 < len(raw) and raw[pos+1] == quote:
                    text.append(char); pos += 2; continue
                quote = None
        elif following == b'/*' and native:
            block = True; pos += 2; continue
        elif char == 35 and not native:
            comment = True
        elif not native and char in (67, 99, 42, 33) and (pos == 0 or raw[pos-1] == 10) and (pos+1 == len(raw) or raw[pos+1] in b' \r\n'):
            # Fixed-form Fortran comments, including in unsupported logic blocks.
            comment = True
        elif char in (34, 39):
            quote = char; text.append(char)
        elif char in (40, 91, 123):
            depth.append(char); text.append(char)
            if len(depth) > 32: reject('esatan_nesting_limit')
        elif char in (41, 93, 125):
            if not depth or depth.pop() != {41:40, 93:91, 125:123}[char]:
                reject('esatan_unbalanced_delimiter')
            text.append(char)
        elif char == 59 and not depth:
            text.append(char)
            emit(pos+1)
        elif char == 10 and not depth and not text.strip():
            emit(pos+1)
        elif char == 10 and not depth and (text.lstrip().startswith(b'$') or native and
                re.match(rb'\s*(?:BEGIN_MODEL|END_MODEL)\b', text)):
            emit(pos+1)
        elif char == 10 and not depth and line_mode:
            emit(pos+1)
        else:
            text.append(char)
        pos += 1
    if start < len(raw):
        code = 'esatan_unterminated_syntax' if quote or block or depth else ''
        if text.strip() and not (text.lstrip().startswith(b'$') or native and
                re.match(rb'\s*(?:BEGIN_MODEL|END_MODEL)\b', text)):
            code = code or 'esatan_missing_semicolon'
        emit(len(raw), code)
    return tuple(records)


def split(text, separator=','):
    """Split only at top level, with closed quote/bracket syntax."""
    result = []; start = 0; stack = []; quote = None; pos = 0
    while pos < len(text):
        c = text[pos]
        if quote:
            if c == quote:
                if pos+1 < len(text) and text[pos+1] == quote:
                    pos += 2; continue
                quote = None
        elif c in '\"\'': quote = c
        elif c in '([{':
            stack.append(c)
            if len(stack) > 32: reject('esatan_nesting_limit')
        elif c in ')]}':
            if not stack or stack.pop() != {')':'(', ']':'[', '}':'{'}[c]:
                reject('esatan_unbalanced_delimiter')
        elif c == separator and not stack:
            result.append(text[start:pos].strip()); start = pos+1
        pos += 1
    if quote or stack: reject('esatan_unterminated_syntax')
    result.append(text[start:].strip())
    return result


def assignments(text):
    result = {}
    for field in split(text):
        m = re.fullmatch('('+NAME+r')\s*=\s*(.+)', field, re.S)
        if not m or m[1].upper() in result: reject('esatan_duplicate_or_invalid_field')
        result[m[1].upper()] = m[2].strip()
    return result
