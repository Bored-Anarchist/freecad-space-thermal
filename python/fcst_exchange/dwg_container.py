# SPDX-License-Identifier: MIT OR Apache-2.0
"""Conservative audits of independent DWG decoders; no thermal interpretation.

Decoder JSON is private input, never trusted evidence of a lossless drawing.
Opaque bit counts, stable handles and every decoded object/class field are checked.
No class name or source value is included in the bounded public verdict.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re

from .core import reject


@dataclass(frozen=True)
class DwgAuditLimits:
    bytes: int = 67108864
    objects: int = 100000
    values: int = 2000000
    depth: int = 32

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in self.__dict__.values()):
            reject('dwg_audit_limits')


def document(raw, *, limits=DwgAuditLimits()):
    if not isinstance(raw, bytes) or not raw or len(raw) > limits.bytes:
        reject('dwg_json_size')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                reject('dwg_json_duplicate_key')
            result[key] = value
        return result
    try:
        data = json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: reject('dwg_json_number'))
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        # ExchangeError is a ValueError: preserve only our fixed diagnostic codes.
        if getattr(error, 'code', '').startswith('dwg_'):
            raise
        reject('dwg_json_contract')
    pending = [(data, 0)]; count = 0
    while pending:
        value, depth = pending.pop(); count += 1
        if count > limits.values or depth > limits.depth:
            reject('dwg_json_structure_limit')
        if isinstance(value, dict):
            pending.extend((v, depth+1) for v in value.values())
        elif isinstance(value, list):
            pending.extend((v, depth+1) for v in value)
        elif isinstance(value, float) and not math.isfinite(value):
            reject('dwg_json_number')
    if (not isinstance(data, dict) or not isinstance(data.get('FILEHEADER'), dict)
            or not isinstance(data['FILEHEADER'].get('version'), str)
            or not re.fullmatch(r'AC10[0-9]{2}', data['FILEHEADER']['version'])
            or not isinstance(data.get('CLASSES'), list)
            or not isinstance(data.get('OBJECTS'), list)
            or len(data['CLASSES']) > limits.objects or len(data['OBJECTS']) > limits.objects):
        reject('dwg_json_contract')
    classes = set(); handles = set()
    for row in data['CLASSES']:
        if (not isinstance(row, dict) or type(row.get('number')) is not int
                or row['number'] < 500 or row['number'] in classes
                or not isinstance(row.get('cppname'), str) or not row['cppname']):
            reject('dwg_class_identity')
        classes.add(row['number'])
    for row in data['OBJECTS']:
        if not isinstance(row, dict):
            reject('dwg_object_contract')
        handle = row.get('handle')
        if (not isinstance(handle, list) or len(handle) != 3
                or any(type(x) is not int or x < 0 for x in handle)
                or handle[0] != 0 or handle[2] == 0 or handle[2] in handles
                or type(row.get('type')) is not int or row['type'] < 0
                or row['type'] >= 500 and row['type'] not in classes
                or not isinstance(row.get('entity', row.get('object')), str)):
            reject('dwg_object_identity')
        handles.add(handle[2])
        if 'unknown_bits' in row or row.get('entity', row.get('object')) in {'UNKNOWN_ENT', 'UNKNOWN_OBJ'}:
            if (type(row.get('num_unknown_bits')) is not int or row['num_unknown_bits'] < 0
                    or not isinstance(row.get('unknown_bits'), str)
                    or not re.fullmatch(r'(?:[0-9a-fA-F]{2})*', row['unknown_bits'])):
                reject('dwg_opaque_contract')
    return data


def _opaque(row):
    return 'unknown_bits' in row or row.get('entity', row.get('object')) in {'UNKNOWN_ENT', 'UNKNOWN_OBJ'}


def audit(raw, *, limits=DwgAuditLimits()):
    data = document(raw, limits=limits)
    opaque = [row for row in data['OBJECTS'] if _opaque(row)]
    mismatch = sum(len(row['unknown_bits'])//2 != (row['num_unknown_bits']+7)//8 for row in opaque)
    return {'version': data['FILEHEADER']['version'], 'classes': len(data['CLASSES']),
            'objects': len(data['OBJECTS']), 'opaque_objects': len(opaque),
            'opaque_bit_length_mismatches': mismatch, 'document_sha256': sha256(raw).hexdigest(),
            'thermal_mapping': 'not_implemented', 'native_ready': False, 'qualified': False}


def compare(before_raw, after_raw, *, limits=DwgAuditLimits()):
    before = document(before_raw, limits=limits); after = document(after_raw, limits=limits)
    a = audit(before_raw, limits=limits); b = audit(after_raw, limits=limits)
    def classes(data):
        return {row['number']: row for row in data['CLASSES']}
    def objects(data):
        # Physical encoded lengths and array indices may change during a rewrite.
        # Every other field, including references and opaque tails, must match.
        return {row['handle'][2]: {k: v for k, v in row.items() if k not in {'size', 'bitsize', 'index'}}
                for row in data['OBJECTS']}
    ac, bc = classes(before), classes(after); ao, bo = objects(before), objects(after)
    changed_classes = sum(ac.get(k) != bc.get(k) for k in ac.keys() | bc.keys())
    changed_objects = sum(ao.get(k) != bo.get(k) for k in ao.keys() | bo.keys())
    # Compare payloads separately so that decoder agreement cannot conceal a
    # missing final byte or changed layer/material/reference on an opaque entity.
    def payloads(data):
        return {row['handle'][2]: (row['type'], row['num_unknown_bits'], row['unknown_bits'].lower())
                for row in data['OBJECTS'] if _opaque(row)}
    payload_equal = payloads(before) == payloads(after)
    same_version = a['version'] == b['version']
    same_header = before['HEADER'] == after['HEADER'] if 'HEADER' in before and 'HEADER' in after else False
    sections = (before.keys() | after.keys()) - {'FILEHEADER','R2004_Header','CLASSES','OBJECTS','HEADER'}
    changed_sections = sum(before.get(k) != after.get(k) for k in sections)
    structural = (same_version and same_header and payload_equal and not changed_classes and not changed_objects and not changed_sections
                  and not a['opaque_bit_length_mismatches'] and not b['opaque_bit_length_mismatches'])
    return {'same_version': same_version, 'same_header': same_header,
            'opaque_inventory_equal': payload_equal,
            'opaque_bit_lengths_valid': not a['opaque_bit_length_mismatches'] and not b['opaque_bit_length_mismatches'],
            'changed_classes': changed_classes, 'changed_objects': changed_objects, 'changed_sections': changed_sections,
            'decoded_inventory_preserved': structural,
            'thermal_mapping': 'not_implemented', 'native_ready': False, 'qualified': False}
