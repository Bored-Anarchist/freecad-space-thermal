# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned thermal preparation acceptance identity, separate from solver qualification."""
from hashlib import sha256
from .gate import evaluate


def input_hashes(root):
    names = ['CMakeLists.txt', 'CMakePresets.json', 'engine/src/contracts.cpp',
             'engine/worker/main.cpp', 'engine/include/fcst/contract_bundle.hpp',
             'tools/generate_contracts.py', 'tools/thermal_schema.py', 'tools/check_thermal.py',
             'python/fcst_tools/thermal.py', 'ci/thermal-acceptance.json',
             'spec/schemas/thermal-input-v1.schema.json']
    for folder in ('engine/include/fcst', 'engine/src', 'engine/tests', 'tests/fixtures/thermal'):
        names += [p.relative_to(root).as_posix() for p in (root/folder).glob('*')
                  if p.is_file() and ('thermal' in p.name or folder.endswith(('tests', 'thermal')))]
    return {name: sha256((root/name).read_bytes()).hexdigest() for name in sorted(set(names))}


def assess(report, policy, hashes, candidate):
    if (report.get('schema_version') != 1 or report.get('candidate') != candidate
            or report.get('input_sha256') != hashes or report.get('solver_available') is not False
            or report.get('work_packages') != ['WP-11.1', 'WP-11.2']
            or report.get('gate', {}).get('status') != 'passed'
            or evaluate(policy['required_cases'], report.get('cases', []))['status'] != 'passed'):
        raise ValueError('thermal_preparation_evidence_invalid')
    return True
